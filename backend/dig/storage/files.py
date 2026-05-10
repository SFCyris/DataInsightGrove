from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    """Root directory for all DIG data — datasets, uploads, cache, sqlite db.

    Defaults to `<repo>/data/` (the repo's data folder is gitignored). Override
    with DIG_DATA_DIR.
    """
    raw = os.environ.get("DIG_DATA_DIR")
    if raw:
        p = Path(raw).expanduser().resolve()
    else:
        # backend/dig/storage/files.py -> repo root is parents[3]
        p = Path(__file__).resolve().parents[3] / "data"
    p.mkdir(parents=True, exist_ok=True)
    (p / "uploads").mkdir(exist_ok=True)
    (p / "datasets").mkdir(exist_ok=True)
    (p / "outputs").mkdir(exist_ok=True)
    return p


def upload_path(dataset_id: str, original_name: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in original_name)
    return data_dir() / "uploads" / f"{dataset_id}-{safe}"


def cached_parquet_path(dataset_id: str) -> Path:
    return data_dir() / "datasets" / f"{dataset_id}.parquet"


def output_path(name: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)
    return data_dir() / "outputs" / safe
