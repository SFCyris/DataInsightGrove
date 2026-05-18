"""Render geographical points on an interactive world map.

Two output formats:
  - **html** (default): a self-contained HTML file using Leaflet + OpenStreetMap-
    style tiles via CDN. The user can pan / zoom / hover to see the per-point
    tooltip ("Name" in bold, "Comment" underneath). Embeds the data inline so
    the file works offline once the tiles cache. The page is responsive — the
    map fills its container so the same artifact looks right at 100×100 in a
    dashboard cell and at 1920×1080 in a fullscreen viewer.
  - **png**: a static raster with a real basemap behind the points (slippy-map
    tiles fetched from the same CDN as the HTML, stitched and projected with
    PIL — no cartopy / geopandas needed). The bbox auto-fits the points with a
    10% padding so a tight cluster doesn't get rendered against an empty world
    view. If the network is unavailable, the renderer falls back to a clean
    graticule over the auto-fitted bbox.

Coordinate parsing handles four common encodings:
  - ``lat_lon`` — "37.77, -122.42" or "37.77 -122.42" (Google / Apple)
  - ``lon_lat`` — "-122.42, 37.77" (GeoJSON / WKT axis order)
  - ``wkt_point`` — "POINT(-122.42 37.77)" / "SRID=4326;POINT(...)"
  - ``separate_columns`` — pick the lat + lon columns directly

The HTML output keeps the same DIG emerald palette as the rest of the app
(marker color defaults to #10b981) so the map slides into the editor preview
without standing out.

Built without folium / cartopy / geopandas on purpose: those bring in heavy
GIS deps that we don't need for "drop dots on a world map". Leaflet is loaded
from a CDN inside the artifact HTML — same model as a Google Maps embed. PIL
(already a matplotlib transitive dependency) handles the PNG basemap stitch.
"""

from __future__ import annotations

import json
import math
import os
import re
from html import escape as _escape
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step

# Lat/lon range for sanity-checking parsed coords. Any point outside this is
# silently dropped from the map (mostly catches NaN / unset / wrong-format).
_LAT_RANGE = (-90.0, 90.0)
_LON_RANGE = (-180.0, 180.0)

_WKT_POINT_RE = re.compile(
    r"POINT\s*\(\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s+([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*\)",
    re.IGNORECASE,
)


# Pen-tester round-2: marker_color / line_color reach the HTML artifact through
# raw f-string interpolation (`{line_color}` inside `'…'`) AND through
# matplotlib's `color=` kwarg. Both surfaces accept any string the user
# supplies — including `'+fetch('/api/datasets',{headers:...}).then(...)+'`
# which slips out of the JS string literal and runs in the iframe origin.
# Lock down to a strict CSS-color allow-list before either render path
# sees the value. Hex / rgb() / rgba() / hsl() / hsla() + the small set of
# CSS named colours we'd actually ship as a default.
_COLOR_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_COLOR_RGB_RE = re.compile(
    r"^rgba?\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*"
    r"(?:,\s*(?:1(?:\.0+)?|0?\.\d+|0)\s*)?\)$"
)
_COLOR_HSL_RE = re.compile(
    r"^hsla?\(\s*\d{1,3}(?:\.\d+)?\s*,\s*\d{1,3}(?:\.\d+)?%\s*,\s*\d{1,3}(?:\.\d+)?%\s*"
    r"(?:,\s*(?:1(?:\.0+)?|0?\.\d+|0)\s*)?\)$"
)
_COLOR_NAMED = frozenset({
    # Limited to the common safe set + a handful DIG's defaults touch.
    "black", "white", "red", "green", "blue", "yellow", "orange", "purple",
    "pink", "brown", "gray", "grey", "cyan", "magenta", "lime", "navy",
    "teal", "olive", "maroon", "silver", "gold", "violet", "indigo",
    "transparent", "currentcolor",
})


def _validate_css_color(value: Any, *, fallback: str) -> str:
    """Return value if it parses as a safe CSS color, otherwise fallback.

    Defence-in-depth: even a value that *parses* is then JS-string-escaped
    by `_js_safe_json` — but the escape can't help if a future renderer
    interpolates the value bare. Validation is the structural fix.
    """
    if not isinstance(value, str):
        return fallback
    s = value.strip()
    if not s:
        return fallback
    if _COLOR_HEX_RE.match(s):
        return s
    if _COLOR_RGB_RE.match(s):
        return s
    if _COLOR_HSL_RE.match(s):
        return s
    if s.lower() in _COLOR_NAMED:
        return s.lower()
    return fallback


