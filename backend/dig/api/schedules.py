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

import asyncio
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

# Serialises crontab mutations. The script's add/remove paths are a
# read-modify-write of the whole crontab (`crontab -l | … | crontab -`),
# so two concurrent mutating requests could each read the same starting
# crontab and the second write would silently drop the first one's
# change. Reads (list) don't need the lock.
_crontab_lock = asyncio.Lock()


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
    # Pen-tester round-3: previously this was gated on `.isdigit()` for both
    # fields, so any non-digit shape (range / step / list) bypassed the
    # check entirely. Now expand each field to its concrete integer set
    # and check every (dom, mon) combination. Also fix the Feb cap from
    # 30 → 29 so Feb-29-on-non-leap-years (which never fires either) is
    # caught when the cron pinned Feb 29 explicitly.
    dom_field = fields[2]
    mon_field = fields[3]
    impossible = {4: 31, 6: 31, 9: 31, 11: 31, 2: 30}  # max-day per month (Feb=30 means "no 30 or 31"; Feb 29 is leap-only and cron auto-skips non-leap)
    try:
        dom_set = _expand_cron_field(dom_field, lo=1, hi=31)
        mon_set = _expand_cron_field(mon_field, lo=1, hi=12)
    except ValueError:
        # Already validated for shape above; if expansion fails, let the
        # existing raise surface elsewhere.
        return " ".join(fields)
    # If EVERY combination in the cartesian product is impossible, the cron
    # genuinely never fires. (Some-impossible-some-fine is fine; cron will
    # skip the impossible ones.)
    if dom_set and mon_set:
        any_possible = False
        for mon in mon_set:
            max_day = impossible.get(mon, 31)
            for dom in dom_set:
                if dom <= max_day:
                    any_possible = True
                    break
            if any_possible:
                break
        if not any_possible:
            raise ValueError(
                f"cron expression {' '.join(fields)!r} can never fire — "
                f"every (day {sorted(dom_set)}, month {sorted(mon_set)}) "
                f"combination is impossible"
            )
    return " ".join(fields)


def _expand_cron_field(field: str, *, lo: int, hi: int) -> set[int]:
    """Expand a cron field shape (digit, *, range, step, list) to its
    concrete set of integer values within [lo, hi]. Returns an empty set
    for `*` (meaning "all values" — caller should treat as the full range).
    """
    out: set[int] = set()
    if field == "*":
        return set(range(lo, hi + 1))
    for token in field.split(","):
        token = token.strip()
        if not token:
            continue
        # Strip step (after `/`)
        step = 1
        if "/" in token:
            base, _, step_s = token.partition("/")
            step = int(step_s)
            if step < 1:
                raise ValueError(f"cron step must be >= 1; got {step}")
            token = base
        # Range or scalar
        if token == "*":
            tlo, thi = lo, hi
        elif "-" in token:
            tlo_s, _, thi_s = token.partition("-")
            tlo, thi = int(tlo_s), int(thi_s)
        else:
            tlo = thi = int(token)
        if tlo > thi:
            raise ValueError(f"cron range {tlo}-{thi} reversed")
        for v in range(tlo, thi + 1, step):
            if lo <= v <= hi:
                out.add(v)
    return out


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


async def _run_script(args: list[str]) -> tuple[int, str, str]:
    """Run dig-schedule.sh with the given args; return (rc, stdout, stderr).

    The blocking subprocess call runs in a worker thread so the crontab
    round-trip (up to the 10s timeout) never stalls the event loop.
    """
    if not _SCRIPT.exists():
        raise HTTPException(500, f"scheduler script not found at {_SCRIPT}")
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
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

    async with _crontab_lock:
        rc, out, err = await _run_script(args)
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
    rc, out, err = await _run_script(["list"])
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
        # Round-4 QA finding: previously ``rest.find("# DIG_SCHED:")`` picked
        # the FIRST occurrence anywhere in the trailing string. A crontab
        # line whose command argument quoted ``"# DIG_SCHED:fake"`` would
        # produce a bogus pipeline_id while the real marker stayed
        # unparsed — UI-side DELETE then failed the ULID check, leaving
        # the real schedule un-removable via the API.
        #
        # The marker we write is always at the END of the line (see
        # ``dig-schedule.sh`` add path: ``... # DIG_SCHED:<pid>``), so the
        # right slice is the LAST occurrence, and the pid we accept must
        # match the same shape ``_validate_pipeline_id`` enforces.
        marker_idx = rest.rfind("# DIG_SCHED:")
        pid_raw = (
            rest[marker_idx + len("# DIG_SCHED:"):].strip()
            if marker_idx >= 0 else ""
        )
        # Strip anything after the first whitespace — defensive.
        pid_raw = pid_raw.split()[0] if pid_raw else ""
        # If the parsed pid doesn't match the validator's shape, surface
        # the row but mark it unknown so the UI doesn't claim to be able
        # to manage it.
        # ULID Crockford base32 is uppercase-canonical and case-insensitive;
        # the crontab marker is stored lowercased, so normalize before the
        # uppercase-only validator (this round-trips with the DELETE path).
        pid_raw = pid_raw.upper()
        try:
            pid = _validate_pipeline_id(pid_raw)
        except ValueError:
            pid = "?"
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

    async with _crontab_lock:
        rc, out, err = await _run_script(["remove", pid])
    if rc != 0:
        raise HTTPException(500, f"scheduler remove failed: {err.strip() or out.strip()}")
    return {"ok": True}
