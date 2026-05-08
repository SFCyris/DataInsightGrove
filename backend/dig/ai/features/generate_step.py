"""Generate a DIG transform step from a natural-language description.

Workflow mirrors generate_connector:
  1. (frontend) User describes what the step should do, optionally with
     the schema of the column(s) it operates on
  2. backend: generate() asks the LLM for {manifest_json, step_py}
  3. backend: lint the step_py (dig/ai/safety.py — same allowlist as
     connectors)
  4. (frontend) Review diff, click Install
  5. backend: install_pending_step() moves files into plugins/steps/

The few-shot example uses the existing `array_length` step — small enough
to fit in the prompt and exercises the canonical Step contract
(to_sql + infer_schema). For Polars-engine steps the model can override
to use execute_polars instead.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.ai.client import AiConfig, AiError, chat
from dig.ai.parsing import parse_json_lenient
from dig.ai.prompts import TOKEN_BUDGETS
from dig.ai.safety import lint_plugin_python


_FEW_SHOT_ARRAY_LENGTH = '''\
# Example transform step — counts array elements. Use this as the
# structural template. For computations that don't fit DuckDB SQL,
# override execute_polars instead of to_sql.

# manifest.json
{
  "id": "array_length",
  "version": "1.0.0",
  "label": "📏 Array length",
  "description": "Add a column with the length of an array column.",
  "category": "derive",
  "engine": { "primary": "sql", "browser": "sql", "deterministic": true },
  "io": {
    "inputs": { "min": 1, "max": 1, "ports": ["in"] },
    "outputs": { "min": 1, "max": 1, "ports": ["out"] }
  },
  "params": {
    "column": { "type": "column_ref", "label": "Array column", "columnFrom": "in", "required": true },
    "outputColumn": { "type": "string", "label": "Output column name", "required": true }
  },
  "preview": { "rowImpact": "preserves", "schemaImpact": "modifies" },
  "tags": ["array", "length"]
}

# step.py
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from dig.engine.step import Step, quote_ident

class ArrayLengthStep(Step):
    def to_sql(self, params, inputs):
        src = inputs["in"]
        col = params["column"]
        out = params["outputColumn"]
        return f"SELECT *, len({quote_ident(col)}) AS {quote_ident(out)} FROM {src}"

    def infer_schema(self, input_schemas, params):
        s = dict(input_schemas.get("in", {}))
        out = params.get("outputColumn")
        if out:
            s[str(out)] = "integer"
        return s

step = ArrayLengthStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
'''


_SYSTEM = """\
You generate DataInsightGrove (DIG) transform-step plugins from natural language.

A DIG step is a Python module whose `to_sql(params, inputs)` returns a SQL
SELECT statement, OR whose `execute_polars(inputs, params)` returns a
PolarsResult. Most simple transforms are SQL — only fall back to Polars
when the operation can't be expressed as a SQL fragment.

Output strictly the following JSON (no Markdown, no code fences, no prose):

{
  "id": "<lowercase_snake_case_id>",
  "label": "<emoji + Title Case label>",
  "description": "<one-sentence description>",
  "manifest_json": <the manifest.json content as a JSON object>,
  "step_py": "<the full step.py source as a JSON string>"
}

Constraints on step.py:
  - Allowed imports: json, re, math, hashlib, base64, datetime, typing,
    pathlib, urllib.parse, polars, dig.engine.step.
  - DO NOT import: os, subprocess, shutil, sys, ctypes, socket, ssl,
    pickle, multiprocessing, threading, importlib, runpy, tempfile,
    urllib.request.
  - DO NOT call: eval, exec, compile, __import__, getattr/setattr/delattr,
    globals/locals/vars, os.system.
  - Define exactly one class subclassing dig.engine.step.Step.
  - For SQL steps: implement `to_sql(params, inputs) -> str` returning ONE
    SELECT statement. ALWAYS use quote_ident(col) for any user-supplied
    column name interpolated into SQL. ALWAYS use quote_str(s) for any
    user-supplied string literal. Never concatenate raw strings into SQL.
  - For Polars steps: implement `execute_polars(inputs, params, ctx) -> PolarsResult`.
    inputs is dict[port_name -> pl.DataFrame]; return PolarsResult(output=df).
  - Implement infer_schema(input_schemas, params) when the step adds, drops,
    renames, or retypes columns.
  - The last line must instantiate `step = MyStep(json.loads(...))` exactly
    as in the example.

Constraints on manifest.json:
  - category must be one of: shape, clean, derive, combine, aggregate, output, custom
  - engine.primary: "sql" if your to_sql works; "polars" if you need Polars
  - engine.browser: "sql" if your to_sql is browser-runnable (deterministic, no FS/network), "none" otherwise
  - io.inputs / io.outputs use port names matching how the user wires the step
  - Every param the step reads from `params` must be declared