def _parse_pair(raw: Any, fmt: str) -> tuple[float, float] | None:
    """Parse a location string into (lat, lon).

    Returns None for any value that doesn't look like a valid pair.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None

    if fmt == "wkt_point":
        m = _WKT_POINT_RE.search(s)
        if m is None:
            return None
        lon = float(m.group(1))
        lat = float(m.group(2))
        return (lat, lon)

    # lat_lon / lon_lat — split on comma, semicolon, or whitespace.
    parts = re.split(r"[\s,;]+", s.strip("()[]{}"))
    parts = [p for p in parts if p]
    if len(parts) < 2:
        return None
    try:
        a = float(parts[0])
        b = float(parts[1])
    except (TypeError, ValueError):
        return None
    if fmt == "lon_lat":
        return (b, a)
    return (a, b)


def _is_valid_latlon(lat: float, lon: float) -> bool:
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return False
    if not (_LAT_RANGE[0] <= lat <= _LAT_RANGE[1]):
        return False
    if not (_LON_RANGE[0] <= lon <= _LON_RANGE[1]):
        return False
    # Drop the (0,0) "null island" — almost certainly missing data, not the
    # Atlantic equator. If a real run actually maps to (0,0) the user can
    # set a marker manually.
    if abs(lat) < 1e-9 and abs(lon) < 1e-9:
        return False
    return True


def _extract_points(
    df: pl.DataFrame,
    fmt: str,
    location: str | None,
    lat_col: str | None,
    lon_col: str | None,
    name_col: str | None,
    comment_col: str | None,
) -> list[dict[str, Any]]:
    """Walk the DataFrame and build a list of {lat, lon, name, comment} dicts.

    Skips rows whose coords don't parse / are out of range. The list ends up
    JSON-encoded and embedded in the HTML, so we keep the keys short.
    """
    pts: list[dict[str, Any]] = []

    if fmt == "separate_columns":
        if not (lat_col and lon_col):
            raise ValueError(
                "export_to_map: format='separate_columns' requires both lat_col and lon_col"
            )
        if lat_col not in df.columns:
            raise ValueError(f"export_to_map: lat column '{lat_col}' not in input")
        if lon_col not in df.columns:
            raise ValueError(f"export_to_map: lon column '{lon_col}' not in input")
        lats = df.get_column(lat_col).cast(pl.Float64, strict=False).to_list()
        lons = df.get_column(lon_col).cast(pl.Float64, strict=False).to_list()
        names = df.get_column(name_col).cast(pl.Utf8).to_list() if name_col and name_col in df.columns else [None] * df.height
        comments = df.get_column(comment_col).cast(pl.Utf8).to_list() if comment_col and comment_col in df.columns else [None] * df.height
        for i in range(df.height):
            lat = lats[i] if lats[i] is not None else float("nan")
            lon = lons[i] if lons[i] is not None else float("nan")
            if not _is_valid_latlon(lat, lon):
                continue
            pts.append({
                "lat": lat,
                "lon": lon,
                "n": names[i] if names[i] is not None else f"Point {i + 1}",
                "c": comments[i] if comments[i] is not None else "",
            })
        return pts

    if not location:
        raise ValueError("export_to_map: 'location' column is required (set 'format=separate_columns' to use lat/lon columns instead)")
    if location not in df.columns:
        raise ValueError(f"export_to_map: location column '{location}' not in input")

    locs = df.get_column(location).cast(pl.Utf8).to_list()
    names = df.get_column(name_col).cast(pl.Utf8).to_list() if name_col and name_col in df.columns else [None] * df.height
    comments = df.get_column(comment_col).cast(pl.Utf8).to_list() if comment_col and comment_col in df.columns else [None] * df.height

    for i in range(df.height):
        parsed = _parse_pair(locs[i], fmt)
        if parsed is None:
            continue
        lat, lon = parsed
        if not _is_valid_latlon(lat, lon):
            continue
        pts.append({
            "lat": lat,
            "lon": lon,
            "n": names[i] if names[i] is not None else f"Point {i + 1}",
            "c": comments[i] if comments[i] is not None else "",
        })
    return pts


# ---- HTML emit -----------------------------------------------------------

_TILE_LAYERS = {
    "osm": {
        "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "attribution": "&copy; OpenStreetMap contributors",
    },
    "carto-light": {
        "url": "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        "attribution": "&copy; OpenStreetMap &copy; CARTO",
    },
    "carto-dark": {
        "url": "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
        "attribution": "&copy; OpenStreetMap &copy; CARTO",
    },
    "esri-natgeo": {
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/NatGeo_World_Map/MapServer/tile/{z}/{y}/{x}",
        "attribution": "&copy; Esri / National Geographic",
    },
}


def _emit_html(
    points: list[dict[str, Any]],
    title: str,
    width: int,
    height: int,
    marker_color: str,
    marker_radius: int,
    tile_provider: str,
    overlay_polygons: list[bytes] | None = None,
) -> str:
    """Return a self-contained HTML document with a Leaflet map.

    All data is embedded in a JSON literal — no external fetch beyond the
    Leaflet library + tiles. The page works in an iframe (sandbox-safe) and
    doesn't read or set cookies.

    Security note: the JSON ``payload`` is interpolated into a ``<script>``
    block, so any ``</script>`` substring inside a user value would close
    the script tag early and let arbitrary HTML/JS escape into the
    document. ``json.dumps`` does not escape ``<``/``/`` by default, so we
    manually replace ``</`` → ``<\\/``, ``<!--`` → ``<\\!--``, and the
    line-separator / paragraph-separator characters that some browsers
    treat as JS line terminators (U+2028 / U+2029). This matches the
    standard JSON-in-HTML escape recommended by OWASP and used by Rails,
    Django, and ASP.NET. The marker_color string takes the same treatment
    since it ends up in the script too.
    """
    safe_title = _escape(title or "Map")

    def _js_safe_json(obj: Any) -> str:
        # Two critical breaks in HTML-script context:
        #   * </script> inside a JSON string closes the wrapping
        #     <script> tag early — XSS escape vector. Replace </
        #     with <\/ inside the JSON output.
        #   * <!-- inside JS opens a parser CDATA-like state in
        #     legacy browsers. Same fix shape.
        # ensure_ascii=True emits U+2028 / U+2029 (the two Unicode
        # chars JS treats as line terminators) as \uXXXX escapes
        # instead of raw bytes — closes the third common
        # JSON-in-script attack.
        s = json.dumps(obj, separators=(",", ":"), ensure_ascii=True)
        return s.replace("</", "<\\/").replace("<!--", "<\\!--")

    payload = _js_safe_json(points)
    # Overlay polygons (multi-layer): rendered as an outlined geo-JSON
    # layer underneath the markers. Empty list → empty FeatureCollection,
    # cheap to inline.
    overlay_geojson = _polygons_to_geojson(overlay_polygons or []).replace("</", "<\\/")
    tile = _TILE_LAYERS.get(tile_provider) or _TILE_LAYERS["carto-light"]
    tile_url = tile["url"]
    tile_attr = tile["attribution"]

    # Center + zoom: if we have points, center on their bbox; else default
    # to a wide world view. The frontend code re-fits the map after load
    # to the actual marker bounds (one-line fitBounds call).
    if points:
        lats = [p["lat"] for p in points]
        lons = [p["lon"] for p in points]
        center_lat = (min(lats) + max(lats)) / 2
        center_lon = (min(lons) + max(lons)) / 2
        center = (center_lat, center_lon)
    else:
        center = (20.0, 0.0)

    # Inline JS / HTML — no f-string interpolation inside the script block
    # (avoids the brace-doubling that template strings would force on us).
    # The ``width`` / ``height`` params are kept as ``min-width`` / ``min-height``
    # hints so the map has a sensible "natural size" when the artifact opens
    # in a new tab. The actual map fills its container — same artifact
    # works in a 100×100 dashboard cell, an 800×600 iframe, or a fullscreen
    # browser tab. The ResizeObserver below reflows the map when the
    # surrounding window/iframe changes size.
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{safe_title}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
<style>
  html, body {{
    margin: 0;
    padding: 0;
    width: 100%;
    height: 100%;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    background: #fafafa;
    overflow: hidden;
  }}
  /* The map fills its container all the way down. Width/height percentages
     are inherited from <html>/<body>, so the map always tracks the actual
     viewport (or iframe) — not a fixed pixel size baked at render time. */
  #dig-map-shell {{
    position: relative;
    width: 100%;
    height: 100%;
    min-width: {int(width)}px;
    min-height: {int(height)}px;
  }}
  /* Dashboard / iframe context: when the host's CSS clamps us to a smaller
     box than the natural minimum, drop the min so the map still fits.
     ``contain: size`` would do the same job but is poorly supported in
     older Edge/Safari. */
  @media (max-width: {int(width)}px), (max-height: {int(height)}px) {{
    #dig-map-shell {{
      min-width: 0;
      min-height: 0;
    }}
  }}
  #dig-map {{
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
  }}
  .dig-tooltip {{
    font-size: 12px;
    line-height: 1.35;
    padding: 6px 8px;
    max-width: 280px;
    word-wrap: break-word;
  }}
  .dig-tooltip .dig-name {{
    font-weight: 700;
    color: #0f172a;
    font-size: 13px;
  }}
  .dig-tooltip .dig-comment {{
    color: #475569;
    margin-top: 2px;
    white-space: pre-wrap;
  }}
  .dig-empty {{
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: #94a3b8;
    font-size: 14px;
    font-style: italic;
  }}
  .dig-title-bar {{
    position: absolute;
    top: 8px;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(255, 255, 255, 0.93);
    border: 1px solid rgba(15, 23, 42, 0.08);
    border-radius: 8px;
    padding: 4px 12px;
    font-size: 12px;
    font-weight: 600;
    color: #0f172a;
    z-index: 1000;
    pointer-events: none;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
    max-width: calc(100% - 24px);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}
</style>
</head>
<body>
<div id="dig-map-shell">
  <div class="dig-title-bar">{safe_title}</div>
  <div id="dig-map" role="img" aria-label="{safe_title}"></div>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<script>
(function () {{
  var POINTS = {payload};
  var MARKER_COLOR = {_js_safe_json(marker_color)};
  var MARKER_RADIUS = {int(marker_radius)};
  var center = [{center[0]}, {center[1]}];
  var map = L.map('dig-map', {{
    zoomControl: true,
    attributionControl: true,
    worldCopyJump: true,
  }}).setView(center, POINTS.length ? 3 : 2);

  L.tileLayer({_js_safe_json(tile_url)}, {{
    attribution: {_js_safe_json(tile_attr)},
    maxZoom: 18,
    subdomains: 'abcd',
    detectRetina: true,
  }}).addTo(map);

  // Overlay polygons (drawn under the markers) — e.g. named zones the
  // user wants the markers placed inside. Empty FeatureCollection is
  // a no-op.
  var OVERLAY = {overlay_geojson};
  if (OVERLAY && OVERLAY.features && OVERLAY.features.length) {{
    L.geoJSON(OVERLAY, {{
      style: {{
        color: '#374151',
        weight: 1.2,
        fillColor: MARKER_COLOR,
        fillOpacity: 0.10,
      }},
      interactive: false,
    }}).addTo(map);
  }}

  var bounds = [];
  POINTS.forEach(function (p) {{
    var marker = L.circleMarker([p.lat, p.lon], {{
      radius: MARKER_RADIUS,
      color: MARKER_COLOR,
      weight: 1.5,
      fillColor: MARKER_COLOR,
      fillOpacity: 0.7,
    }}).addTo(map);
    bounds.push([p.lat, p.lon]);

    // Hover tooltip — name in bold, comment beneath. Permanent tooltip on
    // mouseover (sticky), hidden on mouseout. Click toggles a pinned
    // popup so users can keep one open while zooming.
    var html = '<div class="dig-tooltip">' +
               '<div class="dig-name"></div>' +
               (p.c ? '<div class="dig-comment"></div>' : '') +
               '</div>';
    var tip = document.createElement('div');
    tip.innerHTML = html;
    // Use textContent to neutralise any HTML in the input fields.
    tip.querySelector('.dig-name').textContent = p.n || '';
    var commentEl = tip.querySelector('.dig-comment');
    if (commentEl) commentEl.textContent = p.c || '';
    marker.bindTooltip(tip.innerHTML, {{
      direction: 'top',
      offset: [0, -MARKER_RADIUS],
      sticky: true,
    }});
    marker.bindPopup(tip.innerHTML, {{ maxWidth: 320 }});
  }});

  // Refit on every layout change. fitBounds runs once at boot, then we
  // attach a ResizeObserver so the map reflows when the iframe / window
  // changes size — otherwise a window resize leaves Leaflet sized to the
  // initial dimensions and tiles render outside the visible box.
  //
  // Padding is proportional to the viewport so a very narrow iframe
  // (dashboard tile, mobile drawer) doesn't waste a quarter of its width
  // on whitespace, and a poster-sized export doesn't render markers
  // jammed against the edge.
  function refit() {{
    map.invalidateSize();
    // If a parent frame pre-seeded a viewport (DIG preview iframe
    // restoring the user's pan/zoom across a param edit), honour it
    // instead of refitting to the auto-bounds. The flag is consumed
    // after first use so a real window resize still re-fits.
    if (window.__DIG_INITIAL_VIEW__) {{
      var v = window.__DIG_INITIAL_VIEW__;
      window.__DIG_INITIAL_VIEW__ = null;
      map.setView([v.lat, v.lng], v.zoom);
      return;
    }}
    var shellEl = document.getElementById('dig-map-shell');
    var w = shellEl ? shellEl.clientWidth : 600;
    var h = shellEl ? shellEl.clientHeight : 400;
    var padX = Math.max(8, Math.min(48, Math.round(w * 0.04)));
    var padY = Math.max(8, Math.min(48, Math.round(h * 0.04)));
    if (bounds.length > 1) {{
      map.fitBounds(bounds, {{ padding: [padY, padX], maxZoom: 14 }});
    }} else if (bounds.length === 1) {{
      map.setView(bounds[0], 7);
    }}
  }}
  refit();
  // Push viewport changes to the host iframe so it can restore on the
  // next srcDoc swap. Standalone exports silently no-op.
  function _digPostViewport() {{
    if (window.parent === window) return;
    var c = map.getCenter();
    try {{
      window.parent.postMessage({{
        type: 'dig:map:viewport', lat: c.lat, lng: c.lng, zoom: map.getZoom(),
      }}, '*');
    }} catch (e) {{}}
  }}
  map.on('moveend', _digPostViewport);
  map.on('zoomend', _digPostViewport);
  // Belt-and-braces refit after a frame: Leaflet reads container size
  // synchronously during construction, but the iframe's layout often
  // settles a frame later (especially under aspect-ratio CSS). Without
  // this second pass the map sometimes renders before the iframe
  // reaches its final size.
  requestAnimationFrame(refit);
  if (bounds.length === 0) {{
    var el = document.getElementById('dig-map');
    var note = document.createElement('div');
    note.className = 'dig-empty';
    note.textContent = 'No valid coordinates to plot.';
    el.appendChild(note);
  }}
  // Container resize → re-invalidate. Works across all modern browsers
  // (Safari 14+, Chrome 64+, Firefox 69+). Falls back to window resize
  // for the rare case ResizeObserver is missing.
  var shell = document.getElementById('dig-map-shell');
  if (typeof ResizeObserver !== 'undefined') {{
    var ro = new ResizeObserver(function () {{ refit(); }});
    ro.observe(shell);
  }} else {{
    window.addEventListener('resize', refit);
  }}
}})();
</script>
</body>
</html>
"""
    return html


