"""Static lint for AI-generated Python plugin code.

This is the load-bearing security check before any LLM-emitted plugin is
installed. The user has already explicitly confirmed they want the
generated plugin (via the diff-review UI), but they're not expected to
spot-check every import — so we enforce a small, well-defined sandbox
of what plugin code is allowed to do.

The lint is conservative on purpose: false positives are easy to fix
(rename a variable, restructure the code) but false negatives ship
exploit-able plugins.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass


# Modules a connector / step plugin is allowed to import. Stdlib is on
# the narrow side — most plugins only need a handful of stdlib modules
# plus polars + httpx.
_ALLOWED_TOP_MODULES = frozenset({
    # Stdlib (data + IO that's safe enough for plugins)
    "json",
    "re",
    "math",
    "hashlib",
    "base64",
    "datetime",
    "typing",
    "collections",
    "dataclasses",
    "functools",
    "itertools",
    "pathlib",
    "io",
    "csv",
    "decimal",
    "fractions",
    "uuid",
    "logging",
    "enum",
    "abc",
    # Approved third-party
    "polars",
    "httpx",
    # DIG itself (limited surface)
    "dig",
})

# Specific submodules that are allowed even though their parent isn't (or
# would otherwise expose more surface than we want). `urllib.parse` is fine
# (URL helpers, no IO); `urllib.request` is NOT (urlopen lets a plugin do
# arbitrary HTTP including file://, bypassing the httpx allowlist).
_ALLOWED_DOTTED_IMPORTS = frozenset({
    "urllib.parse",
})


# Names that, if used as function calls or attribute accesses anywhere in
# the AST, immediately fail the lint. These are categorically dangerous
# in user-installed plugin code.
_BANNED_NAMES = frozenset({
    # Code execution
    "eval", "exec", "compile", "__import__",
    # Process spawn
    "system", "popen", "spawn", "Popen", "call", "check_call", "check_output",
    "run", "fork",
    # Pickle / shelve — code-execution channels
    "pickle", "loads", "load", "dumps", "dump",
    "shelve", "marshal", "dill", "cloudpickle",
    # Sockets / raw networking outside the urllib + httpx allow path
    "socket", "ssl",
    # Filesystem destruction
    "rmtree", "unlink", "remove", "rmdir",
    # os module surface that isn't strictly needed for plugins
    "chmod", "chown", "setuid", "setgid", "execv", "execve", "execvp",
    # Reflection that defeats the lint
    "globals", "locals", "vars", "getattr", "setattr", "delattr",
    "__subclasses__", "__bases__", "__mro__", "__class__", "mro",
    # Dunder objects whose subscript / attribute access can defeat the lint:
    # __builtins__["eval"], __loader__.exec_module, __spec__.loader, etc.
    "__builtins__", "__loader__", "__spec__", "__module__", "__globals__",
    "__code__", "__closure__", "__dict__", "__qualname__",
    # urllib.request escape hatches (we allow urllib.parse only)
    "urlopen", "urlretrieve", "Request", "build_opener", "install_opener",
    # Round-4 SEC-1 #2 — Polars sandbox bypass.
    # Plugins receive their input data as pre-loaded DataFrames via the
    # `inputs: dict[str, pl.DataFrame]` argument. They should never do
    # their own filesystem / network IO. Without these bans, an
    # AI-generated plugin could call `pl.read_csv("/etc/passwd")` to
    # exfiltrate local files, `pl.read_csv("http://attacker/")` to do
    # SSRF without going through our hardened REST connector, or
    # `pl.read_database("sqlite:///../data/secrets.db", ...)` to reach
    # other tenants' data. Sink/write methods are blocked for the same
    # reason — write_csv("/tmp/exfil") lets the plugin stash files
    # outside its run-output directory. `register_io_plugin` lets a
    # plugin install an arbitrary IO driver; categorically banned.
    "read_csv", "read_parquet", "read_ipc", "read_ipc_stream",
    "read_json", "read_ndjson", "read_avro", "read_excel",
    "read_database", "read_database_uri", "read_delta", "read_iceberg",
    "scan_csv", "scan_parquet", "scan_ipc", "scan_ndjson",
    "scan_delta", "scan_iceberg", "scan_pyarrow_dataset",
    "write_csv", "write_parquet", "write_ipc", "write_ipc_stream",
    "write_json", "write_ndjson", "write_avro", "write_excel",
    "write_database", "write_delta",
    "sink_csv", "sink_parquet", "sink_ipc", "sink_ndjson",
    "register_io_plugin",
    # Pandas pulls in the same IO surface; if a plugin smuggles pandas
    # in via `import polars; polars.from_pandas(pandas.read_csv(...))`
    # the read_csv attr-access still triggers above (pandas exposes the
    # same names).
})


# Banned full module paths (regardless of how they're imported).
_BANNED_MODULES = frozenset({
    "os", "subprocess", "shutil", "sys", "ctypes", "multiprocessing",
    "threading", "_thread", "asyncio.subprocess", "platform",
    "pickle", "shelve", "marshal", "dill", "cloudpickle",
    "socket", "ssl", "select",
    "importlib", "pkgutil", "runpy", "code", "codeop",
    "tempfile",  # writing arbitrary temp files isn't needed for connectors
})


@dataclass
class LintIssue:
    """One reason the code was rejected. `node` is the AST node that
    triggered the issue; we surface line/column for the UI to highlight."""
    line: int
    col: int
    rule: str
    message: str


def lint_plugin_python(source: str) -> list[LintIssue]:
    """Walk the AST of generated plugin code and return all issues found.
    Empty list = lint passed.

    Doesn't execute anything. Doesn't import anything. Pure static analysis.
    """
    issues: list[LintIssue] = []

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return [LintIssue(
            line=e.lineno or 0,
            col=e.offset or 0,
            rule="syntax",
            message=f"Python syntax error: {e.msg}",
        )]

    for node in ast.walk(tree):
        # ── Imports ────────────────────────────────────────────────────
        if isinstance(node, ast.Import):
            for alias in node.names:
                full = alias.name
                top = full.split(".", 1)[0]
                if full in _BANNED_MODULES or top in _BANNED_MODULES:
                    issues.append(LintIssue(
                        node.lineno, node.col_offset, "banned_import",
                        f"Import of '{full}' is not allowed in plugins.",
                    ))
                elif full in _ALLOWED_DOTTED_IMPORTS:
                    pass  # explicitly allowed submodule (e.g. urllib.parse)
                elif top not in _ALLOWED_TOP_MODULES:
                    issues.append(LintIssue(
                        node.lineno, node.col_offset, "unknown_import",
                        f"Import of '{full}' is not in the plugin allow-list "
                        f"({sorted(_ALLOWED_TOP_MODULES)}).",
                    ))
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            top = mod.split(".", 1)[0]
            if mod in _BANNED_MODULES or top in _BANNED_MODULES:
                issues.append(LintIssue(
                    node.lineno, node.col_offset, "banned_import",
                    f"Import from '{mod}' is not allowed in plugins.",
                ))
            elif mod in _ALLOWED_DOTTED_IMPORTS:
                pass  # urllib.parse — fine
            elif top not in _ALLOWED_TOP_MODULES:
                issues.append(LintIssue(
                    node.lineno, node.col_offset, "unknown_import",
                    f"Import from '{mod}' is not in the plugin allow-list.",
                ))
            else:
                # `from urllib import request` — top is allowed but the
                # imported name is a banned submodule. Walk the names.
                for alias in node.names:
                    if f"{top}.{alias.name}" in _BANNED_MODULES:
                        issues.append(LintIssue(
                            node.lineno, node.col_offset, "banned_import",
                            f"Import from '{mod}' of '{alias.name}' "
                            "exposes a banned surface.",
                        ))

        # ── Banned names (function calls, attribute access) ────────────
        if isinstance(node, ast.Call):
            fn_name = _call_name(node.func)
            if fn_name and _final_segment(fn_name) in _BANNED_NAMES:
                issues.append(LintIssue(
                    node.lineno, node.col_offset, "banned_call",
                    f"Call to '{fn_name}' is not allowed in plugins.",
                ))

        if isinstance(node, ast.Attribute):
            if node.attr in _BANNED_NAMES:
                issues.append(LintIssue(
                    node.lineno, node.col_offset, "banned_attribute",
                    f"Attribute '{node.attr}' is not allowed in plugins.",
                ))

        if isinstance(node, ast.Name):
            if node.id in _BANNED_NAMES:
                issues.append(LintIssue(
                    node.lineno, node.col_offset, "banned_name",
                    f"Name '{node.id}' is not allowed in plugins.",
                ))

        # ── Subscript access on banned names ──────────────────────────
        # Catches __builtins__["eval"], __builtins__['exec'], etc. — the
        # AST is Subscript(value=Name('__builtins__'), slice=Constant("eval")).
        # Also catches obj.__dict__['__builtins__'] via the attribute walker.
        if isinstance(node, ast.Subscript):
            base = node.value
            if isinstance(base, ast.Name) and base.id in _BANNED_NAMES:
                issues.append(LintIssue(
                    node.lineno, node.col_offset, "banned_subscript",
                    f"Subscript access on '{base.id}' is not allowed (sandbox bypass).",
                ))

    return issues


def _call_name(node: ast.AST) -> str | None:
    """Render a Call's `func` AST as a dotted name string, or None."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return None


def _final_segment(dotted: str) -> str:
    return dotted.rsplit(".", 1)[-1]
