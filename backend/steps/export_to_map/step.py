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
    if basemap is not None:
        ax.imshow(np.asarray(basemap), extent=extent, aspect="auto", origin="upper", zorder=0)
    else:
        # Graticule-only fallback — softer than nothing, still recognisable.
        ax.set_facecolor("#eef2f7")
        for lon in range(-180, 181, 30):
            ax.axvline(lon, color="#cbd5e1", linewidth=0.4, zorder=0)
        for lat in range(-90, 91, 30):
            ax.axhline(lat, color="#cbd5e1", linewidth=0.4, zorder=0)

    if points:
        lats = np.array([p["lat"] for p in points])
        lons = np.array([p["lon"] for p in points])
        ax.scatter(
            lons, lats,
            c=marker_color, s=max(8, marker_radius * 6), alpha=0.85,
            edgecolors="white", linewidths=0.8, zorder=2,
        )

    # Auto-fit axes to the bbox we picked (tiles are flush to the bbox edges).
    ax.set_xlim(bbox[0], bbox[2])
    ax.set_ylim(bbox[1], bbox[3])

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(title or "Map")
    # Equal aspect would distort labels at high latitudes (web mercator
    # already stretches things) — leave aspect free; the basemap extent
    # carries the visual proportions.
    ax.tick_params(labelsize=9)

    fig.tight_layout()
    fig.savefig(out_path, format="png", dpi=dpi, bbox_inches="tight")
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

        fmt = (params.get("format") or "lat_lon").lower()
        if fmt not in ("lat_lon", "lon_lat", "wkt_point", "separate_columns"):
            raise ValueError(f"export_to_map: unknown format '{fmt}'")

        location = (params.get("location") or "").strip() or None
        lat_col = (params.get("lat_col") or "").strip() or None
        lon_col = (params.get("lon_col") or "").strip() or None
        name_col = (params.get("name_col") or "").strip() or None
        comment_col = (params.get("comment_col") or "").strip() or None

        max_points = int(params.get("max_points") or 20_000)
        sample_df = df
        if df.height > max_points:
            sample_df = df.sample(n=max_points, seed=42)

        points = _extract_points(
            sample_df, fmt, location, lat_col, lon_col, name_col, comment_col,
        )

        title = params.get("title") or self.id
        format_out = (params.get("format_out") or "html").lower()
        if format_out not in ("html", "png"):
            raise ValueError(f"export_to_map: format_out must be 'html' or 'png', got '{format_out}'")

        width = int(params.get("width") or 1200)
        height = int(params.get("height") or 800)
        marker_color = (params.get("marker_color") or "#10b981").strip()
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

        # Render both. HTML first because it's cheap; PNG triggers
        # matplotlib import which is heavier but unavoidable for the
        # static fallback.
        html_content = _emit_html(
            points, title, width, height, marker_color, marker_radius, tile_provider,
        )
        if format_out == "html":
            primary_path.write_text(html_content, encoding="utf-8")
            _emit_png(
                points, secondary_path, title, width, height,
                marker_color, marker_radius, tile_provider,
            )
        else:
            secondary_path.write_text(html_content, encoding="utf-8")
            _emit_png(
                points, primary_path, title, width, height,
                marker_color, marker_radius, tile_provider,
            )

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
