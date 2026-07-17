#!/usr/bin/env bash
# Project: https://github.com/SFCyris/DataInsightGrove
# Cross-platform DIG start script. Works on Linux + macOS.
#
# Usage:
#   ./scripts/dig-start.sh                      # detached, write PIDs, print URLs
#   ./scripts/dig-start.sh --foreground         # stay foreground, prefixed logs, Ctrl-C cleans up
#   ./scripts/dig-start.sh --local              # bind to 127.0.0.1 only (this machine)
#   ./scripts/dig-start.sh --global             # bind to 0.0.0.0 (any device on the LAN)
#   ./scripts/dig-start.sh --api-port 9000      # override API port for this run
#   ./scripts/dig-start.sh --web-port 4000      # override web port for this run
#   ./scripts/dig-start.sh --data-dir /var/dig  # override data directory
#   ./scripts/dig-start.sh --save               # persist any --*-port / --*-host / --data-dir flags to config
#
# Defaults: api 127.0.0.1:8190  · web 127.0.0.1:3100  · data <repo>/data
# Persistent overrides live at ~/.config/dig/config.json — see scripts/dig_config.py.
#
# Local vs global:
#   --local sets api.host + web.host to 127.0.0.1. DIG only answers on this
#           machine — other devices on your network can't reach it.
#   --global sets both to 0.0.0.0. Any device on your LAN can open the web UI
#           via this machine's hostname / IP. The frontend's runtime auto-
#           derives the API URL from the visiting hostname so it Just Works.
#           NOTE: DIG does not enforce auth by default — see SECURITY in the
#           startup banner.

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_DIR="$REPO_ROOT/scripts"

# ---- portable helpers ----
err()  { printf '%s\n' "$*" >&2; }
info() { printf '\033[36m%s\033[0m\n' "$*"; }

# True when the host string means "all interfaces" (`0.0.0.0`, `::`, `*`).
# Used to flip behaviour between local-only and LAN-wide modes — the
# frontend's NEXT_PUBLIC_DIG_API is pinned only in local mode so the
# browser-side `_resolveApiBase()` (window.location.hostname) takes
# over in global mode.
is_global_bind() {
  case "$1" in
    0.0.0.0|::|*"*"*) return 0 ;;
    *) return 1 ;;
  esac
}

# Enumerate every non-loopback IPv4 address on this machine. Used to
# print "open at: http://X:3100" for every interface when running in
# --global / 0.0.0.0 mode. Robust across Linux (`ip` or `hostname -I`)
# and macOS (`ifconfig`). Hostnames are added as well so users can
# bookmark the friendly form.
list_lan_addresses() {
  local addrs=()
  if command -v ip >/dev/null 2>&1; then
    while IFS= read -r ip; do
      [[ -n "$ip" && "$ip" != "127.0.0.1" ]] && addrs+=("$ip")
    done < <(ip -4 -o addr show 2>/dev/null | awk '{print $4}' | cut -d/ -f1)
  elif command -v ifconfig >/dev/null 2>&1; then
    while IFS= read -r ip; do
      [[ -n "$ip" && "$ip" != "127.0.0.1" ]] && addrs+=("$ip")
    done < <(ifconfig 2>/dev/null | awk '/inet [0-9]/ {print $2}')
  elif command -v hostname >/dev/null 2>&1; then
    # Linux glibc `hostname -I` lists all configured IPs, space-separated.
    for ip in $(hostname -I 2>/dev/null); do
      [[ "$ip" != "127.0.0.1" && "$ip" != "::1" ]] && addrs+=("$ip")
    done
  fi
  printf '%s\n' "${addrs[@]}"
}

# Local hostname for the friendly URL. macOS exposes this via
# `scutil --get LocalHostName` (mDNS .local form); Linux falls through
# to `hostname` which is the kernel hostname (works on any LAN with
# Avahi or just static /etc/hosts entries).
local_hostname() {
  if command -v scutil >/dev/null 2>&1; then
    local h
    h="$(scutil --get LocalHostName 2>/dev/null)"
    [[ -n "$h" ]] && { printf '%s.local\n' "$h"; return; }
  fi
  if command -v hostname >/dev/null 2>&1; then
    hostname 2>/dev/null
  fi
}

