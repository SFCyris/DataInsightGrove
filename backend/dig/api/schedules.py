"""Pipeline scheduling — thin wrapper around the existing dig-schedule.sh
script that manages crontab entries.

The script is the source of truth for what's scheduled (entries land in
the user's crontab tagged `# DIG_SCHED:<pipeline_id>`). The API just
shells out for add/list/remove; we don't maintain a separate DB.

Why this design: cron is already the universal scheduler on every Linux
and macOS install; building our own daemon + storage would be redundant.
The trade-off: schedules survive across DIG restarts but require the
host's cron daemon to be running.
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

router = APIRouter(prefix="/schedules", tags=["schedules"])


# 5-field cron: minute hour dom month dow. Plus DIG-style aliases.
_CRON_FIELD_RE = re.compile(r"^[\d*/,\-]+$")
_PIPELINE_ID_RE = re.compile(r"^[A-Z0-9]{26}$")  # ULID shape

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO_ROOT / "scripts" / "dig-schedule.sh"


def _validate_cron(expr: str) -> str:
    """Light validation — 5 whitespace-separated fields, allowed chars only,
    and per-field range checks so impossible expressions (Feb 31, ``*/0``,
    dow=9) get rejected up front instead of silently never firing.

    Round-3 QA finding: previously the syntax check accepted ``*/0`` (which
    crontab silently treats as never-fire) and out-of-range values like
    dow=9 or dom=32. The user thought their schedule was active.
    """
    if not isinstance(expr, str):
        raise ValueError("cron expression must be a string")
    fields = expr.strip().split()
    if len(fields) != 5:
        raise ValueError(
            f"cron expression must have exactly 5 fields (got {len(fields)}); "
            "use 'm h dom mon dow' format, e.g. '0 8 * * *' for 8am daily",
        )
    # min, max for each field
    field_ranges = [
        ("minute", 0, 59),
        ("hour", 0, 23),
        ("day-of-month", 1, 31),
        ("month", 1, 12),
        ("day-of-week", 0, 7),  # 0 and 7 both = Sunday on most cron flavours
    ]
    for f, (label, lo, hi) in zip(fields, field_ranges):
        if not _CRON_FIELD_RE.match(f):
            raise ValueError(f"cron field {f!r} has invalid characters (allowed: digits, * , / -)")
        # Validate every numeric token in the field against the range.
        # ``*`` and ``*/N`` patterns are handled separately.
        # Tokens are comma-separated.
        for token in f.split(","):
            # Step pattern: BASE/STEP. The step itself must be > 0.
            if "/" in token:
                base, step_s = token.split("/", 1)
                try:
                    step = int(step_s)
                except ValueError:
                    raise ValueError(f"cron field {f!r}: step must be an integer (got {step_s!r})")
                if step < 1:
                    raise ValueError(f"cron field {f!r}: step must be >= 1 (got {step})")
                base_token = base
            else:
                base_token = token
            # Base can be * or N or N-M.
            if base_token == "*":
                continue
            if "-" in base_token:
                lo_s, hi_s = base_token.split("-", 1)
                try:
                    lo_v, hi_v = int(lo_s), int(hi_s)
                except ValueError:
                    raise ValueError(f"cron field {f!r}: range must be N-M with integers (got {base_token!r})")
                if not (lo <= lo_v <= hi and lo <= hi_v <= hi):
                    raise ValueError(
                        f"cron {label} {base_token!r} out of range — must be {lo}..{hi}"
                    )
                if lo_v > hi_v:
                    raise ValueError(f"cron {label} range {base_token!r} reversed (lo > hi)")
            else:
                try:
                    v = int(base_token)
                except ValueError:
                    raise ValueError(f"cron field {f!r}: token must be an integer (got {base_token!r})")
                if not (lo <= v <= hi):
                    raise ValueError(
                        f"cron {label} {v!r} out of range — must be {lo}..{hi}"
                    )
    # Day-of-month / month sanity — Feb 30, Apr 31, etc.
    dom_field = fields[2]
    mon_field = fields[3]
    impossible = {"4": 31, "6": 31, "9": 31, "11": 31, "2": 30}  # max-day per month
    if dom_field.isdigit() and mon_field.isdigit():
        dom_v = int(dom_field)
        max_day = impossible.get(mon_field)
        if max_day is not None and dom_v >= max_day:
            raise ValueError(
                f"cron expression {' '.join(fields)!r} can never fire — "
                f"month {mon_field} doesn't have day {dom_v}"
            )
    return " ".join(fields)


def _validate_pipeline_id(pid: str) -> str:
    """Defends against shell injection via the pipeline-id argument."""
    if not isinstance(pid, str) or not _PIPELINE_ID_RE.match(pid):
        raise ValueError(f"invalid pipeline_id {pid!r} — must be a 26-char ULID")
    return pid


class ScheduleAddRequest(BaseModel):
    pipeline_id: str
    cron: str
    sample_rows: int | None = Field(default=None, ge=1, le=100_000_000)


class ScheduleEntry(BaseModel):
    pipeline_id: str
    cron: str
    sample_rows: int | None = None
    raw: str  # the literal crontab line for display


def _run_script(args: list[str]) -> tuple[int, str, str]:
    """Run dig-schedule.sh with the given args; return (rc, stdout, stderr)."""
    if not _SCRIPT.exists():
        raise HTTPException(500, f"scheduler script not found at {_SCRIPT}")
    try:
        proc = subprocess.run(
            [str(_SCRIPT), *args],
            capture_output=True, text=True, timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise HTTPException(504, "scheduler script timed out") from e
    return proc.returncode, proc.stdout, proc.stderr


@router.post("", response_model=ScheduleEntry, status_code=201)
async def add_schedule(body: ScheduleAddRequest) -> ScheduleEntry:
    """Add or replace a schedule for a pipeline."""
    try:
        cron = _validate_cron(body.cron)
        pid = _validate_pipeline_id(body.pipeline_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    args = ["add", cron, pid]
    if body.sample_rows is not None:
        args.extend(["--sample", str(body.sample_rows)])

    rc, out, err = _run_script(args)
    if rc != 0:
        raise HTTPException(500, f"scheduler add failed: {err.strip() or out.strip()}")

    return ScheduleEntry(
        pipeline_id=pid,
        cron=cron,
        sample_rows=body.sample_rows,
        raw=f"{cron} {pid}" + (f" --sample {body.sample_rows}" if body.sample_rows else ""),
    )


@router.get("", response_model=list[ScheduleEntry])
async def list_schedules() -> list[ScheduleEntry]:
    """List all DIG-managed crontab entries."""
    rc, out, err = _run_script(["list"])
    if rc != 0:
        raise HTTPException(500, f"scheduler list failed: {err.strip() or out.strip()}")

    entries: list[ScheduleEntry] = []
    for raw_line in out.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        # Format: <m> <h> <dom> <mon> <dow> <command...> # DIG_SCHED:<pipeline>
        cron_fields = line.split(maxsplit=5)
        if len(cron_fields) < 6:
            continue
        cron = " ".join(cron_fields[:5])
        rest = cron_fields[5]
        # Pull the pipeline id from the marker.
        marker_idx = rest.find("# DIG_SCHED:")
        pid = rest[marker_idx + len("# DIG_SCHED:"):].strip() if marker_idx >= 0 else "?"
        # Pull sample if present.
        sample: int | None = None
        m = re.search(r"--sample\s+(\d+)", rest)
        if m:
            try:
                sample = int(m.group(1))
            except ValueError:
                pass
        entries.append(ScheduleEntry(pipeline_id=pid, cron=cron, sample_rows=sample, raw=line))
    return entries


@router.delete("/{pipeline_id}")
async def remove_schedule(pipeline_id: str) -> dict[str, bool]:
    """Remove all crontab entries for the given pipeline."""
    try:
        pid = _validate_pipeline_id(pipeline_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    rc, out, err = _run_script(["remove", pid])
    if rc != 0:
        raise HTTPException(500, f"scheduler remove failed: {err.strip() or out.strip()}")
    return {"ok": True}