# ---- PNG fallback --------------------------------------------------------

# ---- PNG basemap (slippy-map tile stitching, no cartopy needed) ----------

# Web-mercator slippy-map math, after the OSM wiki spec. Public-domain math —
# the same formulas Leaflet itself uses, written out here so we can compute
# tile coords without dragging in a GIS lib.
_MERCATOR_LAT_LIMIT = 85.05112878  # the projection blows up near the poles


def _lonlat_to_xy(lon: float, lat: float, z: int) -> tuple[float, float]:
    """Web-mercator (EPSG:3857) tile coords at zoom z, fractional."""
    lat = max(-_MERCATOR_LAT_LIMIT, min(_MERCATOR_LAT_LIMIT, lat))
    n = 2.0 ** z
    x = (lon + 180.0) / 360.0 * n
    lat_rad = math.radians(lat)
    y = (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n
    return (x, y)


def _bbox_with_padding(
    points: list[dict[str, Any]], pad_frac: float = 0.10,
) -> tuple[float, float, float, float]:
    """Return (min_lon, min_lat, max_lon, max_lat) padded for nice framing.

    A single point gets a small synthetic bbox (~ 1° on each side) so the map
    doesn't degenerate to a single tile.
    """
    lats = [p["lat"] for p in points]
    lons = [p["lon"] for p in points]
    if not lats:
        return (-180.0, -85.0, 180.0, 85.0)
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)
    if max_lat == min_lat:
        max_lat += 0.5
        min_lat -= 0.5
    if max_lon == min_lon:
        max_lon += 0.5
        min_lon -= 0.5
    dlat = (max_lat - min_lat) * pad_frac
    dlon = (max_lon - min_lon) * pad_frac
    return (
        max(-180.0, min_lon - dlon),
        max(-_MERCATOR_LAT_LIMIT, min_lat - dlat),
        min(180.0, max_lon + dlon),
        min(_MERCATOR_LAT_LIMIT, max_lat + dlat),
    )


def _pick_zoom(
    bbox: tuple[float, float, float, float], pixel_w: int, pixel_h: int,
) -> int:
    """Highest zoom level whose tile coverage fits in the target raster.

    Slippy tiles are 256 px square. A bbox at zoom z covers
    ``ceil(x_max - x_min)+1`` × ``ceil(y_max - y_min)+1`` tiles. We pick the
    largest z whose covering raster is ≤ 2× the requested pixel dimensions
    (so we get crisp output without fetching hundreds of tiles).
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    max_tiles_w = max(2, (pixel_w * 2) // 256 + 1)
    max_tiles_h = max(2, (pixel_h * 2) // 256 + 1)
    for z in range(18, -1, -1):
        x0, y1 = _lonlat_to_xy(min_lon, min_lat, z)  # bottom-left
        x1, y0 = _lonlat_to_xy(max_lon, max_lat, z)  # top-right (flipped y)
        tiles_w = math.ceil(x1) - math.floor(x0)
        tiles_h = math.ceil(y1) - math.floor(y0)
        if tiles_w <= max_tiles_w and tiles_h <= max_tiles_h:
            return z
    return 0


_TILE_BASEMAPS = {
    "carto-light": "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
    "carto-dark":  "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
    "osm":         "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
    "esri-natgeo": "https://server.arcgisonline.com/ArcGIS/rest/services/NatGeo_World_Map/MapServer/tile/{z}/{y}/{x}",
}


def _tile_cache_dir() -> Path:
    """Cache fetched tiles under ``data/tile_cache`` so repeat runs (and the
    live preview, which fires on every param edit) don't re-pull the same
    tile from the CDN. Tiles are immutable per (provider, z, x, y).
    """
    from dig.storage.files import data_dir as _data_dir
    return _data_dir() / "tile_cache"


def _fetch_tile(provider: str, z: int, x: int, y: int) -> bytes | None:
    """Return tile bytes — from cache when available, otherwise HTTP-fetched.

    Returns None on any failure (DNS, timeout, non-200, write error). The
    caller stitches what it has and the missing tile shows as a blank slot.
    """
    cache_dir = _tile_cache_dir() / provider / str(z) / str(x)
    cache_path = cache_dir / f"{y}.png"
    if cache_path.is_file():
        try:
            return cache_path.read_bytes()
        except OSError:
            pass

    url_tmpl = _TILE_BASEMAPS.get(provider) or _TILE_BASEMAPS["carto-light"]
    url = url_tmpl.format(z=z, x=x, y=y)
    import urllib.request
    import urllib.error
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "DataInsightGrove/1.0 (+https://github.com/SFCyris/DataInsightGrove)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            data = resp.read()
        cache_dir.mkdir(parents=True, exist_ok=True)
        # Round-4 QA-2 fix: write atomically. The previous direct
        # `cache_path.write_bytes(data)` left a half-written PNG on
        # disk if the worker was killed mid-write (or if two threads
        # wrote the same tile concurrently — common, since
        # _stitch_basemap launches up to 8 worker threads). The next
        # read returned a truncated file → PIL.UnidentifiedImageError
        # → blank tile until the cache file was manually deleted.
        # Write to a temp sibling + os.replace (atomic on POSIX +
        # Windows) so the cache only ever contains a complete file.
        tmp = cache_path.with_suffix(cache_path.suffix + f".tmp-{os.getpid()}")
        try:
            tmp.write_bytes(data)
            os.replace(tmp, cache_path)
        finally:
            # Clean up tmp if replace didn't run (e.g. write_bytes
            # raised). os.replace is atomic so the absence of the
            # tmp file after a successful call is expected.
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
        return data
    except (urllib.error.URLError, OSError, TimeoutError):
        return None


def _stitch_basemap(
    bbox: tuple[float, float, float, float],
    pixel_w: int,
    pixel_h: int,
    tile_provider: str,
):
    """Fetch + stitch slippy tiles into a PIL.Image at roughly pixel_w × pixel_h.

    Returns ``(image, extent)`` where ``extent = (left_lon, right_lon,
    bottom_lat, top_lat)`` matches matplotlib's imshow convention. Returns
    ``(None, bbox)`` if not a single tile could be fetched (offline /
    firewalled host) — caller falls back to graticule-only.
    """
    from PIL import Image
    from concurrent.futures import ThreadPoolExecutor

    z = _pick_zoom(bbox, pixel_w, pixel_h)
    min_lon, min_lat, max_lon, max_lat = bbox

    # Tile range covering the bbox at this zoom.
    x0_f, y1_f = _lonlat_to_xy(min_lon, min_lat, z)
    x1_f, y0_f = _lonlat_to_xy(max_lon, max_lat, z)
    x0, x1 = math.floor(x0_f), math.ceil(x1_f)
    y0, y1 = math.floor(y0_f), math.ceil(y1_f)
    n = 2 ** z
    # Clamp inside the tile grid (the bbox can reach the projection limit).
    x0 = max(0, x0); y0 = max(0, y0)
    x1 = min(n, x1); y1 = min(n, y1)

    coords = [
        (x % n, y) for x in range(x0, x1) for y in range(y0, y1) if 0 <= y < n
    ]
    # Bounded thread pool — most CDNs throttle hard past ~12 concurrent.
    fetched: dict[tuple[int, int], bytes] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(_fetch_tile, tile_provider, z, x, y): (x, y)
            for (x, y) in coords
        }
        for f in futures:
            xy = futures[f]
            try:
                data = f.result()
            except Exception:  # noqa: BLE001
                data = None
            if data is not None:
                fetched[xy] = data
    if not fetched:
        return (None, bbox)

    cols = x1 - x0
    rows = y1 - y0
    canvas = Image.new("RGBA", (cols * 256, rows * 256), (255, 255, 255, 255))
    import io
    for (x, y), data in fetched.items():
        try:
            tile_img = Image.open(io.BytesIO(data)).convert("RGBA")
        except Exception:  # noqa: BLE001
            continue
        canvas.paste(tile_img, ((x - x0) * 256, (y - y0) * 256))

    # Crop the stitched canvas down to the actual bbox (sub-tile precision).
    left_px   = int(round((x0_f - x0) * 256))
    right_px  = int(round((x1_f - x0) * 256))
    top_px    = int(round((y0_f - y0) * 256))
    bottom_px = int(round((y1_f - y0) * 256))
    cropped = canvas.crop((left_px, top_px, right_px, bottom_px))
    return (cropped, (min_lon, max_lon, min_lat, max_lat))


def _emit_png(
    points: list[dict[str, Any]],
    out_path: Path,
    title: str,
    width: int,
    height: int,
    marker_color: str,
    marker_radius: int,
    tile_provider: str = "carto-light",
    overlay_polygons: list[bytes] | None = None,
) -> None:
    """Render a static PNG with a real basemap behind the points.

    Steps:
      1. Auto-fit the bbox to the points (10% padding so markers aren't on
         the edge).
      2. Pick a zoom level + fetch + stitch slippy-map tiles into a PIL
         image. Tiles are cached on disk (data/tile_cache) so the live
         preview doesn't re-fetch on every param edit.
      3. Render the basemap as a matplotlib imshow underlay, then scatter
         the points on top.
      4. If tile fetching fails (no network, firewall), fall back to a
         clean graticule on the auto-fitted bbox.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    dpi = 144
    fig_w = max(width / dpi, 4.0)
    fig_h = max(height / dpi, 3.0)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)

    bbox = _bbox_with_padding(points, pad_frac=0.10)
    basemap, extent = _stitch_basemap(bbox, int(fig_w * dpi), int(fig_h * dpi), tile_provider)
    # extent is (lon_min, lon_max, lat_min, lat_max) in raw degrees, but
    # the stitched tiles are Web-Mercator projected. We re-project the
    # axes' y-axis into Mercator-y so polygon overlays + scatter points
    # land in the right pixel rows over the basemap (the choropleth PNG
    # renderer uses the identical trick).
    merc_extent = (
        extent[0], extent[1],
        _lat_to_merc_y(extent[2]), _lat_to_merc_y(extent[3]),
    ) if basemap is not None else extent

    if basemap is not None:
        ax.imshow(np.asarray(basemap), extent=merc_extent, aspect="auto", origin="upper", zorder=0)
    else:
        # Graticule-only fallback — softer than nothing, still recognisable.
        ax.set_facecolor("#eef2f7")
        for lon in range(-180, 181, 30):
            ax.axvline(lon, color="#cbd5e1", linewidth=0.4, zorder=0)
        for lat in range(-90, 91, 30):
            ax.axhline(lat, color="#cbd5e1", linewidth=0.4, zorder=0)

    # Overlay polygons (multi-layer): outlined fills drawn under the
    # markers but above the basemap. Uses the Mercator-projected drawer
    # when we have a basemap so the polygons align with the tiles.
    if overlay_polygons:
        if basemap is not None:
            _draw_polygons_on_axes_mercator(
                ax, overlay_polygons, edge_color="#374151",
                face_color=marker_color, face_alpha=0.10,
                line_width=0.8, zorder=1,
            )
        else:
            _draw_polygons_on_axes(
                ax, overlay_polygons, edge_color="#374151",
                face_color=marker_color, face_alpha=0.10,
                line_width=0.8, zorder=1,
            )

    if points:
        lats = np.array([p["lat"] for p in points])
        lons = np.array([p["lon"] for p in points])
        ys = np.array([_lat_to_merc_y(lat) for lat in lats]) if basemap is not None else lats
        ax.scatter(
            lons, ys,
            c=marker_color, s=max(8, marker_radius * 6), alpha=0.85,
            edgecolors="white", linewidths=0.8, zorder=2,
        )

    # Auto-fit axes to the bbox we picked (tiles are flush to the bbox edges).
    ax.set_xlim(bbox[0], bbox[2])
    if basemap is not None:
        ax.set_ylim(_lat_to_merc_y(bbox[1]), _lat_to_merc_y(bbox[3]))
        # Re-label the y-axis with real latitudes (project Mercator-y back
        # to degrees) so users see "37.8°" not "0.72" radians.
        import math as _m
        from matplotlib.ticker import FuncFormatter

        def _merc_y_to_lat(y, _pos=None) -> str:
            try:
                lat = _m.degrees(2 * _m.atan(_m.exp(y)) - _m.pi / 2)
                return f"{lat:.1f}"
            except (ValueError, OverflowError):
                return ""

        ax.yaxis.set_major_formatter(FuncFormatter(_merc_y_to_lat))
    else:
        ax.set_ylim(bbox[1], bbox[3])

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(title or "Map")
    ax.tick_params(labelsize=9)

    fig.tight_layout()
    fig.savefig(out_path, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)


