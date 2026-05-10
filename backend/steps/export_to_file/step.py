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

        # Pipeline docs are user-supplied (template clones, imports). An
        # absolute `path` or a `..`-laden relative path would let a malicious
        # pipeline write anywhere the API process can reach. Constrain the
        # write under `ctx.out_dir` (the run's artifact directory). The
        # `DIG_EXPORT_ALLOW_ABSOLUTE=1` escape hatch matches the same pattern
        # the REST connector uses (`DIG_REST_ALLOW_PRIVATE`) — set
        # deliberately on a trusted host, never default.
        import os as _os

        allow_abs = _os.environ.get("DIG_EXPORT_ALLOW_ABSOLUTE") == "1"
        path_param = (params.get("path") or "").strip()
        base = (ctx.out_dir if ctx is not None else Path.cwd()).resolve()
        if path_param:
            candidate = Path(path_param).expanduser()
            if not allow_abs:
                if candidate.is_absolute() or any(part == ".." for part in candidate.parts):
                    raise ValueError(
                        "export_to_file: path must be a relative basename inside "
                        "the run output directory (set DIG_EXPORT_ALLOW_ABSOLUTE=1 "
                        "to permit absolute paths on a trusted host)."
                    )
                path = (base / candidate).resolve()
                try:
                    path.relative_to(base)
                except ValueError as e:
                    raise ValueError(
                        "export_to_file: refusing to write outside the run output directory"
                    ) from e
            else:
                path = candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve()
        else:
            path = (base / f"export-{self.id}{ext}").resolve()
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
