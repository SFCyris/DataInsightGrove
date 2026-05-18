# Security Policy

## Threat model

DIG runs in two deployment shapes today:

1. **Single-user local install** — `pip install` on a developer machine, accessed via loopback. No auth gate. The threat model assumes the host machine is trusted; DIG's job is to refuse to do dangerous things on behalf of an attacker who *did* reach the API (e.g. via a malicious browser tab making a same-origin request).
2. **LAN install with bearer-token gate** — `DIG_AUTH_TOKEN` set in the environment; all API + WebSocket requests require the token. The threat model adds: the attacker has network reach to the host but does not have the token.

Multi-user / multi-tenant deployments are not yet supported in OSS. Those scenarios are covered by the planned Enterprise tier (see `internal/TIER_ARCHITECTURE.md`).

### What we defend against

- **Expression injection** — user-supplied SQL fragments (filter predicates, derive-column expressions, validation expressions) are passed through `dig.engine.step.assert_safe_expr`, which tokenises + denylists DDL / DML / file IO / cloud IO / introspection functions. Multi-statement separators, SQL comments, and quoted-form bypasses are all rejected.
- **SSRF / arbitrary file IO via DuckDB** — the safe-expression validator denies `read_csv`, `read_parquet`, `httpfs`, `s3`, `attach`, `pragma`, etc. The local-file connectors share a `assert_local_path_safe` helper that confines reads to `data_dir()` + `samples/` (or an explicit `DIG_LOCAL_FILE_ALLOW_ABSOLUTE` escape hatch).
- **Pack supply chain** — `pythonRequirements` in pack manifests is validated against a strict PEP-508 subset; URL / VCS / path forms (`git+`, `pkg @ url`, `./local`, `-e`) and pip flags are rejected. Install runs `pip install --isolated --index-url https://pypi.org/simple/ -- <reqs>` so a malicious pack cannot redirect the index.
- **AI plugin sandbox** — generated step / connector code is parsed AST-side; allowlisted imports only, with explicit denies for code-exec, process-spawn, pickle, raw sockets, Polars IO (read/scan/write/sink), and reflection that would defeat the lint.
- **Path traversal in artifact serving** — `/runs/{run_id}/artifact` validates the run ID format + DB existence before resolving the path, then `Path.resolve().relative_to(safe_root)` confirms the result stayed inside the run directory (catches symlink escapes).
- **Template injection in variable rendering** — the `{{ }}` template renderer in `dig.engine.templates` is a hand-written sandboxed parser (not Jinja2); no control flow, no attribute walking, no Python `eval`. Filter set is closed. Path rendering enforces cross-OS character bans + traversal rejection.
- **Resource exhaustion** — request bodies are capped at `DIG_MAX_BODY_BYTES` (default 32 MiB); WebSocket frames at `DIG_WS_MAX_BYTES` (default 1 MiB); `/validate` per-node compile probe at `DIG_VALIDATE_MAX_NODES`.
- **WebSocket auth** — `ws://…?token=` validated via `secrets.compare_digest`; uvicorn access logs redact `token=`.
- **Webhooks (outbound)** — receiver signature via HMAC-SHA256 when a `secret` is configured. `http://` allowed for loopback / LAN; `https://` recommended for anything else.
- **REST/HTTPS connector** — SSRF allowlist, 100 MB body cap, scheme gate to block `file://` / `gopher://` / etc.
- **JDBC connector** — table-name regex; SQL denylist closes the quoted-identifier bypass.

### What we don't defend against (yet)

- **Multi-user authentication / authorization** — there is no user model, no RBAC, no audit log. The database schema has been pre-shaped to accept those columns (see `internal/TIER_ARCHITECTURE.md` § 4.2), but the auth provider, policy engine, and audit writer ship with the Enterprise tier.
- **Data residency / VPC isolation** — single-tenant, single-host.
- **Side-channel attacks on co-tenants** — not applicable to the OSS deployment model.
- **Denial-of-service against the loopback gateway** — out of scope; deploy behind a real reverse proxy if exposed.

## Reporting a vulnerability

Please report security issues privately to **scyris@outlook.com** with subject prefix `[DIG security]`.

We aim to:

- Acknowledge receipt within 3 business days.
- Provide a triage assessment within 7 business days.
- Coordinate a fix + disclosure timeline with the reporter for confirmed issues.

Please **do not** open a public GitHub issue or pull request for an unpatched vulnerability. If you need an encrypted channel, request one in your first email and we will provide a PGP fingerprint.

Reports that follow the principle of [coordinated disclosure](https://www.first.org/global/sigs/vulnerability-coordination/multiparty/) will be credited (with permission) in the release notes that ship the fix.

## Supported versions

Current pre-release: **1.0.0-rcN** — receives every security fix
shipped during the rc cycle. The final 0.10.x line still receives
critical security fixes through GA of 1.0.0; thereafter it is
end-of-life.

Older minor versions (`<0.10`): no security backports. Upgrade.

Once 1.0.0 GAs, the support window becomes: **current minor + previous minor**, with security backports to both for at least 90 days after the current minor's release.

## Known security-relevant configuration

- `DIG_AUTH_TOKEN` — set to require a bearer token on every API + WebSocket request. Strongly recommended for any non-loopback exposure.
- `DIG_LOCAL_FILE_ALLOW_ABSOLUTE` — opt-in escape from the local-file path confinement. Use only when you understand the implication that any file the DIG process can read becomes ingestable.
- `DIG_PACK_AUTO_INSTALL_DEPS` — opt-in auto-install of pack `pythonRequirements`. Disable for stricter supply-chain control.
- `DIG_PIP_INDEX_URL` — override the index pack auto-install reads from. Use to point at an internal mirror.
- `DIG_VALIDATE_MAX_NODES`, `DIG_MAX_BODY_BYTES`, `DIG_WS_MAX_BYTES` — resource-exhaustion guardrails.

See [`docs/CONFIG.md`](docs/CONFIG.md) for the full list.
