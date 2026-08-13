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


# Database extensions a pipeline output must never target. Matched casefolded.
_DB_SUFFIXES = frozenset({".sqlite", ".sqlite3", ".db", ".duckdb", ".ddb"})
# Sidecars — truncating a WAL/journal corrupts the database as surely as
# truncating the main file.
_DB_SIDECARS = ("-wal", "-shm", "-journal", ".wal")


def _is_within(candidate: Path, root: Path) -> bool:
    """True when ``candidate`` is inside ``root``, tolerant of the ways a real
    filesystem differs from a string comparison.

    Three normalisations, because each one alone was bypassable:
      * the root is ``resolve()``d, so a symlinked ``uploads/`` still matches;
      * ``samefile`` catches hardlinks/aliases for paths that already exist;
      * the textual prefix check is casefolded, so ``UPLOADS`` matches
        ``uploads`` on case-insensitive volumes (macOS ships one by default).

    Erring toward "inside" is intentional — a false positive refuses a write,
    a false negative destroys user data.
    """
    try:
        root_resolved = root.resolve(strict=False)
    except OSError:
        root_resolved = root

    # Exact / symlink-aware containment first.
    for base in {root, root_resolved}:
        try:
            candidate.relative_to(base)
            return True
        except ValueError:
            pass

    # Same directory reached by a different name (alias, hardlink, case).
    for base in {root, root_resolved}:
        if base.exists():
            for parent in (candidate, *candidate.parents):
                try:
                    if parent.exists() and parent.samefile(base):
                        return True
                except OSError:
                    break

    # Casefolded prefix — the case-insensitive-volume case.
    cand_s = os.path.normcase(str(candidate)).casefold()
    for base in {root, root_resolved}:
        base_s = os.path.normcase(str(base)).casefold().rstrip(os.sep)
        if cand_s == base_s or cand_s.startswith(base_s + os.sep):
            return True
    return False


def _protected_input_roots() -> list[Path]:
    """Directories that hold user INPUT data and DIG's own catalog.

    Nothing DIG writes as pipeline output may ever land here. ``uploads/``
    holds the user's original source files; ``datasets/`` holds the ingested
    parquet those files were turned into; the sqlite catalog holds every
    Pipeline, Dataset, and setting.
    """
    from dig.storage.files import data_dir

    try:
        root = data_dir().resolve()
    except OSError:
        return []
    return [root / "uploads", root / "datasets"]


def assert_write_target_safe(uri_or_path: str, *, allow_database: bool = False) -> Path:
    """Resolve a WRITE target and refuse anything that would clobber input
    data, the ingested dataset cache, or DIG's catalog database.

    Read-safety (``assert_local_path_safe``) is not sufficient for writes:
    its allow-list is the whole of ``data_dir()``, which *contains*
    ``uploads/`` — so a sink URI pointing at a user's own source file passes
    the read check and then truncates the file in place. "Input data is
    sacred" (docs/ADMINISTRATION.md) has to be enforced where the bytes are
    written, not only where they're read.

    The protected roots are rejected **unconditionally** — the
    ``DIG_EXPORT_ALLOW_ABSOLUTE`` hatch widens where output may go, it never
    licenses destroying an input. Outside those roots the usual write
    allow-list applies (anything under ``data_dir()``), with the hatch
    permitting arbitrary absolute destinations on a trusted host.

    Raises:
        ValueError: if the target is a protected input path, or is outside
            the allowed roots without the escape hatch.
    """
    if uri_or_path.startswith("file://"):
        raw = urlparse(uri_or_path).path
    else:
        raw = uri_or_path

    # Embedded-engine JDBC URLs name a local file: `jdbc:sqlite:/path/to.db`.
    # Strip the prefix so the containment checks below see a real path rather
    # than treating the whole string as a relative filename.
    low = raw.lower()
    for prefix in ("jdbc:sqlite:", "jdbc:duckdb:", "jdbc:h2:file:", "jdbc:h2:", "jdbc:derby:"):
        if low.startswith(prefix):
            raw = raw[len(prefix):]
            break

    try:
        path = Path(raw).expanduser().resolve(strict=False)
    except OSError as e:
        raise ValueError(f"unsafe write path {raw!r}: {e}") from e

    # 1. Never write into the sacred input/catalog roots, hatch or not.
    #
    #    Compare CASE-INSENSITIVELY and against RESOLVED roots. `relative_to`
    #    is an exact, case-sensitive, symlink-unaware string comparison, while
    #    the candidate has already been `resolve()`d — so guard and filesystem
    #    normalised differently. On a case-insensitive volume (APFS/macOS by
    #    default, NTFS) `data/UPLOADS/x.csv` slipped past the check and the
    #    write then landed on the real `data/uploads/x.csv`; likewise a
    #    symlinked `uploads/` resolved to a path the unresolved root no longer
    #    prefixed. Casefolding is deliberately over-broad: refusing a
    #    genuinely distinct `UPLOADS/` on a case-sensitive volume costs
    #    nothing, while allowing one destroys the user's source data.
    for protected in _protected_input_roots():
        if _is_within(path, protected):
            raise ValueError(
                f"refusing to write to {raw!r}: {protected} holds source data that DIG "
                "never overwrites. Point the output at data/outputs/ or a path outside "
                "the DIG data directory."
            )

    # 2. Never write over a database file — the catalog or any other. Matched
    #    case-insensitively, and covering the sidecars SQLite/DuckDB create
    #    (`-wal`, `-shm`, `-journal`), since truncating those corrupts the
    #    database just as effectively as truncating the main file.
    name = path.name.casefold()
    suffix = path.suffix.casefold()
    # DIG's own catalog is never a valid write target, not even for a step
    # whose whole job is writing databases.
    if name.startswith("dig.sqlite"):
        raise ValueError(
            f"refusing to write to {raw!r}: that is DIG's own catalog database."
        )
    # `allow_database=True` is for export_to_db, which legitimately creates
    # SQLite/DuckDB files. Everything else writing a .db is a mistake.
    if not allow_database and (
        suffix in _DB_SUFFIXES or any(name.endswith(sidecar) for sidecar in _DB_SIDECARS)
    ):
        raise ValueError(
            f"refusing to write to {raw!r}: that is a database file, not a pipeline output."
        )

    # 3. Beyond that, writes follow the same allow-list as reads. The write
    #    hatch is DIG_EXPORT_ALLOW_ABSOLUTE (matching export_to_file), NOT
    #    the read-oriented DIG_LOCAL_FILE_ALLOW_ABSOLUTE.
    if os.environ.get("DIG_EXPORT_ALLOW_ABSOLUTE") == "1":
        return path

    roots = _allowed_roots()
    for root in roots:
        try:
            path.relative_to(root)
            return path
        except ValueError:
            continue

    raise ValueError(
        f"write path {raw!r} is outside the allowed roots ({', '.join(str(r) for r in roots)}). "
        "Set DIG_EXPORT_ALLOW_ABSOLUTE=1 to permit writing outside the DIG data directory "
        "on a trusted single-tenant host."
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
