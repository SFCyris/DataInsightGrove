#!/usr/bin/env python3
"""Tiny TLS-terminating TCP reverse proxy.

Listens on one or more (host, port) pairs with TLS termination, and
forwards the decrypted byte stream to a plain HTTP backend. Lets DIG
expose both ``http://`` and ``https://`` URLs for the same services
without running every service in dual-protocol mode (which would mean
two uvicorn instances fighting over one SQLite DB, or two ``next dev``
processes confusing HMR).

Architecture:

    browser ──https──▶ this proxy ──http──▶ uvicorn / next-dev

Because the proxy is a transparent TCP forwarder, HTTP/1.1 + WebSocket
upgrades + Server-Sent Events all work without protocol awareness —
the proxy just shovels bytes both ways.

Usage:

    dig_tls_proxy.py \\
        --cert ~/.config/dig/tls/dig.crt \\
        --key  ~/.config/dig/tls/dig.key \\
        --forward 8443:8090 \\
        --forward 3443:3000

``--forward LISTEN:BACKEND`` opens a TLS listener on ``LISTEN`` and
forwards every connection to ``127.0.0.1:BACKEND``. May be repeated.
The bind host is taken from ``--host`` (default ``0.0.0.0``).

Pure stdlib (asyncio + ssl). No third-party deps so this script runs
before any venv is guaranteed activated.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import ssl
import sys
from pathlib import Path
from typing import NamedTuple


log = logging.getLogger("dig_tls_proxy")


class Forward(NamedTuple):
    listen_port: int
    backend_host: str
    backend_port: int


# 64 KiB per read — big enough to amortise syscall cost on bulk uploads
# (Parquet imports, run-output downloads) without bloating per-connection
# RAM. Each open client → 2 buffers (client→backend + backend→client).
_CHUNK = 64 * 1024


async def _pump(src: asyncio.StreamReader, dst: asyncio.StreamWriter,
                tag: str) -> None:
    """Drain ``src``, write to ``dst``. Returns on EOF or any write error.

    We catch BrokenPipeError + ConnectionResetError explicitly because
    those are the *expected* terminations for half-closed streams (one
    side closed first; the other half drains then closes). Logging them
    as errors would spam the log with normal lifecycle events.
    """
    try:
        while True:
            data = await src.read(_CHUNK)
            if not data:
                break
            dst.write(data)
            await dst.drain()
    except (ConnectionResetError, BrokenPipeError):
        # peer closed mid-stream — normal for HTTP keep-alive teardown
        pass
    except Exception as e:  # noqa: BLE001
        log.debug("[%s] pump aborted: %s", tag, e)
    finally:
        try:
            dst.close()
        except Exception:  # noqa: BLE001
            pass


async def _handle_client(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    backend_host: str,
    backend_port: int,
) -> None:
    """Open a parallel TCP connection to the backend and shovel bytes
    both directions until either side closes."""
    peer = client_writer.get_extra_info("peername")
    peer_label = f"{peer[0]}:{peer[1]}" if peer else "?"

    try:
        backend_reader, backend_writer = await asyncio.open_connection(
            backend_host, backend_port,
        )
    except (ConnectionRefusedError, OSError) as e:
        log.warning("backend %s:%d unreachable for %s: %s",
                    backend_host, backend_port, peer_label, e)
        try:
            # Send a 503 the browser can act on — without this, a curl
            # connecting before uvicorn is ready hangs until TCP timeout.
            client_writer.write(
                b"HTTP/1.1 503 Service Unavailable\r\n"
                b"Content-Type: text/plain; charset=utf-8\r\n"
                b"Connection: close\r\n"
                b"\r\n"
                b"DIG TLS proxy: backend not ready yet\n"
            )
            await client_writer.drain()
        except Exception:  # noqa: BLE001
            pass
        client_writer.close()
        return

    await asyncio.gather(
        _pump(client_reader, backend_writer, f"{peer_label}→backend"),
        _pump(backend_reader, client_writer, f"backend→{peer_label}"),
        return_exceptions=True,
    )


async def _serve_forward(
    listen_host: str,
    fwd: Forward,
    ctx: ssl.SSLContext,
) -> None:
    """One TLS listener that forwards to one backend."""

    async def handler(r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
        await _handle_client(r, w, fwd.backend_host, fwd.backend_port)

    server = await asyncio.start_server(
        handler, listen_host, fwd.listen_port, ssl=ctx,
        # Drop connections immediately on shutdown rather than waiting
        # for keep-alive timeouts; matters for fast dig-stop cycles.
        backlog=128,
    )
    sock_info = ", ".join(str(s.getsockname()) for s in server.sockets)
    log.info("https://%s:%d  →  http://%s:%d   (%s)",
             listen_host, fwd.listen_port, fwd.backend_host, fwd.backend_port, sock_info)
    try:
        async with server:
            await server.serve_forever()
    except asyncio.CancelledError:
        pass


def _parse_forward(spec: str) -> Forward:
    """``8443:8090`` → forward LISTEN 8443 → backend 127.0.0.1:8090.

    Also accepts the long form ``8443:127.0.0.1:8090`` for the rare
    deployment where the backend lives on a non-loopback address (e.g.
    a sibling container). Listen port + backend port are required;
    backend host defaults to ``127.0.0.1``.
    """
    parts = spec.split(":")
    if len(parts) == 2:
        return Forward(int(parts[0]), "127.0.0.1", int(parts[1]))
    if len(parts) == 3:
        return Forward(int(parts[0]), parts[1], int(parts[2]))
    raise argparse.ArgumentTypeError(
        f"--forward expects LISTEN_PORT:BACKEND_PORT or "
        f"LISTEN_PORT:BACKEND_HOST:BACKEND_PORT (got {spec!r})"
    )


def _build_ssl_context(cert: str, key: str) -> ssl.SSLContext:
    if not Path(cert).is_file():
        raise SystemExit(f"--cert: file not found: {cert}")
    if not Path(key).is_file():
        raise SystemExit(f"--key: file not found: {key}")
    # PURPOSE_CLIENT_AUTH = "I'm a server authenticating myself to clients"
    # (yes, the name is backwards from how it reads). It's the correct
    # purpose for an https-server-side cert.
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(certfile=cert, keyfile=key)
    # Disable obsolete protocols. TLS 1.0/1.1 are gone from every modern
    # browser anyway; allowing them just creates attack surface.
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


async def _amain(args: argparse.Namespace) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    ctx = _build_ssl_context(args.cert, args.key)
    forwards = [_parse_forward(s) for s in args.forward]
    if not forwards:
        log.error("no --forward rules; nothing to do")
        return 2

    log.info("dig_tls_proxy starting · %d listener(s) · cert=%s",
             len(forwards), args.cert)

    # Install signal handlers that cancel the gather and let asyncio
    # tear the listeners down cleanly. Without this, the rotator wrapper
    # has to escalate to SIGKILL to stop us — and the open TLS sockets
    # would leak FDs in macOS' kqueue accounting.
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, RuntimeError):
            pass

    tasks = [asyncio.create_task(_serve_forward(args.host, f, ctx))
             for f in forwards]
    await stop_event.wait()
    log.info("dig_tls_proxy stopping")
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--cert", required=True, help="TLS certificate (PEM).")
    p.add_argument("--key", required=True, help="TLS private key (PEM).")
    p.add_argument("--host", default="0.0.0.0",
                   help="Bind address for the TLS listeners (default 0.0.0.0).")
    p.add_argument(
        "--forward", action="append", default=[], metavar="LISTEN:BACKEND",
        help="TLS listener → plain-HTTP backend. e.g. `8443:8090` or "
             "`8443:127.0.0.1:8090`. May be repeated.",
    )
    args = p.parse_args(argv)
    try:
        return asyncio.run(_amain(args))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