# ---- Mode-specific extractors --------------------------------------------

def _coerce_geometry_value(g: Any) -> bytes | None:
    """Normalise a single geometry cell to WKB bytes.

    Accepts either raw WKB bytes (the canonical shape) or a WKT string —
    auto-detected from the type. This lets users plug in a CSV-loaded
    text column without first running a separate 'parse_geometry' step.
    None / blank / unparseable values return None so the caller can
    skip them.
    """
    if g is None:
        return None
    if isinstance(g, (bytes, bytearray)):
        return bytes(g)
    if isinstance(g, str):
        s = g.strip()
        if not s:
            return None
        try:
            from shapely import from_wkt, to_wkb
            return to_wkb(from_wkt(s))
        except Exception:  # noqa: BLE001 — parse failure → skip the row
            return None
    return None


def _extract_polygons(df: pl.DataFrame, geom_col: str) -> list[bytes]:
    """Pull WKB-bytes geometry blobs out of a polygon column. Skips
    None entries silently. WKT-string columns are auto-converted via
    `_coerce_geometry_value`."""
    if geom_col not in df.columns:
        return []
    out: list[bytes] = []
    for g in df.get_column(geom_col).to_list():
        wkb = _coerce_geometry_value(g)
        if wkb is not None:
            out.append(wkb)
    return out


def _extract_polygons_with_values(
    df: pl.DataFrame, geom_col: str | None, value_col: str | None,
) -> list[tuple[bytes, float | None]]:
    """For choropleth: paired (polygon WKB, numeric value)."""
    if not geom_col or geom_col not in df.columns:
        # Round-5 follow-up: give the user a complete picture instead of
        # just "geometry_col is required". Users who try choropleth on a
        # lat/lon dataset have nothing useful to pick in the column
        # dropdown — they need to know the data shape is wrong, not that
        # they forgot a click. Include the available columns + a
        # concrete recovery path.
        cols = ", ".join(df.columns[:12])
        more = f" (+{len(df.columns) - 12} more)" if len(df.columns) > 12 else ""
        raise ValueError(
            "export_to_map (choropleth): geometry_col is required — pick a "
            "column containing WKB-encoded polygons (typically produced by a "
            "'parse_geometry' step). If the upstream data has lat/lon points "
            "and no polygon shapes, switch the mode to 'points' or 'heat' "
            f"instead. Available columns: {cols}{more}.",
        )
    geoms = df.get_column(geom_col).to_list()
    if value_col and value_col in df.columns:
        vals = df.get_column(value_col).to_list()
    else:
        vals = [None] * len(geoms)
    out: list[tuple[bytes, float | None]] = []
    for g, v in zip(geoms, vals):
        # Round-5 follow-up: accept WKT strings AND WKB bytes by routing
        # every cell through _coerce_geometry_value. Unparseable cells
        # are silently dropped.
        wkb = _coerce_geometry_value(g)
        if wkb is None:
            continue
        try:
            out.append((wkb, float(v) if v is not None else None))
        except (TypeError, ValueError):
            out.append((wkb, None))
    return out


def _extract_arcs(
    df: pl.DataFrame,
    o_lat: str | None, o_lon: str | None,
    d_lat: str | None, d_lon: str | None,
) -> list[tuple[float, float, float, float]]:
    """For arc mode: (origin_lat, origin_lon, dest_lat, dest_lon) tuples,
    skipping rows with missing coords."""
    missing: list[str] = []
    bad_ref: list[str] = []
    for name, col in (("origin_lat_col", o_lat), ("origin_lon_col", o_lon),
                       ("dest_lat_col", d_lat), ("dest_lon_col", d_lon)):
        if not col:
            missing.append(name)
        elif col not in df.columns:
            bad_ref.append(f"{name}={col!r}")
    if missing or bad_ref:
        # Round-5 follow-up: same upgrade as the choropleth branch above.
        # Arc mode needs 4 separate columns (origin + destination
        # lat/lon). A dataset that only has a single location won't
        # support this; tell the user the requirement, the missing
        # fields, and a recovery path.
        cols = ", ".join(df.columns[:12])
        more = f" (+{len(df.columns) - 12} more)" if len(df.columns) > 12 else ""
        parts: list[str] = []
        if missing:
            parts.append(f"missing: {', '.join(missing)}")
        if bad_ref:
            parts.append(f"not in upstream: {', '.join(bad_ref)}")
        raise ValueError(
            "export_to_map (arc): " + " · ".join(parts) +
            " — arc mode draws origin → destination lines, so each row needs "
            "four lat/lon columns. If the data only has a single location, "
            "switch the mode to 'points' or 'heat' instead. Available "
            f"columns: {cols}{more}.",
        )
    olats = df.get_column(o_lat).to_list()
    olons = df.get_column(o_lon).to_list()
    dlats = df.get_column(d_lat).to_list()
    dlons = df.get_column(d_lon).to_list()
    out: list[tuple[float, float, float, float]] = []
    for ola, olo, dla, dlo in zip(olats, olons, dlats, dlons):
        if None in (ola, olo, dla, dlo):
            continue
        try:
            out.append((float(ola), float(olo), float(dla), float(dlo)))
        except (TypeError, ValueError):
            continue
    return out


# ---- Overlay helpers (used by both base modes + new modes) --------------

def _polygons_to_geojson(polys: list[bytes]) -> str:
    """Convert a list of WKB-bytes polygons to a GeoJSON FeatureCollection
    string. Used as the data payload for L.geoJSON in the HTML output."""
    from shapely import from_wkb
    features = []
    for blob in polys:
        try:
            geom = from_wkb(blob)
        except Exception:
            continue
        features.append({
            "type": "Feature",
            "properties": {},
            "geometry": json.loads(_geom_to_geojson_str(geom)),
        })
    return json.dumps({"type": "FeatureCollection", "features": features})


def _geom_to_geojson_str(geom) -> str:
    from shapely import to_geojson
    return to_geojson(geom)