# Find a Python 3 interpreter that's actually present on either Linux or macOS.
PY="$(command -v python3 || command -v python || true)"
if [[ -z "$PY" ]]; then
  err "python3 not found in PATH — required for the config helper."
  exit 127
fi

# ---- parse CLI flags ----
FOREGROUND=0
SAVE=0
CLI_API_PORT=""
CLI_WEB_PORT=""
CLI_DATA_DIR=""
CLI_API_HOST=""
CLI_WEB_HOST=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --foreground|-f) FOREGROUND=1; shift ;;
    --save)          SAVE=1; shift ;;
    --local|--localhost-only)
      # Shorthand for "--api-host 127.0.0.1 --web-host 127.0.0.1".
      CLI_API_HOST="127.0.0.1"; CLI_WEB_HOST="127.0.0.1"; shift ;;
    --global|--lan|--public)
      # Shorthand for "--api-host 0.0.0.0 --web-host 0.0.0.0".
      CLI_API_HOST="0.0.0.0"; CLI_WEB_HOST="0.0.0.0"; shift ;;
    --api-port)      CLI_API_PORT="${2:?--api-port needs a value}"; shift 2 ;;
    --web-port)      CLI_WEB_PORT="${2:?--web-port needs a value}"; shift 2 ;;
    --api-host)      CLI_API_HOST="${2:?--api-host needs a value}"; shift 2 ;;
    --web-host)      CLI_WEB_HOST="${2:?--web-host needs a value}"; shift 2 ;;
    --data-dir)      CLI_DATA_DIR="${2:?--data-dir needs a value}"; shift 2 ;;
    -h|--help)
      sed -n '2,26p' "$0" | sed 's/^# //; s/^#//'
      exit 0
      ;;
    *) err "unknown flag: $1"; exit 64 ;;
  esac
done

# Apply CLI overrides as env vars so dig_config picks them up.
[[ -n "$CLI_API_PORT" ]] && export DIG_API_PORT="$CLI_API_PORT"
[[ -n "$CLI_WEB_PORT" ]] && export DIG_WEB_PORT="$CLI_WEB_PORT"
[[ -n "$CLI_API_HOST" ]] && export DIG_API_HOST="$CLI_API_HOST"
[[ -n "$CLI_WEB_HOST" ]] && export DIG_WEB_HOST="$CLI_WEB_HOST"
[[ -n "$CLI_DATA_DIR" ]] && export DIG_DATA_DIR="$CLI_DATA_DIR"

# Persist if requested.
if [[ "$SAVE" -eq 1 ]]; then
  [[ -n "$CLI_API_PORT" ]] && "$PY" "$SCRIPT_DIR/dig_config.py" set api.port "$CLI_API_PORT" >/dev/null
  [[ -n "$CLI_WEB_PORT" ]] && "$PY" "$SCRIPT_DIR/dig_config.py" set web.port "$CLI_WEB_PORT" >/dev/null
  [[ -n "$CLI_API_HOST" ]] && "$PY" "$SCRIPT_DIR/dig_config.py" set api.host "$CLI_API_HOST" >/dev/null
  [[ -n "$CLI_WEB_HOST" ]] && "$PY" "$SCRIPT_DIR/dig_config.py" set web.host "$CLI_WEB_HOST" >/dev/null
  [[ -n "$CLI_DATA_DIR" ]] && "$PY" "$SCRIPT_DIR/dig_config.py" set dataDir "$CLI_DATA_DIR" >/dev/null
  err "[dig start] persisted overrides to $("$PY" "$SCRIPT_DIR/dig_config.py" path 2>/dev/null || true)"
fi

# Resolve effective config and bring values into the shell.
EXPORT="$("$PY" "$SCRIPT_DIR/dig_config.py" export)" || { err "config resolve failed"; exit 1; }
eval "$EXPORT"

