/**
 * Translate raw DuckDB / DuckDB-WASM error messages into actionable
 * one-liners that name the exact column / step the user should fix.
 *
 * The DuckDB Binder error surface is verbose and mentions internal
 * concepts ("REPLACE list", "FROM clause") the user can't act on. We
 * pattern-match the common ones and produce a sentence that ends in
 * "available columns: a, b, c" so the user sees both what's wrong and
 * what choices they have.
 */

export interface HumanizedError {
  /** Short user-facing message — show prominently. */
  title: string;
  /** Optional follow-up hint — show smaller below the title. */
  hint?: string;
  /** True when we recognised the pattern; false = we passed the raw message through. */
  recognised: boolean;
}

// "Binder Error: Column "X" in REPLACE list not found in FROM clause"
const _REPLACE_LIST_RE = /Binder\s*Error:\s*Column\s*"([^"]+)"\s*in\s*REPLACE\s*list\s*not\s*found/i;
// "Binder Error: Referenced column "X" not found in FROM clause"
const _REFERENCED_COL_RE = /Binder\s*Error:\s*Referenced\s*column\s*"([^"]+)"\s*not\s*found/i;
// "Binder Error: Column X not found in any table"
const _COLUMN_NOT_FOUND_RE = /Binder\s*Error:\s*Column\s*"?([^"\s]+)"?\s*not\s*found/i;
// "Catalog Error: Table with name X does not exist"
const _TABLE_NOT_FOUND_RE = /Catalog\s*Error:\s*Table\s*with\s*name\s*([^\s!]+)\s*does\s*not\s*exist/i;
// "Conversion Error: Could not convert string '...' to ..."
const _CONVERSION_RE = /Conversion\s*Error:\s*Could\s*not\s*(?:convert|cast)\s*([^\n]+)/i;
// "Parser Error: syntax error at or near \"X\""
const _PARSER_RE = /Parser\s*Error:\s*([^\n]+)/i;

function _availableHint(availableColumns: string[]): string {
  if (availableColumns.length === 0) {
    return "No columns visible at this step.";
  }
  const max = 12;
  const shown = availableColumns.slice(0, max);
  const more = availableColumns.length - max;
  return `Available columns: ${shown.join(", ")}${more > 0 ? ` (+${more} more)` : ""}.`;
}

export function humanizeSqlError(
  raw: string,
  availableColumns: string[] = [],
): HumanizedError {
  // Column-in-REPLACE pattern — most common after a cast on a column the
  // upstream step dropped or renamed.
  let m = raw.match(_REPLACE_LIST_RE);
  if (m) {
    return {
      title: `Column “${m[1]}” doesn't exist at this step.`,
      hint: `An upstream step dropped or renamed it before the cast / replace ran. ${_availableHint(availableColumns)}`,
      recognised: true,
    };
  }

  m = raw.match(_REFERENCED_COL_RE);
  if (m) {
    return {
      title: `Column “${m[1]}” isn't visible at this step.`,
      hint: `${_availableHint(availableColumns)} Edit the focused step's params to point at one of these.`,
      recognised: true,
    };
  }

  m = raw.match(_COLUMN_NOT_FOUND_RE);
  if (m) {
    return {
      title: `Column “${m[1]}” not found.`,
      hint: _availableHint(availableColumns),
      recognised: true,
    };
  }

  m = raw.match(_TABLE_NOT_FOUND_RE);
  if (m) {
    return {
      title: `Step or dataset “${m[1]}” isn't wired in.`,
      hint: "An input reference points at something that no longer exists. Check the canvas for a broken connection.",
      recognised: true,
    };
  }

  m = raw.match(_CONVERSION_RE);
  if (m) {
    return {
      title: "Can't cast some values to the target type.",
      hint: `${m[1].trim()} — try Strict=off (which converts bad values to NULL), or pre-clean the column first.`,
      recognised: true,
    };
  }

  m = raw.match(_PARSER_RE);
  if (m) {
    return {
      title: "SQL syntax error in this step's expression.",
      hint: m[1].trim(),
      recognised: true,
    };
  }

  // Pass through unrecognized errors but trim the leading "X Error:" prefix
  // that DuckDB usually prepends.
  const cleaned = raw.replace(/^[A-Z][a-z]+\s*Error:\s*/, "").trim();
  return { title: cleaned || raw, recognised: false };
}
