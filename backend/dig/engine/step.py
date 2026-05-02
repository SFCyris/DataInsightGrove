"""Step plugin interface.

Each step is a folder under `backend/steps/<id>/` containing:
  - manifest.json — validated against shared/schemas/step-manifest.schema.json
  - step.py      — defines a Step subclass and exports `step = MyStep(manifest)`
  - sql.py       — (optional, Phase 3) JS-runnable SQL fragments for browser parity
  - tests.py     — pytest cases with golden parquet fixtures

The to_sql contract: given input port name -> CTE alias, return the *body* of a
CTE (a SELECT statement) that produces this step's output. The executor wraps
all step SQL fragments in a single WITH clause so the entire pipeline executes
as one DuckDB query.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import polars as pl


@dataclass
class PolarsContext:
    """Per-run context handed to Polars-engine steps."""
    run_id: str
    out_dir: Path
    # Ancestor chain of pipeline IDs currently being executed — populated when
    # a sub-pipeline step recursively calls back into the executor. Used to
    # detect cycles (a sub-pipeline that references its own ancestor).
    pipeline_chain: tuple[str, ...] = ()  # data/outputs/<run_id>


@dataclass
class PolarsResult:
    """Returned by Step.execute_polars().

    `output` is the DataFrame that flows downstream (or simply the input
    passed through, for sink-style steps). `artifacts` is a free-form list of
    files / tables the step wrote — surfaced in the run record for the UI to
    show.
    """
    output: "pl.DataFrame"
    artifacts: list[dict[str, Any]] = field(default_factory=list)


class Step(ABC):
    manifest: dict[str, Any]

    def __init__(self, manifest: dict[str, Any]) -> None:
        self.manifest = manifest

    @property
    def id(self) -> str:
        return self.manifest["id"]

    @property
    def version(self) -> str:
        return self.manifest["version"]

    @property
    def label(self) -> str:
        return self.manifest["label"]

    @property
    def category(self) -> str:
        return self.manifest["category"]

    @property
    def engine_primary(self) -> str:
        return self.manifest["engine"]["primary"]

    @property
    def engine_browser(self) -> str:
        return self.manifest["engine"].get("browser", "none")

    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        """Compile this step to a SQL SELECT statement.

        Args:
          params: validated parameter values from the pipeline node
          inputs: map of port name -> upstream CTE alias (a valid SQL identifier)

        Returns: a SELECT statement (without trailing semicolon) that produces
        this step's output. Use double-quoted identifiers everywhere column or
        table names are user-supplied.

        Pure Polars / Python steps that have no SQL form should set
        `engine.primary = "polars"` in their manifest and override
        `execute_polars` instead. The default to_sql passes the input through
        unchanged so the executor can compile the upstream chain.
        """
        if not inputs:
            raise NotImplementedError(f"step '{self.id}' has no SQL form and no upstream input")
        # Pass-through: lets a Polars terminal step still compile with the SQL
        # pipeline if the executor decides to run it that way.
        first_in = next(iter(inputs.values()))
        return f"SELECT * FROM {first_in}"

    def execute_polars(
        self,
        inputs: dict[str, "pl.DataFrame"],
        params: dict[str, Any],
        ctx: "PolarsContext | None" = None,
    ) -> "PolarsResult":
        """Run this step against materialized Polars DataFrames.

        Override in subclasses with `engine.primary == "polars"`. Default
        raises NotImplementedError. Return a `PolarsResult` describing the
        output frame and any side-effect artifacts produced (file paths,
        rendered images, table names, etc.).
        """
        raise NotImplementedError(f"step '{self.id}' has no Polars implementation")

    def infer_schema(
        self,
        input_schemas: dict[str, dict[str, str]],
        params: dict[str, Any],
    ) -> dict[str, str]:
        """Infer output column name -> logical type given input schemas.

        Default: pass through the first input port unchanged. Subclasses
        override when they add, drop, rename, or retype columns.
        """
        if not input_schemas:
            return {}
        first = next(iter(input_schemas.values()))
        return dict(first)


def quote_ident(name: str) -> str:
    """Double-quote an identifier and escape embedded quotes — DuckDB-safe."""
    return '"' + name.replace('"', '""') + '"'


def quote_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


# ---- Safe-expression validator --------------------------------------------
#
# Steps that accept user-authored SQL fragments (filter_rows.predicate,
# derive_column.expression, …) MUST run their input through `assert_safe_expr`
# before interpolating it. We tokenize and reject anything that could escape
# a column-expression context: DDL/DML keywords, multi-statement separators,
# DuckDB-specific pragmas + filesystem/HTTP IO functions, comment markers.
#
# Without this, a single POST to /pipelines/.../runs is RCE-equivalent because
# DuckDB exposes ATTACH, COPY, read_csv_auto('s3://…'), …. Documented as P0 in
# docs/REVIEW_FINDINGS.md.

import re as _re

# Banned tokens — case-insensitive, word-boundary matched. The list is
# deliberately broad: when in doubt, ban it. False positives on column names
# are unlikely (you wouldn't name a column 'ATTACH') and the user can quote
# the identifier (`"attach"`) to escape the check.
_BANNED_TOKENS = frozenset({
    # multi-statement / control flow
    "begin", "commit", "rollback", "transaction",
    # DDL
    "create", "drop", "alter", "truncate", "grant", "revoke",
    # DML beyond SELECT (which we don't accept here anyway — predicates only)
    "insert", "update", "delete", "merge", "upsert",
    # DuckDB-specific dangerous surface
    "attach", "detach", "copy", "export", "import", "install", "load",
    "pragma", "set", "reset", "settings",
    # Filesystem / HTTP / cloud IO functions
    "read_csv", "read_csv_auto", "read_parquet", "read_json", "read_ndjson",
    "read_blob", "read_text", "read_xlsx", "scan_arrow_ipc",
    "write_csv", "write_parquet", "write_json",
    "parquet_scan", "csv_scan", "json_scan",
    "glob", "list_files", "stat", "directory",
    "httpfs", "https", "s3", "gcs", "azure", "fsspec",
    # System / introspection that could leak
    "system", "shell", "exec", "execute", "spawn",
    "duckdb_extensions", "duckdb_settings", "current_setting",
})

# SQL line + block comment markers (would let an attacker hide a payload).
_COMMENT_RE = _re.compile(r"--.*$|/\*.*?\*/", _re.MULTILINE | _re.DOTALL)
# Token = identifier-or-keyword. Quoted identifiers ("foo bar") are matched
# as a single token and skipped (they're columns).
_TOKEN_RE = _re.compile(r'"[^"]*"|\'(?:[^\']|\'\')*\'|[A-Za-z_][A-Za-z0-9_]*')


class UnsafeExpressionError(ValueError):
    """Raised when a user-authored SQL expression contains banned tokens."""


def assert_safe_expr(expr: str, *, kind: str = "expression") -> str:
    """Validate a user-supplied SQL expression. Returns the trimmed expression.

    Raises UnsafeExpressionError if the input contains:
      - SQL comments (`--`, `/* */`)
      - Statement separators (`;`)
      - Banned tokens (DDL, DML, file IO, attach, pragma, …)

    `kind` is used only in the error message to point the user at the right param.
    """
    if not isinstance(expr, str):
        raise UnsafeExpressionError(f"{kind} must be a string, got {type(expr).__name__}")
    e = expr.strip()
    if not e:
        return e

    # Reject SQL comments — they're a way to hide payload from a regex check.
    if _COMMENT_RE.search(e):
        raise UnsafeExpressionError(
            f"{kind} must not contain SQL comments (-- or /* */)"
        )
    # Reject multi-statement separators outright. Inside string literals is
    # fine, so we strip those before checking.
    no_strs = _re.sub(r"'(?:[^']|'')*'", "''", e)
    if ";" in no_strs:
        raise UnsafeExpressionError(
            f"{kind} must not contain ';' (single statement only)"
        )

    # Tokenize, skip quoted identifiers (columns) + string literals, check
    # remaining bare identifiers against the deny-list.
    for m in _TOKEN_RE.finditer(e):
        tok = m.group(0)
        if tok.startswith('"') or tok.startswith("'"):
            continue  # quoted ident or string literal
        if tok.lower() in _BANNED_TOKENS:
            raise UnsafeExpressionError(
                f"{kind} uses disallowed token {tok!r}. "
                "If this is a column name, quote it: \"" + tok + "\"."
            )
    return e
