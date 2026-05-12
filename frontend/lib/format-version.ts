/**
 * Canonical user-visible version-string formatter.
 *
 * The codebase carries the version in three places, in three formats
 * dictated by the file's ecosystem:
 *
 *   - `backend/pyproject.toml` → PEP 440 (`1.0.0rc1`, no separator)
 *   - `frontend/package.json`  → npm semver (`1.0.0-rc.1`, hyphen + dot)
 *   - `README.md` badge        → `1.0.0-rc1` (hyphen, no dot)
 *
 * The frontend reads `/health.version` which is whatever pyproject.toml
 * shipped (PEP 440). This formatter normalises it to the canonical
 * user-visible form (`1.0.0-rc1`) so the home-page chip, settings
 * "Backend" stat, and footer all match the README badge.
 *
 * Round-2 UX-tester finding: previously three contradictory spellings
 * appeared on the same screen because each surface displayed the raw
 * string from its own ecosystem.
 */
export function fmtVersion(raw: string | null | undefined): string {
  if (!raw) return "—";
  // PEP 440 pre-releases: `1.0.0rc1`, `1.0.0a2`, `1.0.0b3`, `1.0.0.dev4`.
  // Insert a hyphen between the release and the pre-release tag so the
  // result reads `1.0.0-rc1` / `1.0.0-a2` / etc.
  return raw.replace(/^(\d+\.\d+\.\d+)(rc|a|b|alpha|beta|dev|post)/i, "$1-$2");
}
