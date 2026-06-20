"""SSRF + data-egress policy for the **AI endpoint**.

DIG is local-first: the shipped default is Ollama on
``http://127.0.0.1:11434/v1``. Reaching anything *off* the local machine
(a LAN host or a cloud API like OpenAI/Anthropic) sends pipeline data
off-box, so it's gated behind an explicit operator opt-in — a UI toggle
in Settings → AI (``ai_allow_nonlocal``), or the ``DIG_AI_ALLOW_PRIVATE``
env var for headless / ops setups. The env var is an *additional* path,
not the only one.

Three host tiers:

  - **loopback** (127.0.0.1, ::1, localhost, ``*.localhost``)
      → always allowed. The default local-Ollama target.
  - **remote** (RFC1918 LAN private like 10.x / 192.168.x, AND public
    internet like api.openai.com)
      → allowed only when ``allow_nonlocal`` (UI toggle) is set OR
        ``DIG_AI_ALLOW_PRIVATE=1``. This is the data-egress consent gate.
  - **infra** (link-local incl. cloud metadata 169.254.169.254,
    multicast, reserved, unspecified)
      → allowed ONLY via ``DIG_AI_ALLOW_PRIVATE=1``, never via the UI
        toggle. There is no legitimate AI model server at these
        addresses; keeping them behind the harder-to-flip env var
        preserves the metadata-SSRF protection (round-2 pen-tester
        finding) even after a user enables non-local providers for cloud.

Both the runtime client (``ai.client.chat`` / ``list_models``) and the
Test-Connection probe flow through here, so behaviour is consistent.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from typing import Any, Literal
from urllib.parse import urlsplit

_ALLOWED_SCHEMES = ("http", "https")

HostTier = Literal["loopback", "remote", "infra"]


def _env_allow() -> bool:
    return os.environ.get("DIG_AI_ALLOW_PRIVATE") == "1"


def _is_loopback_host(host: str) -> bool:
    """True for host forms that denote the local machine. String check
    (not a resolve) so ``localhost`` / ``*.localhost`` (RFC 6761 reserved
    for loopback) are always local even if a resolver maps them oddly."""
    h = (host or "").lower().strip("[]")  # strip IPv6 brackets
    return h in ("localhost", "127.0.0.1", "::1") or h.endswith(".localhost")


def _classify_ip(ip: ipaddress._BaseAddress) -> HostTier:
    if ip.is_loopback:
        return "loopback"
    if ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        return "infra"
    # RFC1918 private (LAN) and global (public cloud) are both "remote" —
    # both mean data leaves this machine, both gated by the same consent.
    return "remote"


def classify_host(host: str) -> HostTier:
    """Resolve ``host`` and bucket it into a policy tier. Unresolvable →
    ``remote`` (no SSRF target exists if DNS fails; the connection will
    just error with a clear network message rather than a confusing
    policy block)."""
    if _is_loopback_host(host):
        return "loopback"
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, socket.herror, OSError):
        return "remote"
    tiers: set[HostTier] = set()
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        tiers.add(_classify_ip(ip))
    if not tiers:
        return "remote"
    # Most-restrictive wins if a name resolves to a mix (e.g. rebinding):
    # loopback is benign, infra is the strictest, remote in between.
    if "infra" in tiers:
        return "infra"
    if "remote" in tiers:
        return "remote"
    return "loopback"


def assert_ai_url_safe(url: str, *, allow_nonlocal: bool = False) -> None:
    """Validate the AI endpoint URL before any network call.

    ``allow_nonlocal`` is the resolved value of the ``ai_allow_nonlocal``
    UI toggle. Raises ``ValueError`` on rejection with a message that
    points at the toggle.
    """
    parts = urlsplit(url)
    if parts.scheme.lower() not in _ALLOWED_SCHEMES:
        raise ValueError(
            f"AI endpoint scheme {parts.scheme!r} not allowed; only http and https are permitted",
        )
    if not parts.hostname:
        raise ValueError(f"AI endpoint has no host in URL {url!r}")

    tier = classify_host(parts.hostname)
    if tier == "loopback":
        return
    if tier == "remote":
        if allow_nonlocal or _env_allow():
            return
        raise ValueError(
            f"AI endpoint {parts.hostname!r} is non-local — using it sends data off "
            "this machine. Enable “Allow non-local AI providers” in Settings → AI "
            "(or set DIG_AI_ALLOW_PRIVATE=1) to permit cloud / LAN model hosts.",
        )
    # tier == "infra"
    if _env_allow():
        return
    raise ValueError(
        f"AI endpoint host {parts.hostname!r} resolves to a link-local / metadata "
        "address — refused (no legitimate model server lives there). If you really "
        "need this on a trusted host, set DIG_AI_ALLOW_PRIVATE=1.",
    )


def assert_ai_response_peer_safe(response: Any, *, allow_nonlocal: bool = False) -> None:
    """Post-connect DNS-rebinding check, same tiers as
    :func:`assert_ai_url_safe`. A public-looking hostname that rebinds to
    a link-local / metadata IP is refused unless the env var is set; a
    rebind to a remote (LAN/public) IP needs ``allow_nonlocal`` or the
    env var; loopback is always fine."""
    network_stream = response.extensions.get("network_stream")
    if network_stream is None:
        return  # transport doesn't expose it (test fakes etc.) — best-effort
    sock = None
    if hasattr(network_stream, "get_extra_info"):
        try:
            sock = network_stream.get_extra_info("socket")
        except Exception:  # noqa: BLE001
            sock = None
    if sock is None:
        return
    try:
        peer = sock.getpeername()
    except OSError:
        return
    if not peer:
        return
    try:
        peer_ip = ipaddress.ip_address(peer[0])
    except ValueError:
        return

    tier = _classify_ip(peer_ip)
    if tier == "loopback":
        return
    if tier == "remote" and (allow_nonlocal or _env_allow()):
        return
    if tier == "infra" and _env_allow():
        return
    raise RuntimeError(
        f"AI endpoint connection landed on {peer[0]!r} (tier={tier}) despite a "
        "permitted hostname — possible DNS rebinding. Refusing the response. "
        "Enable non-local providers (or DIG_AI_ALLOW_PRIVATE=1) if this is intended.",
    )
