from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step

_EXT = {
    "parquet": ".parquet", "csv": ".csv", "tsv": ".tsv",
    "excel": ".xlsx", "json": ".json", "ndjson": ".jsonl",
}


class ExportToFileStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        fmt = (params.get("format") or "parquet").lower()
        ext = _EXT.get(fmt, "")

        path_param = (params.get("path") or "").strip()
        if path_param:
            path = Path(path_param).expanduser()
            if not path.is_absolute() and ctx is not None:
                path = ctx.out_dir / path
        else:
            base = ctx.out_dir if ctx is not None else Path.cwd()
            path = base / f"export-{self.id}{ext}"
        if path.suffix == "":
            path = path.with_suffix(ext)

        path.parent.mkdir(parents=True, exist_ok=True)

        if fmt == "parquet":
            comp = params.get("compression") or "zstd"
            df.write_parquet(path, compression="uncompressed" if comp == "uncompressed" else comp)
        elif fmt == "csv":
            df.write_csv(path)
        elif fmt == "tsv":
            df.write_csv(path, separator="\t")
        elif fmt == "excel":
            df.write_excel(path)
        elif fmt == "json":
            path.write_text(json.dumps(df.to_dicts(), default=str, indent=2))
        elif fmt == "ndjson":
            df.write_ndjson(path)
        else:
            raise ValueError(f"export_to_file: unknown format '{fmt}'")

        return PolarsResult(
            output=df,
            artifacts=[{
                "kind": "file",
                "format": fmt,
                "path": str(path),
                "rows": df.height,
                "size": path.stat().st_size if path.exists() else None,
            }],
        )


step = ExportToFileStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
