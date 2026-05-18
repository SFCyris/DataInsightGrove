#!/usr/bin/env python3
"""Self-signed TLS cert management for DIG.

Generates an RSA-2048 self-signed certificate valid for ~10 years, with
Subject Alternative Names covering ``localhost``, the machine hostname,
and every non-loopback IPv4 address present at generation time. Stores
cert + key under ``$XDG_CONFIG_HOME/dig/tls/`` (or
``~/.config/dig/tls/``).

On macOS and Linux, optionally installs the certificate into the system
trust store so browsers and Node.js stop warning about "Not Secure". The
trust state is recorded in ``tls/.trusted_sha256`` so subsequent starts
don't re-prompt for sudo.

Uses the system ``openssl`` CLI rather than Python's ``cryptography``
package so this script has zero non-stdlib dependencies and can run
before any virtualenv is guaranteed activated. ``openssl`` ships on
every modern macOS / Linux / WSL by default.

Subcommands:

    bootstrap   ensure cert exists + (optionally) install to trust
    info        print cert details (subject, expiry, SANs, fingerprint)
    regenerate  force regeneration of cert + key
    trust       install cert into system trust store
    untrust     remove cert from system trust store
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


# --- paths ------------------------------------------------------------------

_USER_CFG = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")) / "dig"
_TLS_DIR = _USER_CFG / "tls"
_CERT_FILE = _TLS_DIR / "dig.crt"
_KEY_FILE = _TLS_DIR / "dig.key"
_TRUSTED_MARKER = _TLS_DIR / ".trusted_sha256"
# Records "we attempted an auto-trust install at least once." Separate
# from ``_TRUSTED_MARKER`` (which records SUCCESS) so we can tell apart
# "never tried" from "tried, user declined / had no TTY". Auto-trust is
# attempted once; after that the user has to opt back in explicitly via
# ``./scripts/dig_tls.py trust`` — that bypasses this marker.
_AUTO_TRUST_ATTEMPTED = _TLS_DIR / ".auto_trust_attempted"

# 10-year validity. This is a machine-local self-signed dev cert; rotating
# more often than that gains nothing and creates churn for embedded clients.
_VALIDITY_DAYS = 3650

# Re-generate when fewer than this many days remain so we never serve an
# expired cert and never sit at "just barely valid."
_RENEW_BEFORE_DAYS = 30


# --- system info -----------------------------------------------------------

def _hostname() -> str:
    try:
        return socket.gethostname() or ""
    except OSError:
        return ""


def _list_lan_ipv4() -> list[str]:
    """Return non-loopback IPv4 addresses bound to any local interface.

    Pure-stdlib approach (no ``netifaces``): for each address resolution
    of our own hostname, collect IPv4s, then also probe via UDP socket
    tricks for the routable interface. Best-effort — missing addresses
    don't break the cert (clients on those IPs see a hostname mismatch
    but the cert is still valid for the SANs we did manage to enumerate).
    """
    ips: set[str] = set()

    # 1. gethostbyname_ex usually returns all bound v4 addresses on Linux.
    try:
        _, _, addrs = socket.gethostbyname_ex(_hostname())
        for a in addrs:
            if not a.startswith("127."):
                ips.add(a)
    except (socket.gaierror, OSError):
        pass

    # 2. getaddrinfo cross-check for IPv4. Adds anything the OS knows about
    #    that gethostbyname_ex missed (macOS' resolver is less helpful here).
    try:
        for entry in socket.getaddrinfo(_hostname(), None, socket.AF_INET):
            ip = entry[4][0]
            if not ip.startswith("127."):
                ips.add(ip)
    except (socket.gaierror, OSError):
        pass

    # 3. UDP socket trick: connect to a public IP (no packets are sent),
    #    read the local bound IP. Reliable way to get "the IP you'd be
    #    reached on from the LAN" — fills the gap on macOS, which doesn't
    #    register hostname.local with the local resolver consistently.
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        addr = s.getsockname()[0]
        if not addr.startswith("127."):
            ips.add(addr)
        s.close()
    except OSError:
        pass

    return sorted(ips)


def _sans() -> tuple[list[str], list[str]]:
    """Return (dns_sans, ip_sans) — the addresses the cert will cover."""
    dns_sans: list[str] = ["localhost"]
    hn = _hostname()
    if hn and hn != "localhost":
        if hn not in dns_sans:
            dns_sans.append(hn)
        # macOS frequently exposes ``<hostname>.local`` via mDNS — add it
        # so visiting `https://<machine>.local:3000` from another Mac on
        # the LAN doesn't show a host-mismatch warning.
        local_form = hn if hn.endswith(".local") else f"{hn}.local"
        if local_form not in dns_sans:
            dns_sans.append(local_form)

    ip_sans: list[str] = ["127.0.0.1", "::1"]
    for ip in _list_lan_ipv4():
        if ip not in ip_sans:
            ip_sans.append(ip)
    return dns_sans, ip_sans


# --- openssl plumbing ------------------------------------------------------

def _openssl(*args: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(["openssl", *args], capture_output=True, text=True, check=False, **kw)


def _require_openssl() -> None:
    if not shutil.which("openssl"):
        raise SystemExit(
            "dig_tls: `openssl` not found on PATH. Install it (macOS: bundled; "
            "Debian/Ubuntu: `apt install openssl`; RHEL: `dnf install openssl`) "
            "and re-run."
        )


# --- generate / inspect ----------------------------------------------------

def generate(
    cert_path: Path = _CERT_FILE,
    key_path: Path = _KEY_FILE,
    additional_sans: list[str] | None = None,
) -> None:
    """(Re)generate cert + key. Idempotent — overwrites whatever's there."""
    _require_openssl()
    cert_path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(cert_path.parent, 0o700)

    dns_sans, ip_sans = _sans()
    for extra in additional_sans or []:
        # Heuristic: a SAN containing only digits + . or : is an IP.
        if all(c.isdigit() or c in ".:" for c in extra):
            if extra not in ip_sans:
                ip_sans.append(extra)
        else:
            if extra not in dns_sans:
                dns_sans.append(extra)

    san_parts = [f"DNS:{d}" for d in dns_sans] + [f"IP:{ip}" for ip in ip_sans]
    san_str = ",".join(san_parts)

    subj = f"/CN=DIG self-signed ({_hostname() or 'unknown'})"

    r = _openssl(
        "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(key_path),
        "-out", str(cert_path),
        "-days", str(_VALIDITY_DAYS),
        "-subj", subj,
        "-addext", f"subjectAltName={san_str}",
    )
    if r.returncode != 0:
        raise SystemExit(f"openssl req failed: {r.stderr.strip()}")
    os.chmod(key_path, 0o600)
    os.chmod(cert_path, 0o644)


