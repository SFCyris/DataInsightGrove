"""Build script for geospatial_pack reference data.

Converts the TopoJSON sources fetched into _build/sources/ into compact
parquet files written to data/. After this runs, `dig-pack build` zips
data/ into data.zip + updates pack.json.

Sources (declared in _build/sources.json):
  - us_states_10m.json (us-atlas v3) → data/us_states_10m.parquet
  - world_countries_10m.json (world-atlas v2) → data/world_countries_10m.parquet

The TopoJSON spec is small enough that we decode it inline rather than
take a third-party runtime dependency. The decoder handles:
  - Optional quantization transforms (translate + scale on integer coords)
  - Arc references (positive index = forward, ~index = reversed)
  - Polygon (rings of arcs) and MultiPolygon (lists of rings)

Run with:
  backend/.venv/bin/python FunctionPacks/packs/geospatial_pack/_build/build.py
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PACK_DIR = THIS_DIR.parent
SOURCES_DIR = THIS_DIR / "sources"
DATA_DIR = PACK_DIR / "data"


# ---------- TopoJSON decoder ----------------------------------------------


def _untransform(coord: list[int], transform: dict | None) -> tuple[float, float]:
    """Apply the inverse quantization transform if present.

    TopoJSON quantizes coordinates to integers for compactness:
        x_quantised = (x_real - translate[0]) / scale[0]
    We invert: x_real = translate[0] + x_quantised * scale[0].
    """
    if transform is None:
        return float(coord[0]), float(coord[1])
    sx, sy = transform["scale"]
    tx, ty = transform["translate"]
    return tx + coord[0] * sx, ty + coord[1] * sy


def _decode_arcs(topology: dict) -> list[list[tuple[float, float]]]:
    """Materialise every arc with delta-decoding + un-transformation.

    TopoJSON stores each arc as a sequence of delta-encoded integer
    coordinates relative to the previous point. We reconstruct the real
    [x,y] sequence per arc.
    """
    transform = topology.get("transform")
    decoded: list[list[tuple[float, float]]] = []
    for arc in topology["arcs"]:
        if not arc:
            decoded.append([])
            continue
        if transform is None:
            # No quantization → coords are already floats, no delta encoding.
            decoded.append([(float(p[0]), float(p[1])) for p in arc])
            continue
        # Delta decode: each pair adds to the running coord.
        cx, cy = 0, 0
        points: list[tuple[float, float]] = []
        for dx, dy in arc:
            cx += dx
            cy += dy
            points.append(_untransform([cx, cy], transform))
        decoded.append(points)
    return decoded


def _ring(arc_indices: list[int], decoded_arcs: list[list[tuple[float, float]]]) -> list[tuple[float, float]]:
    """Stitch a list of arc indices into a single ring of points.

    A negative index means "use this arc in reverse" (TopoJSON encodes
    shared boundaries this way so the boundary between two polygons is
    stored once).
    """
    ring: list[tuple[float, float]] = []
    for idx in arc_indices:
        if idx < 0:
            arc = list(reversed(decoded_arcs[~idx]))
        else:
            arc = decoded_arcs[idx]
        # When stitching the second+ arc, skip its first point — the
        # previous arc ended on that vertex (shared endpoint).
        if ring and arc:
            ring.extend(arc[1:])
        else:
            ring.extend(arc)
    return ring


def _valid_ring(points: list[tuple[float, float]]) -> list[tuple[float, float]] | None:
    """A Shapely LinearRing needs at least 4 vertices. TopoJSON sources
    occasionally encode degenerate rings (2-3 points) for tiny offshore
    islands at coarse simplification; skip those instead of crashing
    the whole feature.
    """
    if not points or len(points) < 4:
        return None
    return points


def _to_shapely(geom: dict, decoded_arcs):
    from shapely.geometry import Polygon, MultiPolygon
    t = geom["type"]
    if t == "Polygon":
        rings_raw = [_ring(ai, decoded_arcs) for ai in geom["arcs"]]
        rings = [r for r in (_valid_ring(rg) for rg in rings_raw) if r is not None]
        if not rings:
            return None
        try:
            return Polygon(shell=rings[0], holes=rings[1:])
        except Exception:
            return None
    if t == "MultiPolygon":
        polys = []
        for poly_arcs in geom["arcs"]:
            rings_raw = [_ring(ai, decoded_arcs) for ai in poly_arcs]
            rings = [r for r in (_valid_ring(rg) for rg in rings_raw) if r is not None]
            if not rings:
                continue
            try:
                polys.append(Polygon(shell=rings[0], holes=rings[1:]))
            except Exception:
                continue
        if not polys:
            return None
        return MultiPolygon(polys)
    # Other geometry types (Point, LineString, etc.) — out of scope for
    # boundary lookups.
    return None


def topojson_to_features(topology: dict, object_name: str) -> list[dict]:
    """Return a list of {properties, geometry: shapely} for the named
    TopoJSON object. ``object_name`` is the key under ``topology.objects``."""
    obj = topology["objects"][object_name]
    decoded_arcs = _decode_arcs(topology)
    features = []
    if obj["type"] == "GeometryCollection":
        for geom in obj["geometries"]:
            shape = _to_shapely(geom, decoded_arcs)
            if shape is None:
                continue
            features.append({
                "properties": geom.get("properties") or {},
                "id": geom.get("id"),
                "geometry": shape,
            })
    else:
        shape = _to_shapely(obj, decoded_arcs)
        if shape is not None:
            features.append({"properties": obj.get("properties") or {}, "geometry": shape})
    return features


# ---------- fetch + build --------------------------------------------------


def fetch_if_missing(url: str, dest: Path) -> None:
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  fetching {url}")
    with urllib.request.urlopen(url, timeout=60) as resp, dest.open("wb") as f:
        while True:
            chunk = resp.read(64 * 1024)
            if not chunk:
                break
            f.write(chunk)


# ISO 3166 numeric → alpha-2 / alpha-3 / name. Used to enrich the
# world-atlas output (its built-in properties only include "name").
def _country_lookup_map() -> dict[str, dict[str, str]]:
    """Returns ``{ numeric_3digit: {alpha2, alpha3, name} }``.
    Uses pycountry which is already a dep of reference_data pack."""
    try:
        import pycountry
    except ImportError:
        print("  warn: pycountry not installed — country output will lack ISO codes")
        return {}
    out: dict[str, dict[str, str]] = {}
    for c in pycountry.countries:
        if hasattr(c, "numeric") and c.numeric:
            out[c.numeric] = {
                "alpha_2": c.alpha_2,
                "alpha_3": c.alpha_3,
                "name": c.name,
            }
    return out


def build_us_states() -> None:
    import polars as pl
    src = SOURCES_DIR / "us_states_10m.json"
    fetch_if_missing("https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json", src)
    print(f"  decoding {src.name}")
    topology = json.loads(src.read_text(encoding="utf-8"))
    features = topojson_to_features(topology, "states")
    rows = []
    for f in features:
        geom = f["geometry"]
        if geom is None or geom.is_empty:
            continue
        props = f["properties"]
        centroid = geom.centroid
        rows.append({
            "name": props.get("name", ""),
            "fips": str(f.get("id") or props.get("STATEFP") or "").zfill(2),
            "geometry_wkb": geom.wkb,
            "centroid_lat": float(centroid.y),
            "centroid_lon": float(centroid.x),
            "bbox_min_lon": float(geom.bounds[0]),
            "bbox_min_lat": float(geom.bounds[1]),
            "bbox_max_lon": float(geom.bounds[2]),
            "bbox_max_lat": float(geom.bounds[3]),
        })
    # Attach 2-letter postal codes via a static FIPS → USPS map.
    fips_to_usps = _us_state_fips_to_usps()
    for r in rows:
        r["usps"] = fips_to_usps.get(r["fips"], "")
    df = pl.DataFrame(rows)
    out = DATA_DIR / "us_states_10m.parquet"
    df.write_parquet(out, compression="zstd")
    print(f"  ✓ {out.name}: {len(rows)} rows, {out.stat().st_size:,} bytes")


def _build_world_countries_at_resolution(
    *, resolution_label: str, url: str, source_filename: str, output_filename: str,
) -> None:
    """Shared body for ``build_world_countries_*`` — the only thing that
    differs per resolution is the upstream URL + the output filenames."""
    import polars as pl
    src = SOURCES_DIR / source_filename
    fetch_if_missing(url, src)
    print(f"  decoding {src.name}")
    topology = json.loads(src.read_text(encoding="utf-8"))
    features = topojson_to_features(topology, "countries")
    iso_map = _country_lookup_map()
    rows = []
    for f in features:
        geom = f["geometry"]
        if geom is None or geom.is_empty:
            continue
        props = f["properties"]
        numeric = str(f.get("id") or "").zfill(3) if f.get("id") else ""
        iso_entry = iso_map.get(numeric, {})
        centroid = geom.centroid
        rows.append({
            "name": iso_entry.get("name") or props.get("name", ""),
            "alpha_2": iso_entry.get("alpha_2", ""),
            "alpha_3": iso_entry.get("alpha_3", ""),
            "numeric": numeric,
            "geometry_wkb": geom.wkb,
            "centroid_lat": float(centroid.y),
            "centroid_lon": float(centroid.x),
            "bbox_min_lon": float(geom.bounds[0]),
            "bbox_min_lat": float(geom.bounds[1]),
            "bbox_max_lon": float(geom.bounds[2]),
            "bbox_max_lat": float(geom.bounds[3]),
        })
    df = pl.DataFrame(rows)
    out = DATA_DIR / output_filename
    df.write_parquet(out, compression="zstd")
    print(f"  ✓ {out.name}: {len(rows)} rows at {resolution_label}, {out.stat().st_size:,} bytes")


def build_world_countries_10m() -> None:
    """High-detail: 254 entities including all microstates (Malta,
    Liechtenstein, Monaco, San Marino, Andorra, Singapore)."""
    _build_world_countries_at_resolution(
        resolution_label="1:10,000,000",
        url="https://cdn.jsdelivr.net/npm/world-atlas@2/countries-10m.json",
        source_filename="world_countries_10m.json",
        output_filename="world_countries_10m.parquet",
    )


def build_world_countries_110m() -> None:
    """Low-detail: ~177 entities. Microstates omitted (they're below
    the 110m simplification threshold). Useful when you're rendering
    at world scale and need fast loads + lean payload."""
    _build_world_countries_at_resolution(
        resolution_label="1:110,000,000",
        url="https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json",
        source_filename="world_countries_110m.json",
        output_filename="world_countries_110m.parquet",
    )


def _us_state_fips_to_usps() -> dict[str, str]:
    """Static 51-entry mapping. Sourced from the U.S. Census Bureau's
    state FIPS table — public domain."""
    return {
        "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA",
        "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL",
        "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN",
        "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME",
        "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS",
        "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
        "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
        "39": "OH", "40": "OK", "41": "PA", "42": "PA", "44": "RI",
        "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
        "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI",
        "56": "WY", "60": "AS", "66": "GU", "69": "MP", "72": "PR",
        "78": "VI",
    }


_AGGREGATE_GROUPS: list[tuple[str, str, str, list[str]]] = []  # filled in by build_world_aggregates_at


def _build_world_aggregates_at(resolution_label: str, *, source_filename: str, output_filename: str) -> None:
    """Shared body for aggregate-builder per resolution.

    Reads the freshly-built ``world_countries_<res>.parquet`` so the
    aggregates use the same source resolution + projection. Stored as
    a sibling parquet so the lookup step can query both transparently.
    """
    import polars as pl
    from shapely import wkb
    from shapely.ops import unary_union

    src = DATA_DIR / source_filename
    countries = pl.read_parquet(src)
    by_alpha3 = {row["alpha_3"]: row for row in countries.iter_rows(named=True) if row["alpha_3"]}

    groups: list[tuple[str, str, str, list[str]]] = [
        # (code, full_name, alternate_names_pipe_separated, ISO-3 members)
        ("EU", "European Union",
         "European Union|Europäische Union|Union européenne|Unión Europea",
         ["AUT", "BEL", "BGR", "HRV", "CYP", "CZE", "DNK", "EST", "FIN", "FRA",
          "DEU", "GRC", "HUN", "IRL", "ITA", "LVA", "LTU", "LUX", "MLT", "NLD",
          "POL", "PRT", "ROU", "SVK", "SVN", "ESP", "SWE"]),
        ("EEA", "European Economic Area",
         "European Economic Area",
         # EU 27 + Iceland, Liechtenstein, Norway
         ["AUT", "BEL", "BGR", "HRV", "CYP", "CZE", "DNK", "EST", "FIN", "FRA",
          "DEU", "GRC", "HUN", "IRL", "ITA", "LVA", "LTU", "LUX", "MLT", "NLD",
          "POL", "PRT", "ROU", "SVK", "SVN", "ESP", "SWE",
          "ISL", "LIE", "NOR"]),
        ("SCHENGEN", "Schengen Area",
         "Schengen Area|Schengen",
         # EU members in Schengen + Iceland, Liechtenstein, Norway, Switzerland
         # (excludes Cyprus, Ireland; includes EFTA non-EU members)
         ["AUT", "BEL", "BGR", "HRV", "CZE", "DNK", "EST", "FIN", "FRA",
          "DEU", "GRC", "HUN", "ITA", "LVA", "LTU", "LUX", "MLT", "NLD",
          "POL", "PRT", "ROU", "SVK", "SVN", "ESP", "SWE",
          "ISL", "LIE", "NOR", "CHE"]),
        ("G7", "G7",
         "G7|Group of Seven",
         ["CAN", "FRA", "DEU", "ITA", "JPN", "GBR", "USA"]),
        ("G20", "G20",
         "G20|Group of Twenty",
         # 19 sovereign members. The 20th seat (EU) is captured by the
         # EU aggregate above, so we don't double-count its territory.
         ["ARG", "AUS", "BRA", "CAN", "CHN", "FRA", "DEU", "IND", "IDN",
          "ITA", "JPN", "MEX", "RUS", "SAU", "ZAF", "KOR", "TUR", "GBR",
          "USA"]),
        ("BRICS", "BRICS",
         "BRICS",
         ["BRA", "RUS", "IND", "CHN", "ZAF"]),
        ("USMCA", "USMCA",
         "USMCA|North American Free Trade Area|NAFTA",
         ["USA", "CAN", "MEX"]),
        ("ASEAN", "ASEAN",
         "ASEAN|Association of Southeast Asian Nations",
         ["BRN", "KHM", "IDN", "LAO", "MYS", "MMR", "PHL", "SGP", "THA", "VNM"]),
    ]

    rows = []
    for code, name, aliases, members in groups:
        member_geoms = []
        missing: list[str] = []
        from shapely.validation import make_valid
        for alpha3 in members:
            row = by_alpha3.get(alpha3)
            if row is None:
                missing.append(alpha3)
                continue
            try:
                g = wkb.loads(row["geometry_wkb"])
                # Some source polygons (notably Russia, which crosses the
                # antimeridian) have self-intersections that make Shapely's
                # union_all blow up with a TopologyException. make_valid
                # fixes those without changing the visual outline.
                if not g.is_valid:
                    g = make_valid(g)
                member_geoms.append(g)
            except Exception as e:
                missing.append(f"{alpha3}({type(e).__name__})")
        if missing:
            print(f"  warn: {code}: missing/invalid for {missing}")
        if not member_geoms:
            print(f"  skip: {code} has no member geometries")
            continue
        try:
            merged = unary_union(member_geoms)
        except Exception as e:
            # Fallback: sequential pairwise union with .buffer(0) on each
            # input — slower but tolerant of borderline-invalid geometries.
            print(f"  warn: {code} union_all failed ({e}); falling back to pairwise")
            merged = member_geoms[0].buffer(0)
            for g in member_geoms[1:]:
                merged = merged.union(g.buffer(0))
        # Normalize Polygon → MultiPolygon so the column dtype stays
        # uniform and downstream Shapely use can rely on it.
        if merged.geom_type == "Polygon":
            from shapely.geometry import MultiPolygon
            merged = MultiPolygon([merged])
        centroid = merged.centroid
        rows.append({
            "code": code,
            "name": name,
            "aliases": aliases,
            "member_count": len(member_geoms),
            "members_alpha3": ",".join(members),
            "geometry_wkb": merged.wkb,
            "centroid_lat": float(centroid.y),
            "centroid_lon": float(centroid.x),
            "bbox_min_lon": float(merged.bounds[0]),
            "bbox_min_lat": float(merged.bounds[1]),
            "bbox_max_lon": float(merged.bounds[2]),
            "bbox_max_lat": float(merged.bounds[3]),
        })

    df = pl.DataFrame(rows)
    out = DATA_DIR / output_filename
    df.write_parquet(out, compression="zstd")
    print(f"  ✓ {out.name}: {len(rows)} aggregates at {resolution_label}, {out.stat().st_size:,} bytes")


def build_world_aggregates_10m() -> None:
    _build_world_aggregates_at(
        "1:10,000,000",
        source_filename="world_countries_10m.parquet",
        output_filename="world_aggregates_10m.parquet",
    )


def build_world_aggregates_110m() -> None:
    _build_world_aggregates_at(
        "1:110,000,000",
        source_filename="world_countries_110m.parquet",
        output_filename="world_aggregates_110m.parquet",
    )


def _equal_area_circle_wkb(lat: float, lon: float, area_m2: float) -> bytes:
    """Approximate a region's boundary as an equal-area circle around
    its centroid.

    Given the gazetteer's land area in m², compute the radius of a
    circle with that area and return a 32-vertex regular polygon as
    WKB. This is APPROXIMATE — real ZCTA / Place boundaries are
    irregular, sometimes non-contiguous, and don't fit any radius. But
    it's honest about being a centroid-based stand-in (the user sees a
    circle, not a fake-looking simulated boundary). For accurate
    rendering use a custom dataset.
    """
    import math as _math
    from shapely.geometry import Polygon
    if area_m2 <= 0:
        area_m2 = 196_000.0  # tiny default — ~250 m circle
    r_m = _math.sqrt(area_m2 / _math.pi)
    deg_lat = r_m / 111_320.0
    cos_lat = max(0.01, _math.cos(_math.radians(lat)))
    deg_lon = r_m / (111_320.0 * cos_lat)
    n = 32
    coords = [
        (lon + deg_lon * _math.cos(2 * _math.pi * i / n),
         lat + deg_lat * _math.sin(2 * _math.pi * i / n))
        for i in range(n)
    ]
    coords.append(coords[0])
    return Polygon(coords).wkb


def _fetch_zip_text(url: str, member_filename: str, dest_text: Path) -> None:
    """Download a Census Bureau ``.zip`` containing one ``.txt`` file
    and extract it to ``dest_text``. Idempotent."""
    if dest_text.exists():
        return
    import zipfile as _zipfile
    import io as _io
    print(f"  fetching {url}")
    with urllib.request.urlopen(url, timeout=60) as resp:
        zip_bytes = resp.read()
    with _zipfile.ZipFile(_io.BytesIO(zip_bytes)) as zf:
        with zf.open(member_filename) as src, dest_text.open("wb") as out:
            while True:
                chunk = src.read(64 * 1024)
                if not chunk:
                    break
                out.write(chunk)


def build_us_zcta() -> None:
    """Convert the Census ZCTA gazetteer into a parquet of
    (zip, centroid, approximate boundary)."""
    import polars as pl
    src = SOURCES_DIR / "us_zcta_gazetteer_2023.txt"
    _fetch_zip_text(
        "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_Gaz_zcta_national.zip",
        "2023_Gaz_zcta_national.txt", src,
    )
    print(f"  parsing {src.name}")
    rows = []
    with src.open("r", encoding="utf-8") as f:
        header = [h.strip() for h in f.readline().strip().split("\t")]
        cols = {h: i for i, h in enumerate(header)}
        for line in f:
            parts = [p.strip() for p in line.rstrip("\n").split("\t")]
            if len(parts) < len(header):
                continue
            try:
                zip_code = parts[cols["GEOID"]]
                lat = float(parts[cols["INTPTLAT"]])
                lon = float(parts[cols["INTPTLONG"]])
                area_m2 = float(parts[cols["ALAND"]])
            except (KeyError, ValueError, IndexError):
                continue
            rows.append({
                "zip": zip_code,
                "centroid_lat": lat,
                "centroid_lon": lon,
                "land_area_m2": area_m2,
                "geometry_wkb": _equal_area_circle_wkb(lat, lon, area_m2),
            })
    df = pl.DataFrame(rows)
    out = DATA_DIR / "us_zcta_centroids_2023.parquet"
    df.write_parquet(out, compression="zstd")
    print(f"  ✓ {out.name}: {len(rows)} ZCTAs, {out.stat().st_size:,} bytes")


def build_us_places() -> None:
    """Convert the Census Places gazetteer into a parquet of
    (state, name, place_type, centroid, approximate boundary)."""
    import polars as pl
    src = SOURCES_DIR / "us_places_gazetteer_2023.txt"
    _fetch_zip_text(
        "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_Gaz_place_national.zip",
        "2023_Gaz_place_national.txt", src,
    )
    print(f"  parsing {src.name}")
    suffixes = [
        " municipality", " consolidated government", " metropolitan government",
        " unified government", " urban county",
        " city", " town", " village", " borough", " CDP",
        " comunidad", " zona urbana",
    ]
    rows = []
    with src.open("r", encoding="utf-8") as f:
        header = [h.strip() for h in f.readline().strip().split("\t")]
        cols = {h: i for i, h in enumerate(header)}
        for line in f:
            parts = [p.strip() for p in line.rstrip("\n").split("\t")]
            if len(parts) < len(header):
                continue
            try:
                state = parts[cols["USPS"]]
                geoid = parts[cols["GEOID"]]
                raw_name = parts[cols["NAME"]]
                lsad = parts[cols["LSAD"]]
                lat = float(parts[cols["INTPTLAT"]])
                lon = float(parts[cols["INTPTLONG"]])
                area_m2 = float(parts[cols["ALAND"]])
            except (KeyError, ValueError, IndexError):
                continue
            display = raw_name
            place_type = "place"
            for suf in suffixes:
                if display.endswith(suf):
                    place_type = suf.strip().lower().replace(" ", "_")
                    display = display[: -len(suf)]
                    break
            rows.append({
                "state": state,
                "geoid": geoid,
                "name": display,
                "name_state": f"{display}, {state}",  # for "Springfield, IL"-style lookup
                "full_name": raw_name,
                "place_type": place_type,
                "lsad": lsad,
                "centroid_lat": lat,
                "centroid_lon": lon,
                "land_area_m2": area_m2,
                "geometry_wkb": _equal_area_circle_wkb(lat, lon, area_m2),
            })
    df = pl.DataFrame(rows)
    out = DATA_DIR / "us_places_2023.parquet"
    df.write_parquet(out, compression="zstd")
    print(f"  ✓ {out.name}: {len(rows)} places, {out.stat().st_size:,} bytes")


def main() -> int:
    DATA_DIR.mkdir(exist_ok=True)
    print(f"Building geospatial_pack data → {DATA_DIR}")
    print()
    print("[1/7] US states")
    build_us_states()
    print()
    print("[2/7] World countries — 10m (high detail, all microstates)")
    build_world_countries_10m()
    print()
    print("[3/7] World countries — 110m (low detail, fast world-scale render)")
    build_world_countries_110m()
    print()
    print("[4/7] World aggregates — 10m")
    build_world_aggregates_10m()
    print()
    print("[5/7] World aggregates — 110m")
    build_world_aggregates_110m()
    print()
    print("[6/7] US ZCTA centroids + approximate boundaries")
    build_us_zcta()
    print()
    print("[7/7] US Places centroids + approximate boundaries")
    build_us_places()
    print()
    print("Done. Next:")
    print("  cd <repo-root>")
    print("  backend/.venv/bin/dig-pack build FunctionPacks/packs/geospatial_pack")
    return 0


if __name__ == "__main__":
    sys.exit(main())
