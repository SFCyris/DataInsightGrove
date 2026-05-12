"""Track the last-booted DIG version + run schema upgrades on transitions.

The contract:

  - On every boot, we read ``data/.installed_version`` (a tiny text file
    written by ``upgrade.sh`` after a successful upgrade).
  - We compare it to the running package's ``__version__``.
  - If they differ, we run the additive schema patches (already run
    unconditionally by ``init_db`` — this hook just *records* the
    transition + emits a telemetry event so the UI can show
    "upgraded from X to Y" once).
  - We rewrite the marker file to the current version so the next boot
    sees no transition.

We deliberately do NOT block startup or fail loudly on transition —
``init_db``'s additive ALTER TABLE patches are already idempotent. This
module is the "did we just upgrade?" signal, not the migration engine.

Future: when proper Alembic-style migrations land, this is the hook
that drives them — read prior version, find migration scripts whose
range covers (prior, current], apply in order.
"""
from __future__ import annotations

import logging
from typing import Final

from dig.storage.files import data_dir

log = logging.getLogger(__name__)

_VERSION_FILE_NAME: Final = ".installed_version"


def read_last_installed_version() -> str | None:
    """Return the version recorded on the prior boot, or None on a fresh install."""
    path = data_dir() / _VERSION_FILE_NAME
    if not path.exists():
        return None
    try:
        v = path.read_text(encoding="utf-8").strip()
        return v or None
    except OSError:
        log.exception("could not read %s", path)
        return None


def write_installed_version(version: str) -> None:
    """Record the current version. Best-effort — failures are logged, not raised."""
    path = data_dir() / _VERSION_FILE_NAME
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(version + "\n", encoding="utf-8")
    except OSError:
        log.exception("could not write %s", path)


async def detect_and_record_version_transition() -> tuple[str | None, str]:
    """Compare the boot version to the previous boot's marker; emit an event
    on a transition and update the marker.

    Returns (prior, current). ``prior`` is None on a fresh install.
    Safe to call from the FastAPI lifespan startup hook — every step is
    best-effort and never raises.
    """
    from dig import __version__

    current = __version__
    prior = read_last_installed_version()

    if prior is None:
        log.info("first boot at version %s (no prior marker)", current)
    elif prior != current:
        log.info("version transition: %s -> %s", prior, current)
        try:
            from dig.api.events import EventKinds, emit_event
            await emit_event(
                EventKinds.SYSTEM_STARTUP,
                version=current,
                prior_version=prior,
                upgrade=True,
                level="notification",
            )
        except Exception:
            log.exception("failed to emit upgrade event for %s -> %s", prior, current)
    else:
        log.debug("version unchanged at %s", current)

    write_installed_version(current)
    return prior, current