def _draw_polygons_on_axes(
    ax,
    polys: list[bytes],
    color: str = "#374151",
    *,
    edge_color: str | None = None,
    face_color: str | None = None,
    face_alpha: float = 0.0,
    line_width: float = 1.2,
    zorder: float | None = None,
) -> None:
    """Draw polygons on a matplotlib axes (for PNG output).

    Defaults: outlined only (slate-700 edge, no fill) — matches the
    choropleth/heat overlay style. Pass ``face_color`` + ``face_alpha``
    to get a translucent fill (used by points-mode overlays to lightly
    tint the named zones the markers sit inside)."""
    if not polys:
        return
    from shapely import from_wkb
    from matplotlib.patches import Polygon as MplPolygon
    from matplotlib.collections import PatchCollection
    edge = edge_color or color
    patches = []
    for blob in polys:
        try:
            geom = from_wkb(blob)
        except Exception:
            continue
        # Handle both Polygon and MultiPolygon.
        geoms = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
        for g in geoms:
            if g.exterior is None:
                continue
            xy = list(g.exterior.coords)
            patches.append(MplPolygon(xy, closed=True))
    if patches:
        from matplotlib.colors import to_rgba
        if face_color and face_alpha > 0:
            face = to_rgba(face_color, face_alpha)
        else:
            face = "none"
        coll_kwargs: dict[str, Any] = {
            "facecolor": face,
            "edgecolor": edge,
            "linewidth": line_width,
        }
        if zorder is not None:
            coll_kwargs["zorder"] = zorder
        coll = PatchCollection(patches, **coll_kwargs)
        ax.add_collection(coll)


def _draw_polygons_on_axes_mercator(
    ax,
    polys: list[bytes],
    color: str = "#374151",
    *,
    edge_color: str | None = None,
    face_color: str | None = None,
    face_alpha: float = 0.0,
    line_width: float = 1.2,
    zorder: float | None = None,
) -> None:
    """Same as ``_draw_polygons_on_axes`` but projects every vertex's
    lat to Web Mercator y. Use this on axes whose y-extent is in
    Mercator space (the choropleth PNG renderer with basemap, and the
    points PNG renderer when an overlay is requested over a tiled
    basemap)."""
    if not polys:
        return
    from shapely import from_wkb
    from matplotlib.patches import Polygon as MplPolygon
    from matplotlib.collections import PatchCollection
    from matplotlib.colors import to_rgba
    edge = edge_color or color
    patches = []
    for blob in polys:
        try:
            geom = from_wkb(blob)
        except Exception:
            continue
        geoms = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
        for g in geoms:
            if g.exterior is None:
                continue
            xy = [(x, _lat_to_merc_y(y)) for x, y in g.exterior.coords]
            patches.append(MplPolygon(xy, closed=True))
    if patches:
        if face_color and face_alpha > 0:
            face = to_rgba(face_color, face_alpha)
        else:
            face = "none"
        coll_kwargs: dict[str, Any] = {
            "facecolor": face,
            "edgecolor": edge,
            "linewidth": line_width,
        }
        if zorder is not None:
            coll_kwargs["zorder"] = zorder
        coll = PatchCollection(patches, **coll_kwargs)
        ax.add_collection(coll)


def _color_scale_to_leaflet(scale: str) -> list[str]:
    """5-stop hex ramp for HTML choropleth / heat. Mirrors matplotlib
    sequential colormaps without requiring matplotlib to be loaded just
    to render HTML."""
    ramps = {
        "viridis": ["#440154", "#3b528b", "#21918c", "#5ec962", "#fde725"],
        "magma":   ["#000004", "#3b0f70", "#8c2981", "#de4968", "#fcfdbf"],
        "cividis": ["#00224e", "#395d9c", "#7c7b78", "#bcaa7e", "#fee838"],
        "plasma":  ["#0d0887", "#7e03a8", "#cc4778", "#f89540", "#f0f921"],
        "Greens":  ["#f7fcf5", "#c7e9c0", "#74c476", "#238b45", "#00441b"],
        "Blues":   ["#f7fbff", "#c6dbef", "#6baed6", "#2171b5", "#08306b"],
        "Reds":    ["#fff5f0", "#fcbba1", "#fb6a4a", "#cb181d", "#67000d"],
        "OrRd":    ["#fff7ec", "#fdd49e", "#fc8d59", "#d7301f", "#7f0000"],
        "YlGnBu":  ["#ffffd9", "#c7e9b4", "#41b6c4", "#225ea8", "#081d58"],
    }
    return ramps.get(scale, ramps["viridis"])


# ---- Choropleth ---------------------------------------------------------

def _emit_html_choropleth(
    polygons_with_values: list[tuple[bytes, float | None]],
    title: str, width: int, height: int, color_scale: str, tile_provider: str,
    overlay_polygons: list[bytes] | None = None,
    graduate_below_px: int = 6,
) -> str:
    """Color-coded polygon map.

    The polygon's value column drives the fill color via a 5-stop
    sequential ramp; missing values render grey. All data embedded
    inline.

    Dot-proxy: features whose pixel bbox at the current zoom would be
    smaller than ``graduate_below_px`` are drawn as same-colored dots
    at their centroid. The substitution re-evaluates on every zoom
    change — zooming in past the threshold restores the polygon.
    Tooltip content is shared between polygon and dot form, so the
    user sees the same hover text either way.
    """
    from shapely import from_wkb, to_geojson
    features = []
    values = [v for _, v in polygons_with_values if v is not None]
    vmin = min(values) if values else 0.0
    vmax = max(values) if values else 1.0
    for blob, v in polygons_with_values:
        try:
            geom = from_wkb(blob)
            geo = json.loads(to_geojson(geom))
        except Exception:
            continue
        features.append({
            "type": "Feature",
            "properties": {"value": v},
            "geometry": geo,
        })
    payload = {
        "type": "FeatureCollection",
        "features": features,
        "vmin": vmin, "vmax": vmax,
        "ramp": _color_scale_to_leaflet(color_scale),
        "graduateBelowPx": int(graduate_below_px),
    }
    safe = json.dumps(payload).replace("</", "<\\/")
    overlay_geojson = (
        _polygons_to_geojson(overlay_polygons or [])
        .replace("</", "<\\/")
    )
    tile_url = _TILE_BASEMAPS.get(tile_provider, _TILE_BASEMAPS["carto-light"])
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{_escape(title)}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>html,body,#m{{height:100%;width:100%;margin:0;padding:0}}.legend{{background:white;padding:6px 10px;border-radius:4px;box-shadow:0 1px 3px rgba(0,0,0,.2);font:12px system-ui}}</style>
</head><body><div id="m"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const data = {safe};
const overlayData = {overlay_geojson};
const map = L.map('m');
L.tileLayer('{tile_url}', {{maxZoom:18, attribution:'© OpenStreetMap contributors'}}).addTo(map);
function colorFor(v) {{
  if (v === null || v === undefined) return '#cccccc';
  const t = Math.max(0, Math.min(1, (v - data.vmin) / Math.max(1e-9, data.vmax - data.vmin)));
  const idx = Math.min(data.ramp.length - 1, Math.floor(t * data.ramp.length));
  return data.ramp[idx];
}}
function tooltipHtml(v) {{
  if (v === null || v === undefined) return '<i>no value</i>';
  return 'value: ' + (typeof v === 'number' ? v.toLocaleString() : v);
}}
const layer = L.geoJSON(data, {{
  style: f => ({{ fillColor: colorFor(f.properties.value), weight: 1, color: '#374151', fillOpacity: 0.7 }}),
  onEachFeature: (f, l) => l.bindTooltip(tooltipHtml(f.properties.value))
}}).addTo(map);
if (overlayData.features && overlayData.features.length) {{
  L.geoJSON(overlayData, {{ style: {{ fillOpacity: 0, color: '#374151', weight: 1.2 }} }}).addTo(map);
}}

// ---- Dot-proxy for sub-pixel features ----
// At low zoom, microstates render below 1 pixel and effectively
// disappear from the choropleth. We compute each feature's pixel bbox
// at the current zoom, hide polygons that would render below
// `graduateBelowPx`, and place a same-colored dot at their centroid
// instead. Re-evaluates on every zoom — zooming in past the threshold
// restores the real polygon. Disabled when graduateBelowPx === 0.
const proxyMarkers = new Map();   // feature layer-id → L.circleMarker
function updateDotProxy() {{
  if (!data.graduateBelowPx || data.graduateBelowPx <= 0) return;
  const z = map.getZoom();
  layer.eachLayer(featureLayer => {{
    const lid = layer.getLayerId(featureLayer);
    const bounds = featureLayer.getBounds && featureLayer.getBounds();
    if (!bounds || !bounds.isValid()) return;
    const nw = map.project(bounds.getNorthWest(), z);
    const se = map.project(bounds.getSouthEast(), z);
    const pxDiag = Math.hypot(se.x - nw.x, se.y - nw.y);
    const value = featureLayer.feature.properties.value;
    if (pxDiag < data.graduateBelowPx) {{
      // Hide polygon (transparent stroke + fill, keep layer interactive
      // for tooltip access fallback) and ensure a marker exists.
      featureLayer.setStyle({{ opacity: 0, fillOpacity: 0 }});
      if (!proxyMarkers.has(lid)) {{
        const centroid = bounds.getCenter();
        const marker = L.circleMarker(centroid, {{
          radius: Math.max(3, Math.round(data.graduateBelowPx * 0.55)),
          fillColor: colorFor(value),
          color: '#374151', weight: 1, fillOpacity: 0.95,
        }}).addTo(map);
        marker.bindTooltip(tooltipHtml(value));
        proxyMarkers.set(lid, marker);
      }}
    }} else {{
      // Show polygon, remove marker if present.
      featureLayer.setStyle({{
        opacity: 1, weight: 1, color: '#374151', fillOpacity: 0.7,
        fillColor: colorFor(value),
      }});
      if (proxyMarkers.has(lid)) {{
        map.removeLayer(proxyMarkers.get(lid));
        proxyMarkers.delete(lid);
      }}
    }}
  }});
}}
map.on('zoomend', updateDotProxy);

