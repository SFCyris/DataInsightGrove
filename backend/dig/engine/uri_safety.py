"""Shared URI-safety checks for file-based connectors.

Pen-tester finding (round 2): file-based connectors (csv, feather, excel,
hdf5, …) accepted ``file:///etc/passwd`` URIs and read them into datasets,
giving any authenticated user an arbitrary-file-read primitive on the
backend host. The fix is a central allow-list applied by every file-based
connector before it touches the path.

Allowed paths (when ``DIG_LOCAL_FILE_ALLOW_ABSOLUTE`` is unset):
  1. Anything under the configured ``data_dir()`` — uploads, cached parquet,
     run outputs. This is where DIG legitimately writes user data.
  2. Anything under the bundled ``<repo>/samples/`` folder — the
     "Try with sample data" flow needs to read these on import.

Anything else (``/etc/passwd``, ``~/.ssh/...``, AI-provider API keys
stored in ``data/dig.sqlite``, etc.) raises ``ValueError`` before the
connector ever opens the file.

Bypass (set deliberately on a trusted single-tenant host):
  ``DIG_LOCAL_FILE_ALLOW_ABSOLUTE=1`` — this is the same shape as the
  existing ``DIG_REST_ALLOW_PRIVATE`` and ``DIG_EXPORT_ALLOW_ABSOLUTE``
  escape hatches, so the operator can opt back into the unconstrained
  pre-fix behaviour deliberately.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse


def _allowed_roots() -> list[Path]:
    """Directories the connector is allowed to read from / write to.

    Resolved (symlinks-followed) so a symlink inside an allowed root that
    points at ``/etc`` doesn't sneak through. We also resolve paths the
    same way before the prefix check.
    """
    from dig.storage.files import data_dir

    roots: list[Path] = []
    try:
        roots.append(data_dir().resolve())
    except OSError:
        pass

    # Bundled samples — the "Try with sample data" flow needs to read these.
    repo_root = Path(__file__).resolve().parents[2]
    samples_dir = (repo_root / "samples").resolve()
    if samples_dir.is_dir():
        roots.append(samples_dir)

    # Repo-bundled templates dir (for plugin packs reading their own files).
    templates_dir = (repo_root / "samples" / "templates").resolve()
    if templates_dir.is_dir():
        roots.append(templates_dir)

    return roots


def assert_local_path_safe(uri_or_path: str) -> Path:
    """Resolve ``uri_or_path`` to a ``Path`` and reject anything outside the
    allowed roots. Returns the resolved Path on success.

    Accepts both ``file://...`` URIs and bare paths. The function is
    idempotent — calling it on the returned Path is safe.

    Raises:
        ValueError: if the path escapes the allowed roots and the
            ``DIG_LOCAL_FILE_ALLOW_ABSOLUTE`` escape hatch isn't set.
    """
    if uri_or_path.startswith("file://"):
        raw = urlparse(uri_or_path).path
    else:
        raw = uri_or_path

    # Resolve to canonical absolute form (follows symlinks). If the path
    # doesn't exist yet, ``resolve(strict=False)`` returns the closest
    # existing parent + appended tail, which is enough for the prefix
    # check.
    try:
        path = Path(raw).expanduser().resolve(strict=False)
    except OSError as e:
        raise ValueError(f"unsafe path {raw!r}: {e}") from e

    if os.environ.get("DIG_LOCAL_FILE_ALLOW_ABSOLUTE") == "1":
        return path

    roots = _allowed_roots()
    for root in roots:
        try:
            path.relative_to(root)
            return path
        except ValueError:
            continue

    raise ValueError(
        f"file path {raw!r} is outside the allowed roots ({', '.join(str(r) for r in roots)}). "
        "Set DIG_LOCAL_FILE_ALLOW_ABSOLUTE=1 to permit unconstrained file access on a "
        "trusted single-tenant host."
    )


def assert_uri_scheme_safe(uri: str, *, allowed_schemes: tuple[str, ...] = ("http", "https")) -> None:
    """Reject URIs whose scheme isn't in ``allowed_schemes``. Used by the
    HTTPS / REST connectors to block ``file://`` smuggled into a network
    connector. Default is ``http`` + ``https`` only.
    """
    parts = urlparse(uri)
    if parts.scheme.lower() not in allowed_schemes:
        raise ValueError(
            f"URI scheme {parts.scheme!r} not allowed for this connector; "
            f"permitted: {', '.join(allowed_schemes)}",
        )