API_HOST="${DIG_API_HOST:-127.0.0.1}"
API_PORT="${DIG_API_PORT:-8190}"
API_HTTPS_PORT="${DIG_API_HTTPS_PORT:-8443}"
WEB_HOST="${DIG_WEB_HOST:-127.0.0.1}"
WEB_PORT="${DIG_WEB_PORT:-3100}"
WEB_HTTPS_PORT="${DIG_WEB_HTTPS_PORT:-3443}"

# Where to put PIDs + logs. Use XDG_CONFIG_HOME on both Linux and macOS.
USER_CFG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/dig"
mkdir -p "$USER_CFG_DIR"
PID_FILE="$USER_CFG_DIR/pid.json"

# Effective log dir comes from dig_config.py (defaults → file → env). The
# canonical path is /var/log/DIG; dig_config defaults to that. We bootstrap
# the dir below — sudo if it's a system path the current user can't write
# to, falling back to a per-user location if sudo is unavailable / declined.
LOG_DIR="${DIG_LOG_DIR:-/var/log/DIG}"

# Per-user fallback that doesn't need root. Picked to match each platform's
# native convention so logs surface in the OS-provided viewers (Console.app
# on macOS) and live alongside other XDG state on Linux.
case "$(uname -s)" in
  Darwin) USER_LOG_FALLBACK="$HOME/Library/Logs/DIG" ;;
  *)      USER_LOG_FALLBACK="${XDG_STATE_HOME:-$HOME/.local/state}/DIG/logs" ;;
esac

# Bootstrap LOG_DIR. Three cases:
#   1. Already exists + writable by us → no-op.
#   2. System path (/var/* /opt/*) → sudo mkdir + chown to the current
#      user. Sudo will prompt if there's no cached credential; if the
#      user declines or sudo isn't installed, fall through to the user
#      fallback rather than crash the whole start.
#   3. User path → plain mkdir.
_log_dir_writable() {
  [[ -d "$1" ]] && [[ -w "$1" ]]
}