def fingerprint_sha256(cert_path: Path = _CERT_FILE) -> str:
    """Cert's SHA-256 fingerprint in colon-separated uppercase hex.

    Matches the format ``security verify-cert`` / openssl prints and
    that browsers display in their "View certificate" dialog — so an
    operator can eyeball-compare to confirm trust install was correct.
    """
    if not cert_path.exists():
        return ""
    # DER output is binary, NOT text — bypass _openssl()'s text=True.
    r = subprocess.run(
        ["openssl", "x509", "-in", str(cert_path), "-outform", "DER"],
        capture_output=True, check=False,
    )
    if r.returncode != 0:
        return ""
    digest = hashlib.sha256(r.stdout).hexdigest().upper()
    return ":".join(digest[i:i + 2] for i in range(0, len(digest), 2))


def cert_info(cert_path: Path = _CERT_FILE) -> dict:
    """Return a dict of cert details suitable for JSON dumping."""
    if not cert_path.exists():
        return {}
    r = _openssl(
        "x509", "-in", str(cert_path), "-noout",
        "-subject", "-startdate", "-enddate", "-ext", "subjectAltName",
    )
    if r.returncode != 0:
        return {}
    out: dict = {"path": str(cert_path)}
    san_lines: list[str] = []
    in_san_block = False
    for line in r.stdout.splitlines():
        if line.startswith("subject="):
            out["subject"] = line.split("=", 1)[1].strip()
        elif line.startswith("notBefore="):
            out["valid_from"] = line.split("=", 1)[1].strip()
        elif line.startswith("notAfter="):
            out["valid_until"] = line.split("=", 1)[1].strip()
        elif "Subject Alternative Name" in line:
            in_san_block = True
        elif in_san_block and ("DNS:" in line or "IP" in line):
            san_lines.append(line.strip())
            in_san_block = False
    if san_lines:
        out["sans"] = san_lines[0]
    out["fingerprint_sha256"] = fingerprint_sha256(cert_path)
    out["trusted_in_system_store"] = is_trusted(cert_path)
    return out


