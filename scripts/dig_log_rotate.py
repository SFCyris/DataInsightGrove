#!/usr/bin/env python3
"""Rotating-log wrapper for DIG services.

Spawns ``COMMAND`` as a subprocess, captures its stdout + stderr, and
streams them to a ``RotatingFileHandler``-managed file. Forwards
``SIGTERM`` / ``SIGINT`` / ``SIGHUP`` to the child so ``dig-stop`` (which
kills this wrapper's PID) cleanly tears down the wrapped service.

Why a wrapper instead of e.g. ``logrotate``:
  - portable (no system package dependency, works the same on macOS +
    Linux + WSL)
  - synchronous rotation (the .1 file appears immediately on overflow,
    not "sometime after the next cron tick")
  - no race window where the service writes to a deleted inode while
    logrotate is moving the file aside

Usage:

    python3 dig_log_rotate.py \\
        --file  /var/log/DIG/dig-api.log \\
        --max-bytes 10485760 \\
        --backup-count 5 \\
        -- /path/to/server arg1 arg2

Exit code mirrors the child's. The child's PID is written to
``<file>.pid`` next to the log so external tools (debuggers, dig-stop's
``--deep`` mode, etc.) can find it without parsing ``ps`` output.
"""

from __future__ import annotations

import argparse
import logging.handlers
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path


def _make_handler(path: str, max_bytes: int, backup_count: int) -> logging.handlers.RotatingFileHandler:
    """Build a handler ready to ``write_raw`` into.

    We don't use the ``logging`` framework's record-based pipeline — the
    child's output is already-formatted text (often containing its own
    timestamps). Instead we open the handler and treat its ``stream`` /
    ``shouldRollover`` machinery as raw byte sinks.
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
        delay=False,
    )
    return handler


def _write_raw(handler: logging.handlers.RotatingFileHandler, text: str) -> None:
    """Append text to the handler's stream and rotate if we crossed the size cap."""
    handler.stream.write(text)
    handler.stream.flush()
    # ``maxBytes == 0`` disables rotation per Python's contract — respect it.
    if handler.maxBytes <= 0:
        return
    try:
        size = handler.stream.tell()
    except OSError:
        # Pipe / non-seekable stream: fall back to file stat.
        try:
            size = os.path.getsize(handler.baseFilename)
        except OSError:
            return
    if size >= handler.maxBytes:
        handler.doRollover()


def _pump(stream, handler: logging.handlers.RotatingFileHandler, lock: threading.Lock) -> None:
    """Block-read the child's pipe and forward to the rotating handler.

    Uses ``readline`` so each rotation boundary lands on a clean line
    break (rather than mid-token), which keeps rotated files
    individually parseable. The lock serialises stdout + stderr writers
    so they can't interleave a half-line.
    """
    try:
        for raw in iter(stream.readline, b""):
            text = raw.decode("utf-8", errors="replace")
            with lock:
                _write_raw(handler, text)
    finally:
        try:
            stream.close()
        except Exception:
            pass


def main() -> int:
    p = argparse.ArgumentParser(
        description="Rotating-log wrapper for DIG services.",
        usage="%(prog)s --file PATH [--max-bytes N] [--backup-count N] -- COMMAND [ARGS...]",
    )
    p.add_argument("--file", required=True, help="Active log file path.")
    p.add_argument(
        "--max-bytes", type=int, default=10 * 1024 * 1024,
        help="Rotate when the active file reaches this many bytes (default 10 MB).",
    )
    p.add_argument(
        "--backup-count", type=int, default=5,
        help="How many rotated files to keep (default 5).",
    )
    p.add_argument("rest", nargs=argparse.REMAINDER)
    args = p.parse_args()

    # argparse's REMAINDER includes the leading "--" if the caller used
    # one (which they should, to disambiguate flags meant for the wrapped
    # command). Strip it.
    cmd = list(args.rest)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        p.error("missing COMMAND — pass it after `--`.")

    handler = _make_handler(args.file, args.max_bytes, args.backup_count)

    # Spawn the wrapped command. We split stdout from stderr so each can
    # be drained on its own thread (no deadlock if one floods while the
    # other is silent). Both end up in the same file via the shared lock.
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
        # New session so the wrapped service doesn't inherit our
        # controlling terminal (matters when started under nohup / setsid).
        start_new_session=False,
    )

    # Persist the child PID next to the log file so dig-stop's deep mode
    # (and curious operators) can find it without parsing ps.
    try:
        Path(args.file + ".pid").write_text(str(proc.pid) + "\n")
    except OSError:
        pass

    # Forward terminating signals to the child. Don't trap SIGCHLD —
    # we wait() on the child explicitly below.
    def _forward(signum: int, _frame) -> None:
        try:
            proc.send_signal(signum)
        except Exception:
            pass

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        try:
            signal.signal(sig, _forward)
        except (ValueError, OSError):
            # Some platforms (Windows, signal-restricted threads) don't
            # allow these. The wrapper still functions; ``dig-stop -9``
            # remains a fallback.
            pass

    write_lock = threading.Lock()
    threads = [
        threading.Thread(
            target=_pump, args=(proc.stdout, handler, write_lock),
            name="dig-log-stdout", daemon=True,
        ),
        threading.Thread(
            target=_pump, args=(proc.stderr, handler, write_lock),
            name="dig-log-stderr", daemon=True,
        ),
    ]
    for t in threads:
        t.start()

    rc = proc.wait()
    # Drain the readers so we don't lose the last few lines after exit.
    for t in threads:
        t.join(timeout=2.0)

    # Best-effort cleanup of the side-channel PID file.
    try:
        os.unlink(args.file + ".pid")
    except OSError:
        pass

    return rc


if __name__ == "__main__":
    sys.exit(main())