if ! _log_dir_writable "$LOG_DIR"; then
  case "$LOG_DIR" in
    /var/*|/opt/*|/srv/*|/usr/*)
      info "[dig start] log dir $LOG_DIR isn't writable; bootstrapping with sudo"
      if command -v sudo >/dev/null 2>&1 \
         && sudo -p "[dig start] sudo password to create $LOG_DIR: " mkdir -p "$LOG_DIR" \
         && sudo chown "$(id -un):$(id -gn)" "$LOG_DIR"; then
        info "[dig start] $LOG_DIR ready (chown $(id -un))"
      else
        err "[dig start] could not bootstrap $LOG_DIR via sudo; using $USER_LOG_FALLBACK instead"
        LOG_DIR="$USER_LOG_FALLBACK"
        mkdir -p "$LOG_DIR"
      fi
      ;;
    *)
      mkdir -p "$LOG_DIR"
      ;;
  esac
fi

API_LOG="$LOG_DIR/dig-api.log"
WEB_LOG="$LOG_DIR/dig-web.log"

# Rotation knobs come from dig_config.py too. Defaults: 10 MB × 5 files
# per stream. Override via DIG_LOG_MAX_BYTES / DIG_LOG_BACKUP_COUNT or
# `dig-config set log.maxBytes / log.backupCount`.
LOG_MAX_BYTES="${DIG_LOG_MAX_BYTES:-10485760}"
LOG_BACKUP_COUNT="${DIG_LOG_BACKUP_COUNT:-5}"

# ---- preflight ----
# When deps aren't ready, run the installer rather than punting back to the
# user. Most users hit this on a fresh clone (no .venv, no node_modules) —
# they'd rather wait a few minutes than be told to run another command and
# come back. Power users who don't want this can `--no-auto-install` it.
NEEDS_INSTALL=0
[[ ! -d "$REPO_ROOT/backend/.venv" ]]        && NEEDS_INSTALL=1
[[ ! -d "$REPO_ROOT/frontend/node_modules" ]] && NEEDS_INSTALL=1
if [[ "$NEEDS_INSTALL" -eq 1 ]]; then
  if [[ "${DIG_NO_AUTO_INSTALL:-}" == "1" ]]; then
    err "[dig start] dependencies missing — run ./scripts/dig-install.sh first."
    err "            (DIG_NO_AUTO_INSTALL=1 is set, so the autorun was skipped.)"
    exit 1
  fi
  info "[dig start] dependencies missing — running ./scripts/dig-install.sh now."
  info "            (set DIG_NO_AUTO_INSTALL=1 to skip this autorun)"
  if ! "$REPO_ROOT/scripts/dig-install.sh"; then
    err "[dig start] install failed — see error above. Fix the issue, then re-run ./start.sh"
    exit 1
  fi
fi

# Refuse to start if anything is already LISTENING on the requested ports.
# `-sTCP:LISTEN` matters — without the filter, lingering CLOSED / TIME_WAIT /
# CLOSE_WAIT sockets (e.g. left by a recently-killed dev process or a client
# that connected and hung up) trigger a spurious "port already in use" error
# even though nothing is actually serving. The other dig-* scripts
# (dig-stop, dig-restart, dig-restart-web) already filter to LISTEN — keep
# this one consistent.
if command -v lsof >/dev/null 2>&1; then
  if lsof -ti tcp:"$API_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    err "[dig start] port $API_PORT already in use. Stop it first or pass --api-port N."
    exit 2
  fi
  if lsof -ti tcp:"$WEB_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    err "[dig start] port $WEB_PORT already in use. Stop it first or pass --web-port N."
    exit 2
  fi
fi

# ---- TLS bootstrap ----
# We always serve HTTP on the primary ports (api.port / web.port) so the
# "just open the URL" path never trips on cert-trust issues. When TLS is
# enabled we ALSO open https:// listeners on api.httpsPort / web.httpsPort
# via dig_tls_proxy.py — a tiny asyncio TLS-terminating TCP proxy that
# forwards plain HTTP to the same backends. So: same uvicorn + same next
# dev, but reachable on both protocols.
#
# This decouples cert trust from "can I use the app at all" — which was
# the real failure mode of the previous all-HTTPS setup: an untrusted
# self-signed cert silently drops cross-origin fetch() calls in every
# modern browser, leaving the page blank with no error.
TLS_ENABLED="${DIG_TLS_ENABLED:-1}"
TLS_READY=0
if [[ "$TLS_ENABLED" == "1" || "$TLS_ENABLED" == "true" ]]; then
  TLS_ARGS=(bootstrap)
  if [[ "${DIG_TLS_AUTO_TRUST:-1}" == "1" || "${DIG_TLS_AUTO_TRUST:-1}" == "true" ]]; then
    TLS_ARGS+=(--trust)
  fi
  [[ -n "${DIG_TLS_CERT:-}" ]] && TLS_ARGS+=(--cert "$DIG_TLS_CERT")
  [[ -n "${DIG_TLS_KEY:-}" ]]  && TLS_ARGS+=(--key  "$DIG_TLS_KEY")

  TLS_OUT="$("$PY" "$SCRIPT_DIR/dig_tls.py" "${TLS_ARGS[@]}")" || {
    err "[dig start] TLS bootstrap failed — HTTPS listeners disabled."
    TLS_OUT=""
  }
  if [[ -n "$TLS_OUT" ]]; then
    eval "$TLS_OUT"
    export DIG_TLS_CERT DIG_TLS_KEY
    TLS_READY=1
  fi
fi

cat <<EOF
[dig start] api  → http://$API_HOST:$API_PORT$([[ "$TLS_READY" -eq 1 ]] && echo "  ·  https://$API_HOST:$API_HTTPS_PORT")
[dig start] web  → http://$WEB_HOST:$WEB_PORT$([[ "$TLS_READY" -eq 1 ]] && echo "  ·  https://$WEB_HOST:$WEB_HTTPS_PORT")
[dig start] cfg  → $("$PY" "$SCRIPT_DIR/dig_config.py" path 2>/dev/null || echo '(defaults only)')
EOF

# In global mode the backend refuses to bind to a non-loopback host
# unless DIG_AUTH_TOKEN is set. Auto-generate a strong token on the
# first --global run and persist it so subsequent runs reuse the same
# value (otherwise the frontend's NEXT_PUBLIC_DIG_AUTH_TOKEN would
# rotate every restart and embedded clients would break).
if is_global_bind "$API_HOST"; then
  AUTH_FILE="$USER_CFG_DIR/auth.token"
  # Resolve the token in priority order:
  #   1. DIG_AUTH_TOKEN already in env (e.g. from .bashrc, CI, the operator).
  #   2. ~/.config/dig/auth.token  (persisted across runs).
  #   3. Auto-generate.
  # Then ALWAYS persist to AUTH_FILE so the file is a reliable source-of-
  # truth — without this, the post-startup banner could lie about where
  # the token lives (e.g. operator exported via env, banner claimed file
  # storage, file didn't exist). Caught by Pop!_OS testing.
  if [[ -n "${DIG_AUTH_TOKEN:-}" ]]; then
    info "[dig start] using auth token from existing DIG_AUTH_TOKEN env var"
  elif [[ -s "$AUTH_FILE" ]]; then
    DIG_AUTH_TOKEN="$(tr -d '[:space:]' < "$AUTH_FILE")"
    info "[dig start] reusing auth token from $AUTH_FILE"
  else
    DIG_AUTH_TOKEN="$("$PY" -c 'import secrets; print(secrets.token_urlsafe(32))')"
    info "[dig start] generated a fresh auth token"
  fi
  # Always (re)write to AUTH_FILE so the banner's "Stored at …" claim is
  # truthful and a single canonical place exists for remote integrations.
  if [[ ! -s "$AUTH_FILE" ]] || [[ "$(tr -d '[:space:]' < "$AUTH_FILE")" != "$DIG_AUTH_TOKEN" ]]; then
    umask 077
    printf '%s\n' "$DIG_AUTH_TOKEN" > "$AUTH_FILE"
    chmod 600 "$AUTH_FILE"
    info "[dig start] auth token persisted to $AUTH_FILE (chmod 600)"
  fi
  export DIG_AUTH_TOKEN
  # Frontend client reads this at build/runtime to attach Bearer header.
  export NEXT_PUBLIC_DIG_AUTH_TOKEN="$DIG_AUTH_TOKEN"

  # CORS allow-list. The backend defaults to `localhost:3100,127.0.0.1:3100`,
  # which means a remote browser hitting `http://<lan-ip>:3100` triggers
  # a CORS preflight failure (Firefox masks it as "NetworkError when
  # attempting to fetch resource"). In global mode auto-populate the
  # list with every reachable web origin: localhost/127.0.0.1, the
  # local hostname (mDNS .local on macOS, kernel hostname on Linux),
  # and every non-loopback IPv4 on the box. Honor a user-provided
  # DIG_CORS_ORIGINS — only auto-populate when unset.
  if [[ -z "${DIG_CORS_ORIGINS:-}" ]]; then
    # Build the CORS list for both protocols + every reachable host.
    # The browser sends the page's own origin (scheme + host + port) as
    # the Origin header, so the allow-list has to enumerate every
    # combination the user could land on — http://lan-ip:3100 and
    # https://lan-ip:3443 are different origins as far as CORS is
    # concerned, even though they reach the same Next dev server.
    _add_origin() {
      local host="$1"
      cors_list="$cors_list,http://${host}:${WEB_PORT}"
      [[ "$TLS_READY" -eq 1 ]] && cors_list="$cors_list,https://${host}:${WEB_HTTPS_PORT}"
    }
    cors_list="http://localhost:$WEB_PORT,http://127.0.0.1:$WEB_PORT"
    [[ "$TLS_READY" -eq 1 ]] && cors_list="$cors_list,https://localhost:$WEB_HTTPS_PORT,https://127.0.0.1:$WEB_HTTPS_PORT"
    hn="$(local_hostname)"
    if [[ -n "$hn" ]]; then
      _add_origin "$hn"
      bare="${hn%.local}"
      [[ "$bare" != "$hn" ]] && _add_origin "$bare"
    fi
    while IFS= read -r ip; do
      [[ -n "$ip" ]] && _add_origin "$ip"
    done < <(list_lan_addresses)
    export DIG_CORS_ORIGINS="$cors_list"
    info "[dig start] DIG_CORS_ORIGINS auto-populated for LAN: $DIG_CORS_ORIGINS"
  fi
fi

# Foreground mode: prefix-tag and inherit signals; for `make dev` and Ctrl-C use.
if [[ "$FOREGROUND" -eq 1 ]]; then
  exec "$SCRIPT_DIR/dig-dev.sh"
fi

# ---- detached mode ----
# Try to start with `setsid` (linux) or `nohup` (mac + linux) so the children
# survive shell exit. setsid is preferred because it gives us a process group
# we can kill cleanly later.
START_PREFIX=()
if command -v setsid >/dev/null 2>&1; then
  START_PREFIX=(setsid)
elif command -v nohup >/dev/null 2>&1; then
  START_PREFIX=(nohup)
fi

# Pin the startup banner to the top of both log files BEFORE handing
# them off to the rotator. The banner captures DIG version, git SHA,
# OS / kernel / Python / Node, RAM / CPU / disk, the resolved config,
# and every DIG_* env var (sensitive values masked) — designed to be
# the first thing in any support-ticket attachment.
"$PY" "$SCRIPT_DIR/dig_startup_info.py" --target "$API_LOG" --target "$WEB_LOG" \
  || err "[dig start] startup banner failed (continuing)"

# Rotator wrapper: spawns the wrapped service, captures stdout+stderr,
# writes through Python's RotatingFileHandler with the configured caps,
# forwards SIGTERM/SIGINT/SIGHUP to the child. dig-stop kills the
# wrapper PID; the wrapper propagates and waits for clean shutdown.
ROT=("$PY" "$SCRIPT_DIR/dig_log_rotate.py"
     --max-bytes "$LOG_MAX_BYTES"
     --backup-count "$LOG_BACKUP_COUNT")

cd "$REPO_ROOT/backend"
DIG_HOST="$API_HOST" DIG_PORT="$API_PORT" \
  "${START_PREFIX[@]}" "${ROT[@]}" --file "$API_LOG" -- \
    "$REPO_ROOT/backend/.venv/bin/dig-api" \
    < /dev/null > /dev/null 2>&1 &
API_PID=$!

# next dev — only pin NEXT_PUBLIC_DIG_API for LOCAL mode. In global mode we
# leave it unset so the frontend's runtime default ( `window.location.hostname`
# ) kicks in — that way visiting `http://10.0.0.5:3100` from a phone on the
# LAN talks to the backend at `http://10.0.0.5:8190`, not the phone's own
# localhost. See `_resolveApiBase()` in frontend/lib/api/client.ts.
cd "$REPO_ROOT/frontend"
NEXT_API_ENV=()
if ! is_global_bind "$API_HOST"; then
  NEXT_API_ENV=(NEXT_PUBLIC_DIG_API="http://$API_HOST:$API_PORT")
fi
# Tell the frontend bundle which port answers HTTPS, so the API client
# can route page-on-https → api-on-https-port without hardcoding 8443.
# Picked up by ``frontend/lib/api/client.ts``.
if [[ "$TLS_READY" -eq 1 ]]; then
  NEXT_API_ENV+=(NEXT_PUBLIC_DIG_API_HTTPS_PORT="$API_HTTPS_PORT")
  # Node trusts the cert at runtime via NODE_EXTRA_CA_CERTS — important
  # when Next's SSR side fetches the API on https. Without it Node
  # rejects the self-signed handshake even if the OS trust store accepts
  # it.
  export NODE_EXTRA_CA_CERTS="$DIG_TLS_CERT"
fi

env "${NEXT_API_ENV[@]}" PORT="$WEB_PORT" HOSTNAME="$WEB_HOST" \
  "${START_PREFIX[@]}" "${ROT[@]}" --file "$WEB_LOG" -- \
    pnpm dev --port "$WEB_PORT" --hostname "$WEB_HOST" \
    < /dev/null > /dev/null 2>&1 &
WEB_PID=$!

# TLS proxy — only when cert was successfully prepared. Listens on
# api.httpsPort + web.httpsPort, terminates TLS, forwards to the plain
# HTTP backends started above. Wrapped in the rotator like the other two
# services so its log rotates the same way.
PROXY_PID=""
if [[ "$TLS_READY" -eq 1 ]]; then
  PROXY_LOG="$LOG_DIR/dig-tls-proxy.log"
  "$PY" "$SCRIPT_DIR/dig_startup_info.py" --target "$PROXY_LOG" \
    > /dev/null 2>&1 || true
  "${START_PREFIX[@]}" "${ROT[@]}" --file "$PROXY_LOG" -- \
    "$PY" "$SCRIPT_DIR/dig_tls_proxy.py" \
      --cert "$DIG_TLS_CERT" --key "$DIG_TLS_KEY" \
      --host "$API_HOST" \
      --forward "${API_HTTPS_PORT}:${API_PORT}" \
      --forward "${WEB_HTTPS_PORT}:${WEB_PORT}" \
    < /dev/null > /dev/null 2>&1 &
  PROXY_PID=$!
fi

# Persist PIDs so dig-stop can find them. The TLS proxy is recorded as
# an extra entry when present so dig-stop can tear it down too — without
# this the rotator survives the api/web kills and keeps re-spawning a
# zombie listener until the user finds it manually.
"$PY" - "$PID_FILE" "$API_PID" "$WEB_PID" "${PROXY_PID:-}" \
       "$API_PORT" "$WEB_PORT" "${API_HTTPS_PORT}" "${WEB_HTTPS_PORT}" \
       "$API_LOG" "$WEB_LOG" "${PROXY_LOG:-}" <<'PYEOF'
import json, sys
(path, api_pid, web_pid, proxy_pid,
 api_port, web_port, api_https_port, web_https_port,
 api_log, web_log, proxy_log) = sys.argv[1:]
data = {
    "api": {"pid": int(api_pid), "port": int(api_port), "log": api_log},
    "web": {"pid": int(web_pid), "port": int(web_port), "log": web_log},
}
if proxy_pid:
    data["tls_proxy"] = {
        "pid": int(proxy_pid),
        "https_ports": {"api": int(api_https_port), "web": int(web_https_port)},
        "log": proxy_log or "",
    }
with open(path, "w") as f:
    json.dump(data, f, indent=2)
PYEOF

# Wait for both endpoints to start serving. We probe the HTTP path
# (always available) — the TLS proxy comes up almost instantly once both
# backends are listening, so a separate HTTPS readiness probe just slows
# the start banner without adding signal.
ready_api=0
ready_web=0
for i in $(seq 1 60); do
  if [[ "$ready_api" -eq 0 ]] && curl -sf "http://$API_HOST:$API_PORT/health" >/dev/null 2>&1; then
    ready_api=1
    echo "[dig start] api ready (${i}s)"
  fi
  # Round-3 regression: previous form was `-o /dev/null ... 2>&1` which
  # left stderr streaming to the operator's terminal — every retry while
  # Next.js was still booting printed connection-refused chatter. Match
  # the api-ready line above: silence both streams completely.
  if [[ "$ready_web" -eq 0 ]] && curl -sf "http://$WEB_HOST:$WEB_PORT/" >/dev/null 2>&1; then
    ready_web=1
    echo "[dig start] web ready (${i}s)"
  fi
  if [[ "$ready_api" -eq 1 && "$ready_web" -eq 1 ]]; then break; fi
  sleep 1
done

if [[ "$ready_api" -eq 0 || "$ready_web" -eq 0 ]]; then
  err "[dig start] one or both services failed to start within 60s."
  err "  api log: $API_LOG"
  err "  web log: $WEB_LOG"
  exit 3
fi

echo
echo "✅ DIG is running."
echo

if is_global_bind "$WEB_HOST"; then
  echo "   ACCESS MODE: 🌐 LAN-wide (any device on your network can reach DIG)"
  echo
  echo "   Open the web UI at any of:"
  echo "     • http://localhost:$WEB_PORT          (this machine)"
  [[ "$TLS_READY" -eq 1 ]] && echo "     • https://localhost:$WEB_HTTPS_PORT          (this machine, TLS)"
  hn="$(local_hostname)"
  if [[ -n "$hn" ]]; then
    echo "     • http://$hn:$WEB_PORT"
    [[ "$TLS_READY" -eq 1 ]] && echo "     • https://$hn:$WEB_HTTPS_PORT"
  fi
  while IFS= read -r ip; do
    if [[ -n "$ip" ]]; then
      echo "     • http://$ip:$WEB_PORT"
      [[ "$TLS_READY" -eq 1 ]] && echo "     • https://$ip:$WEB_HTTPS_PORT"
    fi
  done < <(list_lan_addresses)
  echo
  if [[ -n "${DIG_AUTH_TOKEN:-}" ]]; then
    echo "   🔑 Auth token active. Stored at ${USER_CFG_DIR}/auth.token (chmod 600)."
    echo "      Devices on the LAN need to attach Authorization: Bearer <token>"
    echo "      to API calls. The local frontend already picks it up via"
    echo "      NEXT_PUBLIC_DIG_AUTH_TOKEN; remote integrations need the value."
    echo "      Print it: cat ${USER_CFG_DIR}/auth.token"
    echo
  else
    echo "   ⚠ SECURITY: no API auth token is set. Anyone on your network can"
    echo "     read every dataset, edit every pipeline, and trigger backend runs."
    echo "     For more than a quick demo, set NEXT_PUBLIC_DIG_AUTH_TOKEN +"
    echo "     DIG_AUTH_TOKEN, or stop the service with ./scripts/dig-stop.sh"
    echo "     and restart with --local."
    echo
  fi
else
  echo "   ACCESS MODE: 🔒 local-only (only this machine can reach DIG)"
  echo
  echo "   Open the web UI:"
  echo "     • http://localhost:$WEB_PORT"
  [[ "$TLS_READY" -eq 1 ]] && echo "     • https://localhost:$WEB_HTTPS_PORT  (TLS, self-signed)"
  echo
  echo "   To make DIG reachable from other devices on your network, restart with:"
  echo "     ./scripts/dig-restart.sh --global   # this run"
  echo "     ./scripts/dig-start.sh --global --save   # remember it"
  echo
fi

# TLS subsection — only printed when the proxy is running. Shows
# fingerprint + trust state so the operator can spot-check the cert in
# their browser's "View certificate" dialog and confirm it's the one we
# generated. The HTTP path always works regardless of trust state, so
# this is informational rather than a setup requirement.
if [[ "$TLS_READY" -eq 1 ]]; then
  TLS_FP="$("$PY" - <<PYEOF 2>/dev/null
import json, subprocess, sys
r = subprocess.run(
    ["${SCRIPT_DIR}/dig_tls.py", "info"],
    capture_output=True, text=True,
)
try:
    info = json.loads(r.stdout)
except Exception:
    print("(unavailable)"); sys.exit(0)
print(info.get("fingerprint_sha256", "(unavailable)"))
PYEOF
)"
  echo "   🔐 TLS:  also reachable on https://*:$WEB_HTTPS_PORT (web) · https://*:$API_HTTPS_PORT (api)"
  echo "        SHA-256 ${TLS_FP:0:32}…"
  echo "        cert: $DIG_TLS_CERT"
  if "$PY" "$SCRIPT_DIR/dig_tls.py" info 2>/dev/null | grep -q '"trusted_in_system_store": true'; then
    echo "        ✓ installed in system trust store — browsers accept it silently"
  else
    echo "        ⚠ self-signed cert NOT yet in system trust store — HTTPS works but"
    echo "          browsers show a 'Not Secure' warning. Run once to fix:"
    echo "             ./scripts/dig_tls.py trust    (one-time sudo install)"
    echo "          (Or just keep using the http:// URLs above — they don't need trust.)"
  fi
  echo
fi

echo "   api:  http://$API_HOST:$API_PORT$([[ "$TLS_READY" -eq 1 ]] && echo "  ·  https://$API_HOST:$API_HTTPS_PORT")"
echo "   pids: api=$API_PID web=$WEB_PID$([[ -n "${PROXY_PID:-}" ]] && echo " tls-proxy=$PROXY_PID")"
echo "   logs: $API_LOG  ·  $WEB_LOG$([[ "$TLS_READY" -eq 1 ]] && echo "  ·  $PROXY_LOG")"
echo "   stop: ./scripts/dig-stop.sh"