def _normalise_ip(s: str) -> str | None:
    """Return ``str(ipaddress.ip_address(s))`` or None if not a valid IP.

    The whole point is comparison-stability: ``::1`` and
    ``0:0:0:0:0:0:0:1`` and ``0000:0000:0000:0000:0000:0000:0000:0001``
    all normalise to the same canonical short form, so the SAN-coverage
    check doesn't flag a perfectly-correct cert as "missing" the
    address it covers under an equivalent spelling.
    """
    try:
        return str(ipaddress.ip_address(s.strip()))
    except (ValueError, TypeError):
        return None


def _parse_san_line(san_text: str) -> tuple[set[str], set[str]]:
    """Parse openssl's ``subjectAltName`` ext output into (dns, ip) sets.

    openssl prints something like::

        X509v3 Subject Alternative Name:
            DNS:localhost, DNS:my-host.local, IP Address:127.0.0.1,
            IP Address:0:0:0:0:0:0:0:1, IP Address:10.0.0.5

    Older versions used ``IP:`` instead of ``IP Address:``. We accept both,
    and we normalise IPs through ``ipaddress`` so v6 spellings collapse to
    the same canonical form regardless of how openssl chose to print them.
    """
    dns: set[str] = set()
    ips: set[str] = set()
    # Match "DNS:value" and "IP[ Address]:value" entries. The value can
    # contain colons (IPv6) so we anchor on commas / whitespace / EOL.
    for m in re.finditer(r"DNS:([^\s,]+)", san_text):
        dns.add(m.group(1).strip().lower())
    for m in re.finditer(r"IP(?:\s+Address)?:([0-9a-fA-F:.]+)", san_text):
        canonical = _normalise_ip(m.group(1))
        if canonical:
            ips.add(canonical)
    return dns, ips


def needs_regeneration(cert_path: Path = _CERT_FILE) -> tuple[bool, str]:
    """Decide whether to regenerate. Reasons we'd say yes:

      - cert doesn't exist
      - cert is expired or expiring within RENEW_BEFORE_DAYS
      - the current SAN list doesn't cover the current LAN IPs / hostname
        (e.g. the laptop moved networks)
    """
    if not cert_path.exists():
        return True, "no cert on disk"

    # Expiry check (returncode == 0 → cert NOT expired/expiring within window)
    r = subprocess.run(
        ["openssl", "x509", "-in", str(cert_path), "-noout",
         "-checkend", str(_RENEW_BEFORE_DAYS * 86400)],
        capture_output=True, check=False,
    )
    if r.returncode != 0:
        return True, f"expiring within {_RENEW_BEFORE_DAYS} days"

    # SAN coverage: parse what's in the cert vs. what we'd put in it now,
    # using canonical IP normalisation so equivalent spellings (::1 vs
    # 0:0:0:0:0:0:0:1) compare equal.
    r = _openssl("x509", "-in", str(cert_path), "-noout", "-ext", "subjectAltName")
    current = r.stdout if r.returncode == 0 else ""
    cur_dns, cur_ips = _parse_san_line(current)
    want_dns_list, want_ip_list = _sans()
    want_dns = {d.lower() for d in want_dns_list}
    want_ips: set[str] = set()
    for ip in want_ip_list:
        canon = _normalise_ip(ip)
        if canon:
            want_ips.add(canon)

    missing_dns = sorted(want_dns - cur_dns)
    missing_ips = sorted(want_ips - cur_ips)
    if missing_dns or missing_ips:
        parts = [f"DNS:{d}" for d in missing_dns] + [f"IP:{ip}" for ip in missing_ips]
        return True, f"SAN coverage missing: {', '.join(parts[:4])}{'…' if len(parts) > 4 else ''}"

    return False, "current"


