"""Demo-bundle seeding for the home-page "🌱 Try with sample data" button.

The button now seeds three pipelines side-by-side instead of just the
single-dataset overview:

  1. **customers overview**  (1 dataset, 1–3 chart nodes — kept from the v1
     "first-click ends in a chart" UX so brand-new users still hit a chart
     within seconds)
  2. **healthcare clinical analysis**  (5 datasets × 5–10K rows, 30+
     interwoven transform steps, 5 charts) — exercises join chains, group
     aggregations, drift-detectable abnormal-lab signals
  3. **housing market with map**  (4 datasets, 15+ analytic steps, 5
     charts, 1 parquet sink + 1 ``export_to_map`` output rendering listings
     on a real interactive Leaflet map)

The seed flow is idempotent — datasets are looked up by name before
re-importing, and pipelines have stable demo names so the "overwrite if
exists" prompt knows what it's overwriting.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import polars as pl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from dig.engine.history import snapshot_pipeline
from dig.engine.profile import profile_dataframe
from dig.engine.registry import connectors
from dig.storage.files import cached_parquet_path, upload_path
from dig.storage.models import Dataset, Pipeline as PipelineRow

log = logging.getLogger(__name__)

# Stable pipeline names — used as the dedupe key for "already seeded?"
# detection and as the human-readable label everywhere the pipeline
# surfaces (catalog, run history, etc.).
NAME_OVERVIEW   = "📊 demo · customers — overview"
NAME_HEALTHCARE = "🏥 demo · healthcare — clinical analysis"
NAME_HOUSING    = "🏘 demo · housing — market with map"

DEMO_PIPELINE_NAMES = (NAME_OVERVIEW, NAME_HEALTHCARE, NAME_HOUSING)


# ---------------------------------------------------------------------------
# Sample-CSV ingest helper (idempotent)
# ---------------------------------------------------------------------------

async def _import_sample_csv(
    session: AsyncSession,
    sample_basename: str,
    *,
    pretty_name: str,
) -> Dataset:
    """Import (or fetch existing) a bundled sample CSV by basename.

    Idempotent: looks up by ``Dataset.name`` first (the pretty name is
    deterministic and includes the demo prefix), and only ingests if no
    dataset with that name exists.
    """
    # Tolerate multiple existing datasets with the same name (a side effect
    # of repeated demo runs over the project's lifetime). Pick the most
    # recent ready one — re-importing on each seed would be wasteful since
    # the bundled CSV bytes don't change.
    #
    # IMPORTANT: also verify the candidate's source_uri actually points at
    # the bundled CSV we expect. Without this check, ANY dataset that
    # happens to share the pretty name (e.g. a user uploaded their own
    # CSV with name="demo · customers") gets treated as the demo source —
    # the seed pipeline ends up reading the wrong data and the chart
    # heuristics pick fields that don't belong. The basename check is
    # a cheap "did we actually import this exact file?" guard. If a
    # user renamed/replaced the dataset deliberately, ``--basename``
    # mismatch forces a fresh re-import from the bundled bytes, keeping
    # the demo reproducible.
    res = await session.execute(
        select(Dataset).where(Dataset.name == pretty_name).order_by(Dataset.created_at.desc())
    )
    for cand in res.scalars().all():
        if not (cand.storage_uri and cand.status == "ready"):
            continue
        if cand.connector != "csv":
            continue
        # source_uri looks like ``file:///abs/path/to/uploads/<id>/<basename>``
        # — match the trailing basename to the bundled CSV name.
        if (cand.source_uri or "").rstrip("/").endswith("/" + sample_basename):
            return cand

    repo_root = Path(__file__).resolve().parents[3]
    src = (repo_root / "samples" / sample_basename).resolve()
    if not src.is_file():
        raise FileNotFoundError(f"bundled sample missing: samples/{sample_basename}")

    connector = connectors().get("csv")
    ds_id = str(ULID())
    upload = upload_path(ds_id, src.name)
    upload.parent.mkdir(parents=True, exist_ok=True)
    upload.write_bytes(src.read_bytes())

    d = Dataset(
        id=ds_id,
        name=pretty_name,
        connector="csv",
        source_uri=f"file://{upload}",
        options={"delimiter": ",", "header": True},
        file_size=upload.stat().st_size,
        status="ingesting",
    )
    session.add(d)
    await session.commit()

    try:
        lf = connector.read(d.source_uri, d.options)
        cached = cached_parquet_path(ds_id)
        cached.parent.mkdir(parents=True, exist_ok=True)
        df = lf.collect()
        df.write_parquet(cached, compression="zstd")
        d.storage_uri = f"file://{cached}"
        d.row_count = df.height
        profile = profile_dataframe(pl.scan_parquet(cached))
        d.columns = profile["columns"]
        d.profile = profile
        d.status = "ready"
    except Exception as e:
        log.exception("demo CSV ingest failed for %s", sample_basename)
        d.status = "failed"
        d.error = str(e)
    await session.commit()
    return d


# ---------------------------------------------------------------------------
# Pipeline-doc builders — pure functions, no DB access
# ---------------------------------------------------------------------------

def _ds_alias(prefix: str, dataset_id: str) -> str:
    return f"ds_{prefix}_{dataset_id.lower()}"


def build_overview_pipeline_doc(d: Dataset) -> tuple[dict[str, Any], int]:
    """Build the same 1-3 chart overview pipeline that the existing
    ``/pipelines/from-dataset/{id}`` endpoint produces.

    Kept inline (rather than refactored from pipelines.py) because that
    endpoint stays the canonical "make me an overview" path; this is just
    a shared helper for the demo bundle. Returns (doc, chart_count).
    """
    columns = d.columns or []
    if not columns:
        raise ValueError("dataset has no profiled columns yet")

    def _is_numeric(t: str) -> bool:
        s = (t or "").lower()
        return any(k in s for k in ("int", "float", "double", "decimal", "number"))

    def _is_textual(t: str) -> bool:
        s = (t or "").lower()
        return any(k in s for k in ("string", "varchar", "utf8", "text"))

    def _variation(c: dict[str, Any]) -> float:
        std = c.get("std")
        mean = c.get("mean")
        if std is None:
            return -1.0
        if mean is None or mean == 0:
            return float(std)
        return float(std) / max(abs(float(mean)), 1e-9)

    numeric = [c for c in columns if _is_numeric(c.get("type", ""))]
    numeric.sort(key=_variation, reverse=True)
    categorical = [
        c for c in columns
        if _is_textual(c.get("type", ""))
        and 2 <= (c.get("distinctCount") or 0) <= 20
    ]
    categorical.sort(key=lambda c: c.get("distinctCount") or 0)

    ds_alias = f"ds_{d.id.lower()}"
    nodes: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []

    def _add_chart(node_id: str, kind: str, x_col: str, label_emoji: str, x_offset: int) -> None:
        nodes.append({
            "id": node_id,
            "step": "export_to_image",
            "stepVersion": "1.0.0",
            "inputs": {"in": {"port": "out", "ref": ds_alias}},
            "outputs": ["out"],
            "params": {
                "kind": kind,
                "x": x_col,
                "title": f"{x_col} — {'distribution' if kind == 'histogram' else 'top values'}",
                "format": "png",
            },
            "ui": {"x": x_offset, "y": 100, "label": f"{label_emoji} {x_col}"},
        })
        outputs.append({
            "id": f"o_{node_id}",
            "name": f"{x_col}_chart",
            "from": {"port": "out", "ref": node_id},
        })

    if numeric:
        _add_chart("n_chart_hist", "histogram", numeric[0]["name"], "📊", 280)
    if categorical:
        _add_chart("n_chart_bar", "bar_counts", categorical[0]["name"], "🏷", 540)
    if len(numeric) >= 2:
        _add_chart("n_chart_hist2", "histogram", numeric[1]["name"], "📊", 800)

    if not nodes:
        first = columns[0]
        kind = "histogram" if _is_numeric(first.get("type", "")) else "bar_counts"
        _add_chart("n_chart_default", kind, first["name"], "📊", 280)

    doc = {
        "schemaVersion": 1,
        "id": "{{PIPELINE_ID}}",
        "name": NAME_OVERVIEW,
        "datasets": [{
            "id": ds_alias,
            "connector": "parquet",
            "uri": d.storage_uri,
            "label": d.name,
        }],
        "nodes": nodes,
        "outputs": outputs,
    }
    return doc, len(nodes)


# ---- healthcare ---------------------------------------------------------

# Layout grid: x = column (per stage), y = row (per dataset chain). Keeps
# the editor canvas readable when there are 30+ nodes.
_X = lambda col: 100 + col * 240  # noqa: E731 — local helper for compactness
_Y_PAT  = 80
_Y_ENC  = 280
_Y_ORD  = 480
_Y_RES  = 680
_Y_DX   = 880
_Y_OUT  = 1100


def build_healthcare_pipeline_doc(uris: dict[str, tuple[str, str]]) -> tuple[dict[str, Any], int]:
    """Build the healthcare demo pipeline.

    ``uris`` is a dict ``{kind: (dataset_uri, dataset_label)}`` where ``kind``
    is one of ``patients`` / ``encounters`` / ``orders`` / ``results`` /
    ``diagnoses`` — each pointing at the cached parquet path for the matching
    bundled CSV. Returns (doc, chart_count).
    """
    needed = {"patients", "encounters", "orders", "results", "diagnoses"}
    missing = needed - set(uris.keys())
    if missing:
        raise ValueError(f"healthcare seed needs URIs for: {sorted(missing)}")

    ds_pat = "ds_pat"
    ds_enc = "ds_enc"
    ds_ord = "ds_ord"
    ds_res = "ds_res"
    ds_dx  = "ds_dx"

    nodes: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []

    def add(node_id: str, step: str, inputs: dict, params: dict, x: int, y: int, label: str) -> None:
        nodes.append({
            "id": node_id,
            "step": step,
            "stepVersion": "1.0.0",
            "inputs": inputs,
            "outputs": ["out"],
            "params": params,
            "ui": {"x": x, "y": y, "label": label},
        })

    # ---- Patients chain (filter adults, clean ws, bin age) ---------------
    add("n_pat_filter", "filter_rows",
        {"in": {"ref": ds_pat}},
        {"predicate": '"age" >= 18'},
        _X(1), _Y_PAT, "🔍 Adults (18+)")
    add("n_pat_clean_ws", "clean_whitespace",
        {"in": {"ref": "n_pat_filter"}},
        {"column": "insurance_kind", "collapse": True, "lowercase": False},
        _X(2), _Y_PAT, "🧹 Trim insurance_kind")
    add("n_pat_age_bin", "bin_numeric",
        {"in": {"ref": "n_pat_clean_ws"}},
        {"column": "age", "mode": "custom_breaks", "breaks": "0,18,35,50,65,80,150", "as": "age_band"},
        _X(3), _Y_PAT, "📦 Age bands")
    add("n_pat_select", "select_columns",
        {"in": {"ref": "n_pat_age_bin"}},
        {"columns": ["patient_id", "sex", "age", "age_band", "bmi", "smoker_flag", "insurance_kind"]},
        _X(4), _Y_PAT, "✂️ Keep relevant cols")

    # ---- Encounters chain (cast date, derive LOS_days, bin LOS) ---------
    add("n_enc_cast_date", "cast_type",
        {"in": {"ref": ds_enc}},
        {"column": "encounter_date", "targetType": "datetime", "strict": False},
        _X(1), _Y_ENC, "🔄 Cast → datetime")
    add("n_enc_los_days", "derive_column",
        {"in": {"ref": "n_enc_cast_date"}},
        {"name": "los_days", "expression": '"length_of_stay_hours" / 24.0'},
        _X(2), _Y_ENC, "➕ los_days")
    add("n_enc_los_band", "bin_numeric",
        {"in": {"ref": "n_enc_los_days"}},
        {"column": "los_days", "mode": "custom_breaks", "breaks": "0,1,3,7,14,30,365", "as": "los_band"},
        _X(3), _Y_ENC, "📦 LOS bands")
    add("n_enc_filter_recent", "filter_rows",
        {"in": {"ref": "n_enc_los_band"}},
        {"predicate": "\"encounter_date\" >= TIMESTAMP '2025-12-01'"},
        _X(4), _Y_ENC, "🔍 ≥ 2025-12")
    add("n_enc_sort", "sort_rows",
        {"in": {"ref": "n_enc_filter_recent"}},
        {"by": [{"column": "encounter_date", "direction": "desc"}]},
        _X(5), _Y_ENC, "↕️ Newest first")

    # Join encounters + patients
    add("n_enc_join_pat", "join",
        {"left": {"ref": "n_enc_sort"}, "right": {"ref": "n_pat_select"}},
        {
            "kind": "left",
            "keys": [{"left": "patient_id", "right": "patient_id", "op": "="}],
            "columnCollisions": "keep_left",
        },
        _X(6), _Y_ENC, "🔗 Join enc × pat")

    # ---- Lab orders chain (cast, drop cancelled) ------------------------
    add("n_ord_cast_ts", "cast_type",
        {"in": {"ref": ds_ord}},
        {"column": "ordered_at", "targetType": "datetime", "strict": False},
        _X(1), _Y_ORD, "🔄 Cast ordered_at")
    add("n_ord_filter", "filter_rows",
        {"in": {"ref": "n_ord_cast_ts"}},
        {"predicate": '"cancelled_flag" = \'N\''},
        _X(2), _Y_ORD, "🔍 Active orders")
    add("n_ord_select", "select_columns",
        {"in": {"ref": "n_ord_filter"}},
        {"columns": ["order_id", "encounter_id", "test_code", "ordered_at", "priority", "ordering_provider_id"]},
        _X(3), _Y_ORD, "✂️ Trim columns")
    # Join orders + encounters (with patient demographics carried through)
    add("n_ord_join_enc", "join",
        {"left": {"ref": "n_ord_select"}, "right": {"ref": "n_enc_join_pat"}},
        {
            "kind": "inner",
            "keys": [{"left": "encounter_id", "right": "encounter_id", "op": "="}],
            "columnCollisions": "keep_left",
        },
        _X(4), _Y_ORD, "🔗 Join ord × enc")

    # Group orders by priority + department for one of the charts
    add("n_ord_group_priority", "group_aggregate",
        {"in": {"ref": "n_ord_join_enc"}},
        {
            "groupBy": ["priority", "department"],
            "aggregates": [{"fn": "count", "column": "order_id", "as": "n_orders"}],
        },
        _X(5), _Y_ORD, "📊 By priority × dept")

    # ---- Lab results chain (cast, derive severity_score, join, abnormal) -
    add("n_res_cast_ts", "cast_type",
        {"in": {"ref": ds_res}},
        {"column": "resulted_at", "targetType": "datetime", "strict": False},
        _X(1), _Y_RES, "🔄 Cast resulted_at")
    add("n_res_severity", "derive_column",
        {"in": {"ref": "n_res_cast_ts"}},
        {
            "name": "severity_score",
            "expression": (
                'CASE '
                'WHEN "value_numeric" > "reference_high" '
                'THEN ("value_numeric" - "reference_high") / NULLIF("reference_high", 0) '
                'WHEN "value_numeric" < "reference_low" '
                'THEN ("reference_low" - "value_numeric") / NULLIF(GREATEST("reference_low", 1), 0) '
                'ELSE 0.0 END'
            ),
        },
        _X(2), _Y_RES, "➕ severity_score")
    add("n_res_join_ord", "join",
        {"left": {"ref": "n_res_severity"}, "right": {"ref": "n_ord_join_enc"}},
        {
            "kind": "inner",
            "keys": [{"left": "order_id", "right": "order_id", "op": "="}],
            "columnCollisions": "keep_left",
        },
        _X(3), _Y_RES, "🔗 Join res × ord")
    add("n_res_filter_abnormal", "filter_rows",
        {"in": {"ref": "n_res_join_ord"}},
        {"predicate": '"abnormal_flag" <> \'N\''},
        _X(4), _Y_RES, "🚨 Abnormal only")
    add("n_res_group_test", "group_aggregate",
        {"in": {"ref": "n_res_filter_abnormal"}},
        {
            "groupBy": ["test_code", "department"],
            "aggregates": [{"fn": "count", "column": "result_id", "as": "n_abnormal"}],
        },
        _X(5), _Y_RES, "📊 Test × dept")
    add("n_res_dept_count", "group_aggregate",
        {"in": {"ref": "n_res_filter_abnormal"}},
        {
            "groupBy": ["department"],
            "aggregates": [{"fn": "count", "column": "result_id", "as": "abnormal_count"}],
        },
        _X(6), _Y_RES, "📊 Abnormal by dept")

    # ---- Diagnoses chain (dedupe, chronic only, join, top codes) --------
    add("n_dx_dedupe", "deduplicate",
        {"in": {"ref": ds_dx}},
        {"key": ["diagnosis_id"]},
        _X(1), _Y_DX, "🧼 Dedupe")
    add("n_dx_rename", "rename_columns",
        {"in": {"ref": "n_dx_dedupe"}},
        {"mapping": [
            {"from": "icd10_code", "to": "diagnosis_code"},
            {"from": "icd10_name", "to": "diagnosis_name"},
        ]},
        _X(2), _Y_DX, "✏️ Rename ICD")
    add("n_dx_chronic", "filter_rows",
        {"in": {"ref": "n_dx_rename"}},
        {"predicate": '"chronic_flag" = \'Y\''},
        _X(3), _Y_DX, "🔍 Chronic only")
    add("n_dx_join_enc", "join",
        {"left": {"ref": "n_dx_chronic"}, "right": {"ref": "n_enc_join_pat"}},
        {
            "kind": "inner",
            "keys": [{"left": "encounter_id", "right": "encounter_id", "op": "="}],
            "columnCollisions": "keep_left",
        },
        _X(4), _Y_DX, "🔗 Join dx × enc")
    add("n_dx_top_codes", "group_aggregate",
        {"in": {"ref": "n_dx_join_enc"}},
        {
            "groupBy": ["diagnosis_code", "diagnosis_name"],
            "aggregates": [{"fn": "count", "column": "diagnosis_id", "as": "n_dx"}],
        },
        _X(5), _Y_DX, "📊 Top codes")
    add("n_dx_top_sort", "sort_rows",
        {"in": {"ref": "n_dx_top_codes"}},
        {"by": [{"column": "n_dx", "direction": "desc"}]},
        _X(6), _Y_DX, "↕️ Most → least")
    add("n_dx_top_head", "sample_rows",
        {"in": {"ref": "n_dx_top_sort"}},
        {"kind": "head", "n": 20},
        _X(7), _Y_DX, "✂️ Top 20")

    # ---- Output charts (5) ----------------------------------------------
    add("n_chart_age_hist", "export_to_image",
        {"in": {"ref": "n_pat_select"}},
        {"kind": "histogram", "x": "age", "title": "Patient age distribution", "format": "png"},
        _X(0), _Y_OUT, "📊 Age histogram")
    outputs.append({"id": "o_age", "name": "patient_age_chart", "from": {"ref": "n_chart_age_hist"}})

    add("n_chart_los_hist", "export_to_image",
        {"in": {"ref": "n_enc_filter_recent"}},
        {"kind": "histogram", "x": "los_days", "title": "Length of stay (days)", "format": "png"},
        _X(2), _Y_OUT, "📊 LOS histogram")
    outputs.append({"id": "o_los", "name": "los_chart", "from": {"ref": "n_chart_los_hist"}})

    add("n_chart_dept_bar", "export_to_image",
        {"in": {"ref": "n_enc_filter_recent"}},
        {"kind": "bar_counts", "x": "department", "title": "Encounters by department", "format": "png"},
        _X(4), _Y_OUT, "🏷 Dept bar")
    outputs.append({"id": "o_dept", "name": "department_chart", "from": {"ref": "n_chart_dept_bar"}})

    add("n_chart_dx_bar", "export_to_image",
        {"in": {"ref": "n_dx_top_head"}},
        {"kind": "bar_counts", "x": "diagnosis_code", "title": "Top 20 chronic diagnoses", "format": "png"},
        _X(6), _Y_OUT, "🏷 ICD bar")
    outputs.append({"id": "o_dx", "name": "top_diagnoses_chart", "from": {"ref": "n_chart_dx_bar"}})

    add("n_chart_heatmap", "export_to_image",
        {"in": {"ref": "n_res_group_test"}},
        {
            "kind": "heatmap",
            "x": "department", "y4": "test_code", "value": "n_abnormal",
            "title": "Abnormal labs by test × department", "format": "png",
        },
        _X(8), _Y_OUT, "🔥 Heatmap")
    outputs.append({"id": "o_heat", "name": "abnormal_heatmap_chart", "from": {"ref": "n_chart_heatmap"}})

    chart_count = 5

    doc = {
        "schemaVersion": 1,
        "id": "{{PIPELINE_ID}}",
        "name": NAME_HEALTHCARE,
        "tags": ["demo", "healthcare", "labs"],
        "datasets": [
            {"id": ds_pat, "connector": "parquet", "uri": uris["patients"][0],   "label": uris["patients"][1]},
            {"id": ds_enc, "connector": "parquet", "uri": uris["encounters"][0], "label": uris["encounters"][1]},
            {"id": ds_ord, "connector": "parquet", "uri": uris["orders"][0],     "label": uris["orders"][1]},
            {"id": ds_res, "connector": "parquet", "uri": uris["results"][0],    "label": uris["results"][1]},
            {"id": ds_dx,  "connector": "parquet", "uri": uris["diagnoses"][0],  "label": uris["diagnoses"][1]},
        ],
        "nodes": nodes,
        "outputs": outputs,
    }
    return doc, chart_count


# ---- housing ------------------------------------------------------------

_Y_LIST = 80
_Y_SAL  = 280
_Y_SCH  = 480
_Y_INC  = 680
_Y_HOU_OUT = 900


def build_housing_pipeline_doc(uris: dict[str, tuple[str, str]]) -> tuple[dict[str, Any], int]:
    """Build the housing demo pipeline.

    ``uris`` keys: ``listings`` / ``sales`` / ``schools`` / ``incidents``.
    Pipeline produces 5 charts + 1 parquet sink + 1 interactive map output.

    Returns (doc, chart_count) — chart_count counts ALL visualization outputs
    (5 charts + 1 map = 6) so the toast shown to the user is correct.
    """
    needed = {"listings", "sales", "schools", "incidents"}
    missing = needed - set(uris.keys())
    if missing:
        raise ValueError(f"housing seed needs URIs for: {sorted(missing)}")

    ds_list = "ds_list"
    ds_sales = "ds_sales"
    ds_sch = "ds_sch"
    ds_inc = "ds_inc"

    nodes: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []

    def add(node_id: str, step: str, inputs: dict, params: dict, x: int, y: int, label: str) -> None:
        nodes.append({
            "id": node_id,
            "step": step,
            "stepVersion": "1.0.0",
            "inputs": inputs,
            "outputs": ["out"],
            "params": params,
            "ui": {"x": x, "y": y, "label": label},
        })

    # ---- Listings chain --------------------------------------------------
    add("n_list_filter_geo", "filter_rows",
        {"in": {"ref": ds_list}},
        {"predicate": '"latitude" IS NOT NULL AND "longitude" IS NOT NULL'},
        _X(1), _Y_LIST, "🔍 Has lat/lon")
    add("n_list_cast_lat", "cast_type",
        {"in": {"ref": "n_list_filter_geo"}},
        {"column": "latitude", "targetType": "double", "strict": False},
        _X(2), _Y_LIST, "🔄 Cast latitude")
    add("n_list_cast_lon", "cast_type",
        {"in": {"ref": "n_list_cast_lat"}},
        {"column": "longitude", "targetType": "double", "strict": False},
        _X(3), _Y_LIST, "🔄 Cast longitude")
    add("n_list_ppsf", "derive_column",
        {"in": {"ref": "n_list_cast_lon"}},
        {"name": "price_per_sqft", "expression": '"list_price_usd" / NULLIF("sqft", 0)'},
        _X(4), _Y_LIST, "➕ price/sqft")
    add("n_list_price_band", "bin_numeric",
        {"in": {"ref": "n_list_ppsf"}},
        {
            "column": "list_price_usd",
            "mode": "custom_breaks",
            "breaks": "0,250000,500000,750000,1000000,2000000,100000000",
            "as": "price_band",
        },
        _X(5), _Y_LIST, "📦 Price tiers")
    add("n_list_active", "filter_rows",
        {"in": {"ref": "n_list_price_band"}},
        {"predicate": "\"list_status\" IN ('active','sold','pending')"},
        _X(6), _Y_LIST, "🔍 Tradeable")
    # Combined location string for the map — "lat,lon"
    add("n_list_loc_str", "derive_column",
        {"in": {"ref": "n_list_active"}},
        {
            "name": "loc_str",
            "expression": "CAST(\"latitude\" AS VARCHAR) || ',' || CAST(\"longitude\" AS VARCHAR)",
        },
        _X(7), _Y_LIST, "➕ loc_str")
    add("n_list_popup_label", "derive_column",
        {"in": {"ref": "n_list_loc_str"}},
        {
            "name": "popup_label",
            "expression": "\"address\" || ', ' || \"city\" || ', ' || \"state\"",
        },
        _X(8), _Y_LIST, "➕ popup_label")
    add("n_list_popup_comment", "derive_column",
        {"in": {"ref": "n_list_popup_label"}},
        {
            "name": "popup_comment",
            "expression": (
                "\"property_type\" || ' · ' || CAST(\"beds\" AS VARCHAR) || 'BR / ' || "
                "CAST(\"baths\" AS VARCHAR) || 'BA · ' || CAST(\"sqft\" AS VARCHAR) || ' sqft · $' || "
                "CAST(\"list_price_usd\" AS VARCHAR)"
            ),
        },
        _X(9), _Y_LIST, "➕ popup_comment")

    # ---- Sales chain -----------------------------------------------------
    add("n_sales_cast_date", "cast_type",
        {"in": {"ref": ds_sales}},
        {"column": "sale_date", "targetType": "date", "strict": False},
        _X(1), _Y_SAL, "🔄 Cast sale_date")
    add("n_sales_join_list", "join",
        {"left": {"ref": "n_sales_cast_date"}, "right": {"ref": "n_list_active"}},
        {
            "kind": "inner",
            "keys": [{"left": "listing_id", "right": "listing_id", "op": "="}],
            "columnCollisions": "keep_left",
        },
        _X(2), _Y_SAL, "🔗 Sales × listings")
    add("n_sales_diff", "derive_column",
        {"in": {"ref": "n_sales_join_list"}},
        {
            "name": "price_diff_pct",
            "expression": '("sale_price_usd" - "list_price_usd") * 100.0 / NULLIF("list_price_usd", 0)',
        },
        _X(3), _Y_SAL, "➕ price_diff_pct")
    add("n_sales_recent", "filter_rows",
        {"in": {"ref": "n_sales_diff"}},
        {"predicate": "\"sale_date\" >= DATE '2025-05-01'"},
        _X(4), _Y_SAL, "🔍 Last 12mo")
    add("n_sales_group_city", "group_aggregate",
        {"in": {"ref": "n_sales_recent"}},
        {
            "groupBy": ["city"],
            "aggregates": [
                {"fn": "count", "column": "sale_id",       "as": "n_sales"},
                {"fn": "mean",  "column": "sale_price_usd","as": "avg_sale_price"},
                {"fn": "mean",  "column": "days_on_market","as": "avg_dom"},
            ],
        },
        _X(5), _Y_SAL, "📊 By city")

    # ---- Schools chain ---------------------------------------------------
    add("n_sch_top", "filter_rows",
        {"in": {"ref": ds_sch}},
        {"predicate": '"rating_1_10" >= 7'},
        _X(1), _Y_SCH, "🔍 Rating 7+")
    add("n_sch_group_city", "group_aggregate",
        {"in": {"ref": "n_sch_top"}},
        {
            "groupBy": ["city"],
            "aggregates": [
                {"fn": "count", "column": "school_id",   "as": "good_schools"},
                {"fn": "mean",  "column": "rating_1_10", "as": "avg_rating"},
            ],
        },
        _X(2), _Y_SCH, "📊 Schools / city")

    # ---- Incidents chain -------------------------------------------------
    add("n_inc_severe", "filter_rows",
        {"in": {"ref": ds_inc}},
        {"predicate": "\"severity\" IN ('medium','high')"},
        _X(1), _Y_INC, "🔍 Severe only")
    add("n_inc_cast_ts", "cast_type",
        {"in": {"ref": "n_inc_severe"}},
        {"column": "occurred_at", "targetType": "datetime", "strict": False},
        _X(2), _Y_INC, "🔄 Cast occurred_at")
    add("n_inc_recent", "filter_rows",
        {"in": {"ref": "n_inc_cast_ts"}},
        {"predicate": "\"occurred_at\" >= TIMESTAMP '2025-11-01'"},
        _X(3), _Y_INC, "🔍 Last 6mo")

    # ---- Final map dataset (top-priced listings) ------------------------
    add("n_list_sort_price", "sort_rows",
        {"in": {"ref": "n_list_popup_comment"}},
        {"by": [{"column": "list_price_usd", "direction": "desc"}]},
        _X(10), _Y_LIST, "↕️ Most expensive")
    add("n_list_top500", "sample_rows",
        {"in": {"ref": "n_list_sort_price"}},
        {"kind": "head", "n": 500},
        _X(11), _Y_LIST, "✂️ Top 500")

    # Parquet sink for the listings_with_geo dataset (the user-requested
    # "one output data set with geographical locations").
    add("n_sink_parquet", "export_to_file",
        {"in": {"ref": "n_list_top500"}},
        {"format": "parquet", "compression": "zstd"},
        _X(12), _Y_LIST, "💾 Parquet sink")
    outputs.append({
        "id": "o_listings_geo",
        "name": "listings_with_geo",
        "from": {"ref": "n_sink_parquet"},
    })

    # ---- Charts (5) ------------------------------------------------------
    add("n_chart_price_hist", "export_to_image",
        {"in": {"ref": "n_list_active"}},
        {"kind": "histogram", "x": "list_price_usd", "title": "List price distribution", "format": "png"},
        _X(0), _Y_HOU_OUT, "📊 Price hist")
    outputs.append({"id": "o_price_hist", "name": "price_hist", "from": {"ref": "n_chart_price_hist"}})

    add("n_chart_sqft_scatter", "export_to_image",
        {"in": {"ref": "n_list_active"}},
        {
            "kind": "scatter",
            "x": "sqft", "y": "list_price_usd",
            "title": "Sqft vs list price", "format": "png",
        },
        _X(2), _Y_HOU_OUT, "✦ Sqft × price")
    outputs.append({"id": "o_sqft", "name": "sqft_scatter", "from": {"ref": "n_chart_sqft_scatter"}})

    add("n_chart_dom_hist", "export_to_image",
        {"in": {"ref": "n_sales_recent"}},
        {"kind": "histogram", "x": "days_on_market", "title": "Days on market", "format": "png"},
        _X(4), _Y_HOU_OUT, "📊 DOM hist")
    outputs.append({"id": "o_dom", "name": "days_on_market_chart", "from": {"ref": "n_chart_dom_hist"}})

    add("n_chart_city_bar", "export_to_image",
        {"in": {"ref": "n_sales_group_city"}},
        {"kind": "bar_counts", "x": "city", "title": "Sales by city", "format": "png"},
        _X(6), _Y_HOU_OUT, "🏷 City bar")
    outputs.append({"id": "o_city", "name": "city_bar", "from": {"ref": "n_chart_city_bar"}})

    add("n_chart_band_heatmap", "export_to_image",
        {"in": {"ref": "n_list_active"}},
        {
            "kind": "heatmap",
            "x": "city", "y4": "price_band", "value": "sqft",
            "title": "City × price band (avg sqft)", "format": "png",
        },
        _X(8), _Y_HOU_OUT, "🔥 Band heatmap")
    outputs.append({"id": "o_band", "name": "band_heatmap", "from": {"ref": "n_chart_band_heatmap"}})

    # ---- Map output ------------------------------------------------------
    # Format = lat_lon over the derived loc_str column.
    add("n_chart_map", "export_to_map",
        {"in": {"ref": "n_list_top500"}},
        {
            "format": "lat_lon",
            "location": "loc_str",
            "name_col": "popup_label",
            "comment_col": "popup_comment",
            "title": "Top-priced listings",
            "marker_color": "#10b981",
            "marker_radius": 7,
            "tile_provider": "carto-light",
            "format_out": "html",
        },
        _X(10), _Y_HOU_OUT, "🗺 Listings map")
    outputs.append({"id": "o_map", "name": "listings_map", "from": {"ref": "n_chart_map"}})

    # 5 image charts + 1 map = 6 visualizations
    chart_count = 6

    doc = {
        "schemaVersion": 1,
        "id": "{{PIPELINE_ID}}",
        "name": NAME_HOUSING,
        "tags": ["demo", "housing", "geo", "map"],
        "datasets": [
            {"id": ds_list,  "connector": "parquet", "uri": uris["listings"][0],  "label": uris["listings"][1]},
            {"id": ds_sales, "connector": "parquet", "uri": uris["sales"][0],     "label": uris["sales"][1]},
            {"id": ds_sch,   "connector": "parquet", "uri": uris["schools"][0],   "label": uris["schools"][1]},
            {"id": ds_inc,   "connector": "parquet", "uri": uris["incidents"][0], "label": uris["incidents"][1]},
        ],
        "nodes": nodes,
        "outputs": outputs,
    }
    return doc, chart_count


# ---------------------------------------------------------------------------
# Public seeding flow
# ---------------------------------------------------------------------------

async def detect_existing_demo_pipelines(session: AsyncSession) -> list[str]:
    """Return the names of demo pipelines that already exist in the DB."""
    res = await session.execute(
        select(PipelineRow).where(PipelineRow.name.in_(DEMO_PIPELINE_NAMES))
    )
    return sorted({row.name for row in res.scalars().all()})


async def _get_demo_pipeline_ids(session: AsyncSession) -> list[str]:
    """Return IDs (not names) of every existing demo pipeline. Used by
    the seed-then-delete path to capture the OLD set before seeding new
    ones — without this, the cleanup would also delete the just-seeded
    pipelines (same name)."""
    res = await session.execute(
        select(PipelineRow).where(PipelineRow.name.in_(DEMO_PIPELINE_NAMES))
    )
    return [row.id for row in res.scalars().all()]


async def delete_pipelines_by_id(session: AsyncSession, pipeline_ids: list[str]) -> int:
    """Delete the given pipelines + cascade their runs + history snapshots.
    Caller passes the explicit ID list (vs. ``delete_demo_pipelines``
    which deletes by name) so the seed-then-delete flow can target only
    the OLD set, not the freshly-seeded new one."""
    if not pipeline_ids:
        return 0
    from dig.storage.models import PipelineHistory, Run
    runs = await session.execute(select(Run).where(Run.pipeline_id.in_(pipeline_ids)))
    for r in runs.scalars().all():
        await session.delete(r)
    snaps = await session.execute(
        select(PipelineHistory).where(PipelineHistory.pipeline_id.in_(pipeline_ids))
    )
    for h in snaps.scalars().all():
        await session.delete(h)
    rows = await session.execute(select(PipelineRow).where(PipelineRow.id.in_(pipeline_ids)))
    for row in rows.scalars().all():
        await session.delete(row)
    await session.commit()
    return len(pipeline_ids)


async def delete_demo_pipelines(session: AsyncSession) -> int:
    """Delete every existing demo pipeline by name + all of their runs +
    all of their history snapshots. Returns the count of pipelines
    deleted.

    Why cascade explicitly: ``Run.pipeline_id`` and
    ``PipelineHistory.pipeline_id`` are plain string columns, NOT foreign
    keys with ON DELETE CASCADE. Without this, a re-seed would leave
    orphan rows in the runs / history tables — those rows still surface
    in the run-history list page (with `pipelineName` falling back to
    the dead ULID, no way to navigate to them, no way to re-run them).
    Adding the cascade here keeps the overwrite path producing the
    "fresh demo state" the user just asked for.
    """
    from dig.storage.models import PipelineHistory, Run

    res = await session.execute(
        select(PipelineRow).where(PipelineRow.name.in_(DEMO_PIPELINE_NAMES))
    )
    rows = list(res.scalars().all())
    if not rows:
        return 0

    pids = [row.id for row in rows]

    # Delete runs first so any open subscriber on /runs doesn't see a
    # mid-cascade snapshot.
    runs = await session.execute(select(Run).where(Run.pipeline_id.in_(pids)))
    for r in runs.scalars().all():
        await session.delete(r)

    # Then history snapshots.
    snaps = await session.execute(
        select(PipelineHistory).where(PipelineHistory.pipeline_id.in_(pids))
    )
    for h in snaps.scalars().all():
        await session.delete(h)

    # Finally the pipeline rows themselves.
    for row in rows:
        await session.delete(row)
    await session.commit()
    return len(rows)


async def seed_all_demos(session: AsyncSession) -> dict[str, Any]:
    """Idempotently import bundled CSVs and create the three demo pipelines.

    Caller is responsible for the "already exists" check + overwrite gate
    (use ``detect_existing_demo_pipelines`` and ``delete_demo_pipelines``
    before invoking this if the user said yes to overwrite).

    Returns a summary dict with the created pipelines + their primary
    dataset id (the customers overview pipeline is the "primary" — the
    frontend redirects to it as before so the first-run UX is unchanged).
    """
    import json as _json

    # --- 1. Customers overview --------------------------------------------
    customers = await _import_sample_csv(
        session, "customers-demo.csv", pretty_name="demo · customers",
    )
    if customers.status != "ready":
        raise RuntimeError(f"customers demo dataset not ready: {customers.error}")
    cust_doc, cust_charts = build_overview_pipeline_doc(customers)
    cust_pid = str(ULID())
    cust_doc["id"] = cust_pid
    cust_row = PipelineRow(id=cust_pid, name=NAME_OVERVIEW, document=cust_doc, etag=1)
    session.add(cust_row)
    await snapshot_pipeline(session, cust_pid, cust_doc, 1, triggered_by="import")

    # --- 2. Healthcare ----------------------------------------------------
    health_specs = [
        ("patients",   "healthcare-patients-demo.csv",    "demo · healthcare patients"),
        ("encounters", "healthcare-encounters-demo.csv",  "demo · healthcare encounters"),
        ("orders",     "healthcare-lab-orders-demo.csv",  "demo · healthcare lab orders"),
        ("results",    "healthcare-lab-results-demo.csv", "demo · healthcare lab results"),
        ("diagnoses",  "healthcare-diagnoses-demo.csv",   "demo · healthcare diagnoses"),
    ]
    h_uris: dict[str, tuple[str, str]] = {}
    for kind, basename, label in health_specs:
        d = await _import_sample_csv(session, basename, pretty_name=label)
        if d.status != "ready":
            raise RuntimeError(f"{basename} not ready: {d.error}")
        h_uris[kind] = (d.storage_uri, d.name)

    h_doc, h_charts = build_healthcare_pipeline_doc(h_uris)
    h_pid = str(ULID())
    h_doc["id"] = h_pid
    h_row = PipelineRow(id=h_pid, name=NAME_HEALTHCARE, document=h_doc, etag=1)
    session.add(h_row)
    await snapshot_pipeline(session, h_pid, h_doc, 1, triggered_by="import")

    # --- 3. Housing -------------------------------------------------------
    housing_specs = [
        ("listings",  "housing-listings-demo.csv",  "demo · housing listings"),
        ("sales",     "housing-sales-demo.csv",     "demo · housing sales"),
        ("schools",   "housing-schools-demo.csv",   "demo · housing schools"),
        ("incidents", "housing-incidents-demo.csv", "demo · housing incidents"),
    ]
    hou_uris: dict[str, tuple[str, str]] = {}
    for kind, basename, label in housing_specs:
        d = await _import_sample_csv(session, basename, pretty_name=label)
        if d.status != "ready":
            raise RuntimeError(f"{basename} not ready: {d.error}")
        hou_uris[kind] = (d.storage_uri, d.name)

    hou_doc, hou_charts = build_housing_pipeline_doc(hou_uris)
    hou_pid = str(ULID())
    hou_doc["id"] = hou_pid
    hou_row = PipelineRow(id=hou_pid, name=NAME_HOUSING, document=hou_doc, etag=1)
    session.add(hou_row)
    await snapshot_pipeline(session, hou_pid, hou_doc, 1, triggered_by="import")

    await session.commit()

    return {
        "primary": {"datasetId": customers.id, "pipelineId": cust_pid},
        "pipelines": [
            {"id": cust_pid, "name": NAME_OVERVIEW,   "chartCount": cust_charts},
            {"id": h_pid,    "name": NAME_HEALTHCARE, "chartCount": h_charts},
            {"id": hou_pid,  "name": NAME_HOUSING,    "chartCount": hou_charts},
        ],
        "totalCharts": cust_charts + h_charts + hou_charts,
    }