"""


async def generate_step(
    cfg: AiConfig,
    *,
    description: str,
    schema_hint: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Ask the LLM for a step plugin. Returns:
      {
        "id": str,
        "manifest": dict,
        "step_py": str,
        "lint_issues": [LintIssue],
        "model": str,
      }
    Raises AiError on non-parseable response.
    """
    if not description.strip():
        raise AiError("description is required")

    user_parts = [f"User description: {description.strip()}"]
    if schema_hint:
        cols = "\n".join(f"  {n}: {t}" for n, t in sorted(schema_hint.items()))
        user_parts.append(f"Available columns at the input port:\n{cols}")
    user_parts.append("\nFew-shot example:")
    user_parts.append(f"```\n{_FEW_SHOT_ARRAY_LENGTH}\n```")
    user_parts.append("\nGenerate the JSON now.")

    # Two-phase chat — same fallback as the suggestor features.
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]
    last_err: AiError | None = None
    resp = None
    for use_json_format in (True, False):
        try:
            resp = await chat(
                cfg,
                messages=messages,
                response_format="json_object" if use_json_format else None,
                temperature=0.1,
                max_tokens=TOKEN_BUDGETS["generate_step"],
            )
            break
        except AiError as e:
            last_err = e
            if "empty message" not in str(e).lower():
                raise
    if resp is None:
        raise AiError(str(last_err) if last_err else "AI returned no content")

    parsed = parse_json_lenient(resp.text)
    if parsed is None:
        raise AiError(f"AI returned non-JSON: {resp.text[:300]}")

    required = {"id", "manifest_json", "step_py"}
    missing = required - set(parsed.keys())
    if missing:
        raise AiError(f"AI response missing keys: {missing}")

    step_py = str(parsed["step_py"])
    issues = lint_plugin_python(step_py)

    return {
        "id": str(parsed["id"]),
        "label": parsed.get("label"),
        "description": parsed.get("description"),
        "manifest": parsed["manifest_json"],
        "step_py": step_py,
        "lint_issues": [
            {"line": i.line, "col": i.col, "rule": i.rule, "message": i.message}
            for i in issues
        ],
        "model": resp.model,
    }


# ── Pending / install plumbing — same shape as generate_connector ──


def _validate_step_id(sid: Any) -> str:
    """Reject anything unsafe to use as a single path segment."""
    if not isinstance(sid, str) or not sid:
        raise ValueError("step_id must be a non-empty string")
    if len(sid) > 64:
        raise ValueError("step_id too long (max 64 chars)")
    if not sid.replace("_", "").isalnum():
        raise ValueError(
            f"invalid step id: {sid!r} — must be snake_case alphanumeric "
            "(a-z 0-9 _ only)",
        )
    return sid


def _safe_path_under(root: Path, *segments: str) -> Path:
    p = root.joinpath(*segments).resolve()
    try:
        p.relative_to(root.resolve())
    except ValueError as e:
        raise ValueError(f"path escapes root: {p}") from e
    return p


def _pending_step_dir(repo_root: Path, step_id: str) -> Path:
    sid = _validate_step_id(step_id)
    return _safe_path_under(repo_root, "plugins", "_pending", "steps", sid)


def _installed_step_dir(repo_root: Path, step_id: str) -> Path:
    sid = _validate_step_id(step_id)
    return _safe_path_under(repo_root, "plugins", "steps", sid)


def stage_pending_step(repo_root: Path, step: dict[str, Any]) -> Path:
    sid = _validate_step_id(step.get("id"))
    pending_dir = _pending_step_dir(repo_root, sid)
    pending_dir.mkdir(parents=True, exist_ok=True)
    (pending_dir / "manifest.json").write_text(json.dumps(step["manifest"], indent=2))
    (pending_dir / "step.py").write_text(step["step_py"])
    return pending_dir


def install_pending_step(repo_root: Path, step_id: str) -> Path:
    src = _pending_step_dir(repo_root, step_id)
    dst = _installed_step_dir(repo_root, step_id)
    if not src.exists():
        raise FileNotFoundError(f"pending step {step_id!r} not found")
    if dst.exists():
        for fname in ("manifest.json", "step.py"):
            sf, df = src / fname, dst / fname
            if not df.exists() or sf.read_bytes() != df.read_bytes():
                raise FileExistsError(
                    f"step {step_id!r} already installed with different contents",
                )
        import shutil as _sh
        _sh.rmtree(src)
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    return dst


def discard_pending_step(repo_root: Path, step_id: str) -> None:
    src = _pending_step_dir(repo_root, step_id)
    if src.exists():
        import shutil as _sh
        _sh.rmtree(src)