# --- system trust store ----------------------------------------------------

def is_trusted(cert_path: Path = _CERT_FILE) -> bool:
    """Did we previously install THIS cert (by SHA-256) into the trust store?

    We track this in a sidecar file rather than querying the system
    keychain directly because the latter requires platform-specific
    invocations that vary by macOS version + Linux distro. The marker
    is a SHA fingerprint, so a cert rotation invalidates trust state
    automatically.
    """
    if not _TRUSTED_MARKER.exists():
        return False
    try:
        marker = _TRUSTED_MARKER.read_text().strip()
    except OSError:
        return False
    return bool(marker) and marker == fingerprint_sha256(cert_path)


def _trust_macos(cert_path: Path) -> tuple[bool, str]:
    """Add cert as a trusted root in the macOS System keychain.

    ``-d`` = add to admin domain (System.keychain, not the user's login).
    ``-r trustRoot`` = trust as a root CA for SSL.
    ``security`` will prompt for sudo if the keychain requires it.
    """
    cmd = [
        "sudo", "-p", "[dig tls] sudo password to add cert to System keychain: ",
        "security", "add-trusted-cert", "-d", "-r", "trustRoot",
        "-k", "/Library/Keychains/System.keychain",
        str(cert_path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if r.returncode != 0:
        return False, (r.stderr.strip() or r.stdout.strip() or "security add-trusted-cert failed")
    return True, "installed into /Library/Keychains/System.keychain"


def _trust_linux(cert_path: Path) -> tuple[bool, str]:
    """Copy cert into the system CA store and run update-ca-certificates.

    Targets the Debian/Ubuntu layout (/usr/local/share/ca-certificates).
    Most RHEL-family distros symlink that path or accept it as an
    additional anchor via update-ca-trust extract. Failures here fall
    back to the "show fingerprint, browser still warns" path.
    """
    dest = "/usr/local/share/ca-certificates/dig-self-signed.crt"
    cmd = [
        "sudo", "-p", "[dig tls] sudo password to install cert in system trust: ",
        "bash", "-lc",
        f"install -m 0644 {shlex_quote(str(cert_path))} {dest} && "
        f"(update-ca-certificates 2>/dev/null || update-ca-trust extract)",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if r.returncode != 0:
        return False, (r.stderr.strip() or r.stdout.strip() or "update-ca-certificates failed")
    return True, f"installed into {dest}"


def _untrust_macos(cert_path: Path) -> tuple[bool, str]:
    sha = fingerprint_sha256(cert_path).replace(":", "")
    cmd = [
        "sudo", "-p", "[dig tls] sudo password to remove cert from System keychain: ",
        "security", "delete-certificate", "-Z", sha,
        "/Library/Keychains/System.keychain",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if r.returncode != 0:
        return False, (r.stderr.strip() or r.stdout.strip() or "delete-certificate failed")
    return True, "removed from System keychain"


def _untrust_linux(_cert_path: Path) -> tuple[bool, str]:
    dest = "/usr/local/share/ca-certificates/dig-self-signed.crt"
    cmd = [
        "sudo", "-p", "[dig tls] sudo password to remove cert from system trust: ",
        "bash", "-lc",
        f"rm -f {dest} && (update-ca-certificates --fresh 2>/dev/null || update-ca-trust extract)",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if r.returncode != 0:
        return False, (r.stderr.strip() or r.stdout.strip() or "remove failed")
    return True, f"removed from {dest}"


def trust(cert_path: Path = _CERT_FILE) -> tuple[bool, str]:
    """Add cert to platform trust store. Idempotent via the marker file."""
    if is_trusted(cert_path):
        return True, "already trusted"

    sysname = platform.system()
    if sysname == "Darwin":
        ok, msg = _trust_macos(cert_path)
    elif sysname == "Linux":
        ok, msg = _trust_linux(cert_path)
    else:
        return False, f"trust install not implemented for {sysname}"

    if ok:
        try:
            _TRUSTED_MARKER.write_text(fingerprint_sha256(cert_path) + "\n")
            os.chmod(_TRUSTED_MARKER, 0o600)
        except OSError as e:
            return True, f"{msg} (warning: could not write marker: {e})"
    return ok, msg


def untrust(cert_path: Path = _CERT_FILE) -> tuple[bool, str]:
    sysname = platform.system()
    if sysname == "Darwin":
        ok, msg = _untrust_macos(cert_path)
    elif sysname == "Linux":
        ok, msg = _untrust_linux(cert_path)
    else:
        return False, f"trust uninstall not implemented for {sysname}"
    if ok:
        _TRUSTED_MARKER.unlink(missing_ok=True)
    return ok, msg


# --- subcommands ----------------------------------------------------------

def cmd_bootstrap(args: argparse.Namespace) -> int:
    """Ensure cert exists + key paths are echoed to stdout for the shell to eval.

    On stderr: log lines describing what we did. On stdout: shell-eval
    KEY=VALUE pairs. Exit 0 unless we couldn't produce a usable cert.
    """
    cert_path = Path(args.cert) if args.cert else _CERT_FILE
    key_path = Path(args.key) if args.key else _KEY_FILE

    regen, reason = needs_regeneration(cert_path)
    if regen:
        print(f"[dig tls] generating cert: {reason}", file=sys.stderr)
        generate(cert_path, key_path, additional_sans=args.san or [])
        # New cert → previous trust state is meaningless. Clear BOTH markers
        # so the next auto-trust pass gets a fresh attempt (a legitimate
        # regeneration — e.g. laptop moved to a different LAN — is a good
        # reason to re-prompt for sudo just this once).
        _TRUSTED_MARKER.unlink(missing_ok=True)
        _AUTO_TRUST_ATTEMPTED.unlink(missing_ok=True)
        print(f"[dig tls] cert SHA-256: {fingerprint_sha256(cert_path)}", file=sys.stderr)

    if args.trust:
        if is_trusted(cert_path):
            print("[dig tls] cert already trusted by system", file=sys.stderr)
        elif _AUTO_TRUST_ATTEMPTED.exists():
            # We've previously tried and either succeeded-but-marker-now-missing
            # (rare; user manually edited the trust state) or failed/declined.
            # Don't pester on every restart — the user can opt back in with
            # ``./scripts/dig_tls.py trust`` which bypasses this check.
            print(
                "[dig tls] auto-trust skipped (already attempted once). "
                "Run `./scripts/dig_tls.py trust` to install manually.",
                file=sys.stderr,
            )
        else:
            ok, msg = trust(cert_path)
            # Mark the attempt regardless of outcome so we don't auto-retry
            # on every restart. The user can re-trigger explicitly via the
            # ``trust`` subcommand below.
            try:
                _AUTO_TRUST_ATTEMPTED.parent.mkdir(parents=True, exist_ok=True)
                _AUTO_TRUST_ATTEMPTED.write_text(
                    "outcome={}\n".format("ok" if ok else "failed")
                )
            except OSError:
                pass
            if ok:
                print(f"[dig tls] system trust: {msg}", file=sys.stderr)
            else:
                # Don't fail the start — the browser will just show a
                # warning the user can click through (or they can stick
                # to http://localhost which doesn't care about trust).
                print(f"[dig tls] WARNING: system trust install failed: {msg}", file=sys.stderr)
                print(
                    "[dig tls] won't auto-retry on subsequent restarts. "
                    "When you're ready: ./scripts/dig_tls.py trust",
                    file=sys.stderr,
                )

    # Shell-evalable output on stdout.
    print(f"DIG_TLS_CERT={cert_path}")
    print(f"DIG_TLS_KEY={key_path}")
    return 0


def cmd_info(_args: argparse.Namespace) -> int:
    info = cert_info()
    if not info:
        print("(no cert)")
        return 1
    print(json.dumps(info, indent=2))
    return 0


def cmd_regenerate(args: argparse.Namespace) -> int:
    cert_path = Path(args.cert) if args.cert else _CERT_FILE
    key_path = Path(args.key) if args.key else _KEY_FILE
    print(f"[dig tls] regenerating cert at {cert_path}", file=sys.stderr)
    generate(cert_path, key_path, additional_sans=args.san or [])
    _TRUSTED_MARKER.unlink(missing_ok=True)
    print(f"[dig tls] new SHA-256: {fingerprint_sha256(cert_path)}", file=sys.stderr)
    print(f"[dig tls] cert is no longer trusted; re-run `dig_tls.py trust` if needed", file=sys.stderr)
    return 0


def cmd_trust(_args: argparse.Namespace) -> int:
    # Explicit user-initiated trust install — clear the "auto-trust
    # attempted" marker first so the user is asking for a fresh try.
    # ``trust()`` is idempotent (no-op if already trusted) so re-running
    # this is always safe.
    _AUTO_TRUST_ATTEMPTED.unlink(missing_ok=True)
    ok, msg = trust()
    if ok:
        # Stamp the attempted-marker on success too so the start-script
        # auto-trust path stays skipped (the success marker
        # `_TRUSTED_MARKER` is what `is_trusted` checks; this is just
        # defense-in-depth).
        try:
            _AUTO_TRUST_ATTEMPTED.write_text("outcome=ok\n")
        except OSError:
            pass
    print(f"[dig tls] {msg}", file=sys.stderr)
    return 0 if ok else 1


def cmd_untrust(_args: argparse.Namespace) -> int:
    ok, msg = untrust()
    # Removing trust resets the attempt marker too so a future start
    # script's auto-trust step (if the user re-enables it) will try
    # again rather than skipping silently.
    if ok:
        _AUTO_TRUST_ATTEMPTED.unlink(missing_ok=True)
    print(f"[dig tls] {msg}", file=sys.stderr)
    return 0 if ok else 1


def shlex_quote(s: str) -> str:
    """Local shlex.quote import — keep top-level imports minimal."""
    import shlex
    return shlex.quote(s)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    bs = sub.add_parser("bootstrap", help="ensure cert exists; optionally install to trust store")
    bs.add_argument("--cert", help="cert path override")
    bs.add_argument("--key", help="key path override")
    bs.add_argument("--trust", action="store_true",
                    help="install cert into system trust store (prompts for sudo)")
    bs.add_argument("--san", action="append",
                    help="extra SAN to include (DNS or IP). May be repeated.")

    sub.add_parser("info", help="print current cert details")

    rg = sub.add_parser("regenerate", help="force regeneration of cert + key")
    rg.add_argument("--cert", help="cert path override")
    rg.add_argument("--key", help="key path override")
    rg.add_argument("--san", action="append")

    sub.add_parser("trust", help="install cert into system trust store")
    sub.add_parser("untrust", help="remove cert from system trust store")

    args = p.parse_args(argv)
    return {
        "bootstrap": cmd_bootstrap,
        "info": cmd_info,
        "regenerate": cmd_regenerate,
        "trust": cmd_trust,
        "untrust": cmd_untrust,
    }[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