// Initial viewport: honour parent-seeded view (preview iframe restoring
// pan/zoom across param edits), otherwise auto-fit. After the viewport
// is set, run updateDotProxy once so dot/polygon state matches the
// initial zoom level.
if (window.__DIG_INITIAL_VIEW__) {{
  const v = window.__DIG_INITIAL_VIEW__;
  map.setView([v.lat, v.lng], v.zoom);
}} else {{
  const b = layer.getBounds();
  if (b.isValid()) map.fitBounds(b, {{padding:[20,20]}});
  else map.setView([20, 0], 2);
}}
updateDotProxy();
const lg = L.control({{position:'bottomright'}});
lg.onAdd = () => {{
  const d = L.DomUtil.create('div','legend');
  let html = '<b>{_escape(title)}</b><br/>min: ' + data.vmin.toFixed(2) +
             ' &nbsp; max: ' + data.vmax.toFixed(2);
  if (data.graduateBelowPx > 0) {{
    html += '<br/><span style="font-size:10px;color:#6b7280;">Small regions shown as dots at low zoom</span>';
  }}
  d.innerHTML = html;
  return d;
}};
lg.addTo(map);
// Push viewport changes back to the parent (preview iframe host) so it
// can restore them on the next srcDoc swap. Standalone exports — where
// there's no listening parent — silently no-op.
function _digPostViewport() {{
  if (window.parent === window) return;
  const c = map.getCenter();
  try {{
    window.parent.postMessage({{
      type: 'dig:map:viewport', lat: c.lat, lng: c.lng, zoom: map.getZoom(),
    }}, '*');
  }} catch (e) {{ /* sandboxed cross-origin — ignore */ }}
}}
map.on('moveend', _digPostViewport);
map.on('zoomend', _digPostViewport);
</script></body></html>"""


def _lat_to_merc_y(lat: float) -> float:
    """Project WGS84 latitude (degrees) to Web Mercator Y in radians.

    The slippy-map tiles served by every common provider (OSM, Carto,
    Stamen, etc.) are in Web Mercator (EPSG:3857). Tile pixels are
    LINEAR in Mercator-y, NOT linear in latitude — a one-pixel step is
    a larger lat-delta near the equator than near the poles. When we
    drop the stitched tile image into matplotlib via ``imshow``, we
    have two choices: either re-warp the image to plate carrée
    (expensive + lossy), or project our polygons into the same
    Mercator-y space the image is already in. We do the latter.

    Returns the projection in radians (matplotlib's axis scale is
    arbitrary so the absolute unit doesn't matter — what matters is
    that the polygons AND the extent use the same projection so they
    land on the same pixels).
    """
    import math as _math
    # Clamp to Web Mercator's valid range; outside this latitudes go to
    # ±infinity which would break the extent calculation.
    lat = max(-85.05112878, min(85.05112878, lat))
    return _math.log(_math.tan(_math.pi / 4 + _math.radians(lat) / 2))


def _emit_png_choropleth(
    polygons_with_values: list[tuple[bytes, float | None]],
    out_path: Path, title: str, width: int, height: int,
    color_scale: str, tile_provider: str,
    overlay_polygons: list[bytes] | None = None,
    graduate_below_px: int = 6,
) -> None:
    """Static PNG choropleth via matplotlib.

    Renders the slippy-map basemap as an imshow underlay (matching the
    points-mode renderer + the HTML choropleth's Leaflet tile layer)
    and overlays the filled polygons on top with the chosen sequential
    colormap. Bbox auto-fits the polygon extents.

    Projection: every polygon's lat coordinates are projected into
    Web Mercator y so they align with the tile image (which is
    natively in EPSG:3857). Without this, polygons drawn at high
    latitudes drift north relative to their basemap counterparts —
    e.g. Washington state lands ~1° north of its actual outline.

    Dot-proxy: when a feature's bbox would render below
    ``graduate_below_px`` pixels on screen, we draw a same-colored
    dot at its centroid instead of the polygon. Standard cartographic
    technique for sub-pixel features (microstates, tiny ZCTAs). Set
    ``graduate_below_px=0`` to disable.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.cm as cm
    from matplotlib.patches import Polygon as MplPolygon
    from matplotlib.collections import PatchCollection
    import numpy as np
    from shapely import from_wkb

    dpi = 144
    fig_w = max(width / dpi, 4.0)
    fig_h = max(height / dpi, 3.0)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
    if not polygons_with_values:
        ax.text(0.5, 0.5, "(no polygons)", ha="center", va="center")
        fig.savefig(out_path, bbox_inches="tight")
        plt.close(fig)
        return

    # Per-FEATURE accounting (one row per upstream WKB blob, even when
    # the blob is a MultiPolygon). Lets us decide dot-proxy on the
    # feature's combined bbox, not per polygon part. Per-feature lat
    # span is also computed from the underlying geometry directly,
    # NOT the post-projection patch, so the threshold reasoning stays
    # in geographic units.
    feature_patches: list[list[MplPolygon]] = []   # list of patches per feature
    feature_values: list[float] = []
    feature_bbox_lon_span: list[float] = []        # in degrees
    feature_bbox_lat_span: list[float] = []        # in degrees
    feature_centroid_lon: list[float] = []
    feature_centroid_lat: list[float] = []
    bbox = [float("inf"), float("inf"), float("-inf"), float("-inf")]
    for blob, v in polygons_with_values:
        try:
            geom = from_wkb(blob)
        except Exception:
            continue
        feat_patches: list[MplPolygon] = []
        feat_bbox = [float("inf"), float("inf"), float("-inf"), float("-inf")]
        geoms = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
        for g in geoms:
            if g.exterior is None:
                continue
            xy = [(x, _lat_to_merc_y(y)) for x, y in g.exterior.coords]
            feat_patches.append(MplPolygon(xy, closed=True))
            minx, miny, maxx, maxy = g.bounds
            feat_bbox[0] = min(feat_bbox[0], minx); feat_bbox[1] = min(feat_bbox[1], miny)
            feat_bbox[2] = max(feat_bbox[2], maxx); feat_bbox[3] = max(feat_bbox[3], maxy)
        if not feat_patches:
            continue
        feature_patches.append(feat_patches)
        feature_values.append(v if v is not None else float("nan"))
        feature_bbox_lon_span.append(feat_bbox[2] - feat_bbox[0])
        feature_bbox_lat_span.append(feat_bbox[3] - feat_bbox[1])
        feature_centroid_lon.append((feat_bbox[0] + feat_bbox[2]) / 2.0)
        feature_centroid_lat.append((feat_bbox[1] + feat_bbox[3]) / 2.0)
        bbox[0] = min(bbox[0], feat_bbox[0]); bbox[1] = min(bbox[1], feat_bbox[1])
        bbox[2] = max(bbox[2], feat_bbox[2]); bbox[3] = max(bbox[3], feat_bbox[3])

    # Pad the bbox by 4% — tight enough that polygons fill the frame
    # (matches the Leaflet HTML's fitBounds padding=[20,20]) without
    # leaving distracting whitespace at the edges.
    if bbox[0] != float("inf"):
        span_lon = max(0.5, (bbox[2] - bbox[0]))
        span_lat = max(0.5, (bbox[3] - bbox[1]))
        padded = (
            bbox[0] - span_lon * 0.04,
            bbox[1] - span_lat * 0.04,
            bbox[2] + span_lon * 0.04,
            bbox[3] + span_lat * 0.04,
        )
    else:
        padded = (-180.0, -85.0, 180.0, 85.0)

    # Stitch the basemap underlay BEFORE the polygons so it sits at
    # zorder 0. _stitch_basemap returns (PIL image, extent_latlon) or
    # (None, bbox) if the network fetch fails.
    basemap, extent_latlon = _stitch_basemap(
        padded, int(fig_w * dpi), int(fig_h * dpi), tile_provider,
    )
    if basemap is not None:
        # Re-project the extent's y bounds to Web Mercator so the
        # image's pixel rows (which are linear in Mercator y) map
        # correctly to our axes. The x bounds pass through — Mercator
        # is identity in longitude.
        left_lon, right_lon, bottom_lat, top_lat = extent_latlon
        merc_extent = (
            left_lon, right_lon,
            _lat_to_merc_y(bottom_lat), _lat_to_merc_y(top_lat),
        )
        ax.imshow(np.asarray(basemap), extent=merc_extent, aspect="auto", origin="upper", zorder=0)
    else:
        ax.set_facecolor("#eef2f7")
        for lon in range(-180, 181, 30):
            ax.axvline(lon, color="#cbd5e1", linewidth=0.4, zorder=0)
        for lat in range(-90, 91, 30):
            ax.axhline(_lat_to_merc_y(lat), color="#cbd5e1", linewidth=0.4, zorder=0)

    cmap = cm.get_cmap(color_scale)
    arr = np.array(feature_values, dtype=float)
    valid = ~np.isnan(arr)
    if valid.any():
        vmin, vmax = float(np.nanmin(arr)), float(np.nanmax(arr))
        norm = matplotlib.colors.Normalize(vmin=vmin, vmax=vmax)
    else:
        norm = matplotlib.colors.Normalize(vmin=0, vmax=1)

    # Compute pixels-per-degree at the render resolution. Used to
    # decide which features fall below the dot-proxy threshold.
    px_per_deg_lon = (fig_w * dpi) / max(1e-6, (padded[2] - padded[0]))
    # Lat is non-linear (Mercator), so we approximate using the mid-
    # latitude's local px-per-degree. Good enough for the threshold
    # check; the actual rendering uses the projected y throughout.
    mid_merc_span = _lat_to_merc_y(padded[3]) - _lat_to_merc_y(padded[1])
    px_per_merc_unit = (fig_h * dpi) / max(1e-6, mid_merc_span)
    # Convert each feature's geographic bbox into a pixel bbox.
    polygon_patches: list[MplPolygon] = []
    polygon_values: list[float] = []
    dot_x: list[float] = []
    dot_y: list[float] = []
    dot_values: list[float] = []
    dot_count = 0
    for i, patches in enumerate(feature_patches):
        # Pixel size at this zoom: lon → px directly; lat → use the
        # Mercator-y delta covered by the feature's lat bbox.
        merc_top = _lat_to_merc_y(feature_centroid_lat[i] + feature_bbox_lat_span[i] / 2)
        merc_bot = _lat_to_merc_y(feature_centroid_lat[i] - feature_bbox_lat_span[i] / 2)
        px_w = feature_bbox_lon_span[i] * px_per_deg_lon
        px_h = abs(merc_top - merc_bot) * px_per_merc_unit
        # Diagonal — single threshold against the feature's larger
        # screen extent. A thin tall sliver might pass even at low px_w.
        px_diag = (px_w ** 2 + px_h ** 2) ** 0.5
        if graduate_below_px > 0 and px_diag < graduate_below_px:
            dot_x.append(feature_centroid_lon[i])
            dot_y.append(_lat_to_merc_y(feature_centroid_lat[i]))
            dot_values.append(feature_values[i])
            dot_count += 1
        else:
            polygon_patches.extend(patches)
            polygon_values.extend([feature_values[i]] * len(patches))

    # Draw the polygon features as before.
    if polygon_patches:
        poly_arr = np.array(polygon_values, dtype=float)
        coll = PatchCollection(
            polygon_patches, cmap=cmap, edgecolor="#374151", linewidth=0.75, alpha=0.85,
        )
        coll.set_array(poly_arr)
        coll.set_norm(norm)
        coll.set_zorder(2)
        ax.add_collection(coll)
        cbar_source = coll
    else:
        cbar_source = None

    # Dot-proxies for sub-pixel features. Same colormap + norm so the
    # encoding stays uniform across polygon + dot features.
    if dot_x:
        # Render dots slightly larger than the threshold so they're
        # clearly visible (the threshold is a "below this you can't see
        # the polygon"; the dot needs to actually register on screen).
        dot_marker_size = max(graduate_below_px, 6) ** 2  # matplotlib `s` is area in pt^2
        dot_arr = np.array(dot_values, dtype=float)
        # Filter out NaN values so cmap doesn't crash; render those as
        # neutral grey for honesty.
        dot_arr_safe = np.where(np.isnan(dot_arr), vmin if valid.any() else 0, dot_arr)
        sc = ax.scatter(
            dot_x, dot_y, c=dot_arr_safe, cmap=cmap, norm=norm,
            s=dot_marker_size, edgecolor="#374151", linewidths=0.75,
            alpha=0.95, zorder=3,
        )
        if cbar_source is None:
            cbar_source = sc

    # Overlay polygons (zone outlines etc.) are also in lat/lon and must
    # be re-projected to Mercator y before drawing — otherwise they
    # would land at the wrong vertical position relative to the basemap
    # while the choropleth polygons land correctly.
    _draw_polygons_on_axes_mercator(ax, overlay_polygons or [])
    ax.set_xlim(padded[0], padded[2])
    ax.set_ylim(_lat_to_merc_y(padded[1]), _lat_to_merc_y(padded[3]))
    ax.set_title(title or "Map", fontsize=12, pad=8)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.grid(False)
    if valid.any() and cbar_source is not None:
        cbar = fig.colorbar(cbar_source, ax=ax, shrink=0.7, pad=0.02)
        cbar.outline.set_visible(False)
    # Caption: when dot-proxies were used, note it so the reader knows
    # the small dots are real data, not decoration.
    if dot_count > 0:
        fig.text(
            0.99, 0.01,
            f"{dot_count} small {'region' if dot_count == 1 else 'regions'} "
            "shown as dots",
            ha="right", va="bottom",
            fontsize=8, color="#6b7280", style="italic",
        )
    fig.tight_layout()
    fig.savefig(out_path, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)


# ---- Heat-on-map --------------------------------------------------------

def _emit_html_heat(
    points: list[dict[str, Any]],
    title: str, width: int, height: int, color_scale: str, tile_provider: str,
    overlay_polygons: list[bytes] | None = None,
) -> str:
    """Kernel-density heat overlay via leaflet.heat plugin (CDN-loaded)."""
    pts_payload = [[p["lat"], p["lon"], 1] for p in points if "lat" in p and "lon" in p]
    safe = json.dumps(pts_payload).replace("</", "<\\/")
    overlay_geojson = (
        _polygons_to_geojson(overlay_polygons or [])
        .replace("</", "<\\/")
    )
    tile_url = _TILE_BASEMAPS.get(tile_provider, _TILE_BASEMAPS["carto-light"])
    ramp = _color_scale_to_leaflet(color_scale)
    grad_obj = {f"{i / (len(ramp) - 1):.2f}": c for i, c in enumerate(ramp)}
    grad_json = json.dumps(grad_obj)
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{_escape(title)}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>html,body,#m{{height:100%;width:100%;margin:0;padding:0}}</style>
</head><body><div id="m"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js"></script>
<script>
const pts = {safe};
const overlayData = {overlay_geojson};
const map = L.map('m');
L.tileLayer('{tile_url}', {{maxZoom:18, attribution:'© OpenStreetMap contributors'}}).addTo(map);
const heat = L.heatLayer(pts, {{ radius: 25, blur: 15, gradient: {grad_json} }}).addTo(map);
if (overlayData.features && overlayData.features.length) {{
  L.geoJSON(overlayData, {{ style: {{ fillOpacity: 0, color: '#374151', weight: 1.2 }} }}).addTo(map);
}}
if (window.__DIG_INITIAL_VIEW__) {{
  const v = window.__DIG_INITIAL_VIEW__;
  map.setView([v.lat, v.lng], v.zoom);
}} else if (pts.length) {{
  const lats = pts.map(p => p[0]); const lons = pts.map(p => p[1]);
  map.fitBounds([[Math.min(...lats), Math.min(...lons)], [Math.max(...lats), Math.max(...lons)]], {{padding:[20,20]}});
}} else {{ map.setView([20, 0], 2); }}
function _digPostViewport() {{
  if (window.parent === window) return;
  const c = map.getCenter();
  try {{
    window.parent.postMessage({{
      type: 'dig:map:viewport', lat: c.lat, lng: c.lng, zoom: map.getZoom(),
    }}, '*');
  }} catch (e) {{}}
}}
map.on('moveend', _digPostViewport);
map.on('zoomend', _digPostViewport);
</script></body></html>"""


def _emit_png_heat(
    points: list[dict[str, Any]],
    out_path: Path, title: str, width: int, height: int,
    color_scale: str, tile_provider: str,
    overlay_polygons: list[bytes] | None = None,
) -> None:
    """Static PNG heatmap via 2D histogram."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
    lats = [p["lat"] for p in points if "lat" in p and "lon" in p]
    lons = [p["lon"] for p in points if "lon" in p and "lat" in p]
    if not lats:
        ax.text(0.5, 0.5, "(no points)", ha="center", va="center")
        fig.savefig(out_path, bbox_inches="tight")
        plt.close(fig)
        return
    h, xe, ye = np.histogram2d(lons, lats, bins=80)
    img = ax.imshow(h.T, origin="lower", extent=(xe[0], xe[-1], ye[0], ye[-1]),
                    cmap=color_scale, aspect="equal", alpha=0.85)
    _draw_polygons_on_axes(ax, overlay_polygons or [])
    fig.colorbar(img, ax=ax, shrink=0.7, label="density")
    ax.set_title(title); ax.set_xlabel("longitude"); ax.set_ylabel("latitude")
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


# ---- Arc / origin-destination -------------------------------------------

def _emit_html_arc(
    arcs: list[tuple[float, float, float, float]],
    title: str, width: int, height: int, line_color: str, tile_provider: str,
    overlay_polygons: list[bytes] | None = None,
) -> str:
    """Origin → destination polylines via Leaflet."""
    safe = json.dumps(arcs).replace("</", "<\\/")
    overlay_geojson = (
        _polygons_to_geojson(overlay_polygons or [])
        .replace("</", "<\\/")
    )
    tile_url = _TILE_BASEMAPS.get(tile_provider, _TILE_BASEMAPS["carto-light"])
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{_escape(title)}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>html,body,#m{{height:100%;width:100%;margin:0;padding:0}}</style>
</head><body><div id="m"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const arcs = {safe};
const overlayData = {overlay_geojson};
const map = L.map('m');
L.tileLayer('{tile_url}', {{maxZoom:18, attribution:'© OpenStreetMap contributors'}}).addTo(map);
const allLats = []; const allLons = [];
arcs.forEach(([oLa, oLo, dLa, dLo]) => {{
  L.polyline([[oLa, oLo], [dLa, dLo]], {{color: '{line_color}', weight: 1.5, opacity: 0.6}}).addTo(map);
  L.circleMarker([oLa, oLo], {{radius: 3, color: '{line_color}', fillOpacity: 0.8}}).addTo(map);
  L.circleMarker([dLa, dLo], {{radius: 4, color: '#374151', fillOpacity: 0.8}}).addTo(map);
  allLats.push(oLa, dLa); allLons.push(oLo, dLo);
}});
if (overlayData.features && overlayData.features.length) {{
  L.geoJSON(overlayData, {{ style: {{ fillOpacity: 0, color: '#374151', weight: 1.2 }} }}).addTo(map);
}}
if (allLats.length) {{
  map.fitBounds([[Math.min(...allLats), Math.min(...allLons)], [Math.max(...allLats), Math.max(...allLons)]], {{padding:[20,20]}});
}} else {{ map.setView([20, 0], 2); }}
</script></body></html>"""


def _emit_png_arc(
    arcs: list[tuple[float, float, float, float]],
    out_path: Path, title: str, width: int, height: int,
    line_color: str, tile_provider: str,
    overlay_polygons: list[bytes] | None = None,
) -> None:
    """Static PNG arcs — straight lines (great-circle interpolation
    would need geographiclib; straight-line is the conventional
    map-projection compromise for static images)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
    if not arcs:
        ax.text(0.5, 0.5, "(no arcs)", ha="center", va="center")
        fig.savefig(out_path, bbox_inches="tight")
        plt.close(fig)
        return
    lats: list[float] = []; lons: list[float] = []
    for ola, olo, dla, dlo in arcs:
        ax.plot([olo, dlo], [ola, dla], color=line_color, alpha=0.5, linewidth=0.8)
        ax.scatter([olo], [ola], c=line_color, s=8, alpha=0.8)
        ax.scatter([dlo], [dla], c="#374151", s=12, alpha=0.8)
        lats.extend([ola, dla]); lons.extend([olo, dlo])
    _draw_polygons_on_axes(ax, overlay_polygons or [])
    pad_x = max(0.5, (max(lons) - min(lons)) * 0.05)
    pad_y = max(0.5, (max(lats) - min(lats)) * 0.05)
    ax.set_xlim(min(lons) - pad_x, max(lons) + pad_x)
    ax.set_ylim(min(lats) - pad_y, max(lats) + pad_y)
    ax.set_aspect("equal")
    ax.set_title(title); ax.set_xlabel("longitude"); ax.set_ylabel("latitude")
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


# ---- Step ---------------------------------------------------------------

class ExportToMapStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]

        mode = (params.get("mode") or "points").lower()
        if mode not in ("points", "choropleth", "heat", "arc"):
            raise ValueError(f"export_to_map: unknown mode '{mode}'")

        fmt = (params.get("format") or "lat_lon").lower()
        if fmt not in ("lat_lon", "lon_lat", "wkt_point", "separate_columns"):
            raise ValueError(f"export_to_map: unknown format '{fmt}'")

        location = (params.get("location") or "").strip() or None
        lat_col = (params.get("lat_col") or "").strip() or None
        lon_col = (params.get("lon_col") or "").strip() or None
        name_col = (params.get("name_col") or "").strip() or None
        comment_col = (params.get("comment_col") or "").strip() or None
        # New mode-specific column refs.
        geometry_col = (params.get("geometry_col") or "").strip() or None
        value_col = (params.get("value_col") or "").strip() or None
        origin_lat_col = (params.get("origin_lat_col") or "").strip() or None
        origin_lon_col = (params.get("origin_lon_col") or "").strip() or None
        dest_lat_col = (params.get("dest_lat_col") or "").strip() or None
        dest_lon_col = (params.get("dest_lon_col") or "").strip() or None
        color_scale = (params.get("color_scale") or "viridis").strip()
        overlay_polygon_col = (params.get("overlay_polygon_col") or "").strip() or None
        # Choropleth-only: pixel threshold below which a polygon is
        # drawn as a same-colored dot at its centroid instead. Cartographic
        # technique to surface sub-pixel features (microstates, tiny ZCTAs)
        # at world zoom. 0 disables.
        graduate_below_px = max(0, int(params.get("graduate_below_px") or 6))

        max_points = int(params.get("max_points") or 20_000)
        sample_df = df
        if df.height > max_points:
            sample_df = df.sample(n=max_points, seed=42)

        # Per-mode data extraction. Points mode reuses the original
        # _extract_points helper. Other modes build their own payloads
        # below before rendering.
        points = _extract_points(
            sample_df, fmt, location, lat_col, lon_col, name_col, comment_col,
        ) if mode in ("points", "heat") else []

        # Polygon-overlay layer — shared across every base mode. Built
        # once so each renderer can draw it on top.
        overlay_polygons = (
            _extract_polygons(sample_df, overlay_polygon_col)
            if overlay_polygon_col else []
        )

        title = params.get("title") or self.id
        format_out = (params.get("format_out") or "html").lower()
        if format_out not in ("html", "png"):
            raise ValueError(f"export_to_map: format_out must be 'html' or 'png', got '{format_out}'")

        width = int(params.get("width") or 1200)
        height = int(params.get("height") or 800)
        # Round-2 SEC: validate against the CSS-color allow-list — anything
        # else falls back to the DIG default rather than reaching the
        # raw-f-string interpolation in the HTML emit functions. Both the
        # marker (points/heat) AND line (arc) emit paths call this same
        # variable, so one gate locks both.
        marker_color = _validate_css_color(
            params.get("marker_color"), fallback="#10b981",
        )
        marker_radius = int(params.get("marker_radius") or 6)
        tile_provider = (params.get("tile_provider") or "carto-light").lower()

        # Output paths — write whichever format the user asked for as the
        # primary, but always also write the secondary so callers (preview,
        # external embed) can pick. The primary is what the editor's preview
        # endpoint serves.
        #
        # Filename uses ``ctx.node_id`` (the per-pipeline DAG identifier),
        # NOT ``self.id`` (the step-class id, shared across every
        # ``export_to_map`` node). Two map nodes in the same pipeline used
        # to silently overwrite each other's HTML/PNG when the filename
        # was ``f"{self.id}.{fmt}"``. Falls back to ``self.id`` only when
        # there is no ctx (unit-test usage).
        path_param = (params.get("path") or "").strip()
        if path_param:
            primary_path = Path(path_param).expanduser()
            if not primary_path.is_absolute() and ctx is not None:
                primary_path = ctx.out_dir / primary_path
        else:
            base = ctx.out_dir if ctx is not None else Path.cwd()
            stem = (ctx.node_id if ctx is not None and ctx.node_id else self.id)
            primary_path = base / f"{stem}.{format_out}"
        if primary_path.suffix == "":
            primary_path = primary_path.with_suffix(f".{format_out}")
        primary_path = primary_path.resolve()
        # Path scoping — see export_to_image for the rationale (a malicious
        # ``path`` could otherwise write attacker-controlled HTML/PNG bytes
        # anywhere the backend can reach).
        import os as _os
        if ctx is not None and _os.environ.get("DIG_EXPORT_ALLOW_ABSOLUTE") != "1":
            base_resolved = Path(ctx.out_dir).resolve()
            try:
                primary_path.relative_to(base_resolved)
            except ValueError as e:
                raise ValueError(
                    f"export_to_map: refusing to write outside the run output "
                    f"directory (got {primary_path}). Set DIG_EXPORT_ALLOW_ABSOLUTE=1 "
                    f"to override on a trusted host."
                ) from e
        primary_path.parent.mkdir(parents=True, exist_ok=True)

        # Build secondary path (the "other" format) alongside the primary.
        secondary_format = "png" if format_out == "html" else "html"
        secondary_path = primary_path.with_suffix(f".{secondary_format}")

        # Per-mode HTML + PNG rendering. Each renderer accepts the
        # extracted-once overlay_polygons list so the multi-layer case
        # (e.g. markers over named zones) works uniformly across modes.
        if mode == "points":
            html_content = _emit_html(
                points, title, width, height, marker_color, marker_radius, tile_provider,
                overlay_polygons=overlay_polygons,
            )
            png_render = lambda path: _emit_png(
                points, path, title, width, height,
                marker_color, marker_radius, tile_provider,
                overlay_polygons=overlay_polygons,
            )
        elif mode == "choropleth":
            polygons_with_values = _extract_polygons_with_values(
                sample_df, geometry_col, value_col,
            )
            html_content = _emit_html_choropleth(
                polygons_with_values, title, width, height, color_scale, tile_provider,
                overlay_polygons=overlay_polygons,
                graduate_below_px=graduate_below_px,
            )
            png_render = lambda path: _emit_png_choropleth(
                polygons_with_values, path, title, width, height, color_scale, tile_provider,
                overlay_polygons=overlay_polygons,
                graduate_below_px=graduate_below_px,
            )
        elif mode == "heat":
            html_content = _emit_html_heat(
                points, title, width, height, color_scale, tile_provider,
                overlay_polygons=overlay_polygons,
            )
            png_render = lambda path: _emit_png_heat(
                points, path, title, width, height, color_scale, tile_provider,
                overlay_polygons=overlay_polygons,
            )
        elif mode == "arc":
            arcs = _extract_arcs(
                sample_df, origin_lat_col, origin_lon_col, dest_lat_col, dest_lon_col,
            )
            html_content = _emit_html_arc(
                arcs, title, width, height, marker_color, tile_provider,
                overlay_polygons=overlay_polygons,
            )
            png_render = lambda path: _emit_png_arc(
                arcs, path, title, width, height, marker_color, tile_provider,
                overlay_polygons=overlay_polygons,
            )
        else:
            raise ValueError(f"export_to_map: unknown mode '{mode}'")

        if format_out == "html":
            primary_path.write_text(html_content, encoding="utf-8")
            png_render(secondary_path)
        else:
            secondary_path.write_text(html_content, encoding="utf-8")
            png_render(primary_path)

        # Artifact list — primary first so preview-step (which serves the
        # first 'image' artifact) returns the requested format. The
        # secondary is still surfaced in the run record so the user can
        # download both from the artifacts panel.
        artifacts: list[dict[str, Any]] = [
            {
                "kind": "image",
                "format": format_out,
                "path": str(primary_path),
                "width": width,
                "height": height,
                "chart": "map",
                "rows_plotted": len(points),
                "title": title,
                "marker_color": marker_color,
                "tile_provider": tile_provider,
            },
            {
                "kind": "image",
                "format": secondary_format,
                "path": str(secondary_path),
                "width": width,
                "height": height,
                "chart": "map",
                "rows_plotted": len(points),
                "title": title,
            },
        ]

        return PolarsResult(output=df, artifacts=artifacts)


step = ExportToMapStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
