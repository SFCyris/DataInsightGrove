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
  /**
   * True when the error did NOT originate from the focused step's params
   * — it came from upstream (a broken dataset registration, a missing
   * input, a Polars-only step compiled for the browser engine, etc.).
   * The page uses this to suppress "✨ Suggest fix", since changing the
   * focused step's params can't repair an upstream problem and offering
   * the AI a doomed prompt produces misleading "fixes".
   */
  originatesUpstream?: boolean;
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

// ── Chart-step (export_to_image) errors. The renderer raises ValueError
// with a single short sentence; we recognise each one and turn it into a
// "what to do next" hint that picks specific columns from `availableColumns`
// where useful. See backend/steps/export_to_image/step.py:_render_*.
const _CHART_NEEDS_XY_RE = /^(scatter|line|hexbin)\s+needs\s+both\s+x\s+and\s+y$/i;
const _CHART_HEATMAP_RE = /^heatmap\s+needs\s+x,\s+y\s+and\s+value$/i;
const _CHART_SCATTER3D_RE = /^scatter3d\s+needs\s+x,\s+y\s+and\s+z$/i;
const _CHART_UNKNOWN_KIND_RE = /export_to_image:\s+unknown\s+kind\s+'([^']+)'/i;

// ── Chart-pack steps from plugins/packs/business_charts (funnel, pareto,
// waterfall). They share the "no non-null rows" guard at the start of
// `execute_polars`. The chart's input was either empty or every row had
// NULL in the value column — a render of nothing isn't a render.
//   "funnel_chart: no non-null rows"
//   "pareto_chart: no non-null rows"
//   "waterfall_chart: no non-null rows"
const _CHART_NO_ROWS_RE = /^(funnel_chart|pareto_chart|waterfall_chart):\s+no\s+non-null\s+rows$/i;

// ── Polars column-not-found. Format is just the bare column name in the
// exception's str(): "polars.exceptions.ColumnNotFoundError: foo" or
// (after FastAPI wraps it) "...: unable to find column "foo"".
const _POLARS_COL_RE = /(?:ColumnNotFoundError|unable\s*to\s*find\s*column)\s*:?\s*"?([^"\n]+?)"?(?:\s|;|$)/i;

// ── Polars-only step picked as the focused/terminal node. The browser
// engine compiles to SQL only; steps with `browser: "none"` (e.g.
// export_to_image, forecast, …) raise this from compile_for_browser.
//   "step 'export_to_image' has browser engine 'none'; only 'sql' is supported in compile_for_browser"
const _NO_BROWSER_ENGINE_RE = /step\s+'([^']+)'\s+has\s+browser\s+engine\s+'([^']+)'/i;

// ── Dataset-loading errors (upstream of any step). DuckDB raises these
// from the CTE that wraps the dataset's source URI in read_csv_auto /
// read_parquet / read_json_auto. The most common case is a Parquet file
// that was registered as CSV (or vice versa) — the auto-sniffer fails
// before any step's logic runs. The fix can't come from the focused
// step's params; the user has to re-import or fix the dataset entry.
//   "Invalid Input Error: Error when sniffing file "/path/to/file.parquet". …"
//   "IO Error: Could not open file "/path/to/file": ..."
//   "IO Error: No such file or directory: '/path/to/file'"
const _DATASET_SNIFF_RE = /Error\s+when\s+sniffing\s+file\s+"([^"]+)"/i;
const _IO_OPEN_RE = /IO\s*Error:\s*(?:Could\s*not\s*open\s*file|No\s*such\s*file)/i;

// ── Manifest param validation (dag.py:validate_params_against_manifests).
// Format examples:
//   "invalid params: node 'n_x'.width: expected integer, got str"
//   "invalid params: node 'n_x'.width: 5000 > max 4000"
//   "invalid params: node 'n_x'.width: -10 < min 200"
//   "invalid params: node 'n_x': required param 'kind' missing"
const _PARAM_REQUIRED_RE = /node\s+'[^']+':\s*required\s+param\s+'([^']+)'\s+missing/i;
const _PARAM_TYPE_RE = /node\s+'[^']+'\.([^:]+):\s*expected\s+(\w+),\s*got\s+(\w+)/i;
const _PARAM_BOUNDS_RE = /node\s+'[^']+'\.([^:]+):\s*(-?\d+(?:\.\d+)?)\s*([<>])\s*(min|max)\s*(-?\d+(?:\.\d+)?)/i;
const _PARAM_ENUM_RE = /node\s+'[^']+'\.([^:]+):\s*'([^']*)'\s+not\s+in\s+enumValues/i;

function _availableHint(availableColumns: string[]): string {
  if (availableColumns.length === 0) {
    return "No columns visible at this step.";
  }
  const max = 12;
  const shown = availableColumns.slice(0, max);
  const more = availableColumns.length - max;
  return `Available columns: ${shown.join(", ")}${more > 0 ? ` (+${more} more)` : ""}.`;
}

/** Suggest a numeric column from the schema (e.g. for scatter X/Y). */
function _suggestNumeric(availableColumns: string[]): string | null {
  // We don't know types here, but column names that look numeric (end in
  // _z, _id, contain "count"/"rate"/"value") are decent guesses; otherwise
  // just return the first column. If the caller has type info it can pass
  // a smarter pre-filtered list.
  if (availableColumns.length === 0) return null;
  const numericish = availableColumns.find((c) =>
    /(_z|_count|_rate|_value|count|rate|value|amount|price|qty|num)$/i.test(c),
  );
  return numericish ?? availableColumns[0];
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
      // A missing input reference can't be fixed by editing the focused
      // step's params — the canvas wiring needs adjusting.
      originatesUpstream: true,
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

  // ── Chart-step errors (export_to_image). These are short ValueError
  // messages from the renderer; turn each one into a "pick X / Y / Z" hint.
  m = raw.match(_CHART_NEEDS_XY_RE);
  if (m) {
    const kind = m[1].toLowerCase();
    const suggestion = _suggestNumeric(availableColumns);
    return {
      title: `${kind} charts need both an X and a Y column.`,
      hint: suggestion
        ? `Try X = “${suggestion}” and a different numeric column for Y. ${_availableHint(availableColumns)}`
        : `Pick a numeric column for X and another for Y. ${_availableHint(availableColumns)}`,
      recognised: true,
    };
  }

  m = raw.match(_CHART_HEATMAP_RE);
  if (m) {
    return {
      title: "Heatmap needs X, Y and a Value column.",
      hint: `X + Y label the rows/columns of the grid; Value fills each cell with a number to colour. ${_availableHint(availableColumns)}`,
      recognised: true,
    };
  }

  m = raw.match(_CHART_SCATTER3D_RE);
  if (m) {
    return {
      title: "3-D scatter needs X, Y and Z columns.",
      hint: `Pick three numeric columns — Z is the depth axis. ${_availableHint(availableColumns)}`,
      recognised: true,
    };
  }

  m = raw.match(_CHART_UNKNOWN_KIND_RE);
  if (m) {
    return {
      title: `Unknown chart kind “${m[1]}”.`,
      hint: "Pick one of: histogram, bar_counts, scatter, line, hexbin, heatmap, scatter3d. Or set 'auto' to let DIG choose by column types.",
      recognised: true,
    };
  }

  m = raw.match(_CHART_NO_ROWS_RE);
  if (m) {
    const chart = m[1].replace("_chart", "");
    return {
      title: `${chart} chart has no rows to plot.`,
      hint:
        "Every input row has NULL in the value column, or the upstream step yielded zero rows. " +
        "Check that the value column has non-null values and that any upstream filter / aggregate hasn't reduced the result to empty. " +
        _availableHint(availableColumns),
      recognised: true,
    };
  }

  // ── Polars-only step focused as terminal. These steps emit artifacts
  // (images, files, forecasts) and have no live tabular preview. The
  // hint nudges the user toward the actual mechanism: run on backend to
  // produce the artifact, or focus the upstream step to inspect its data.
  m = raw.match(_NO_BROWSER_ENGINE_RE);
  if (m) {
    return {
      title: "This step doesn't have a live preview.",
      hint: `“${m[1]}” produces an artifact (image / file / forecast), not a tabular result that can stream into the grid. Click ▶ Run on backend to produce the output, or click the upstream step to preview its rows.`,
      recognised: true,
      // Not really an "upstream" error in the dataset sense, but it's
      // also not fixable by changing the focused step's params — the
      // step ran fine, the browser just can't render its output. Treat
      // as upstream-class so the same gating logic applies.
      originatesUpstream: true,
    };
  }

  // ── Dataset auto-sniffing failed (e.g. parquet file registered as CSV).
  m = raw.match(_DATASET_SNIFF_RE);
  if (m) {
    const path = m[1];
    const looksParquet = /\.parquet$/i.test(path);
    const looksJson = /\.(?:json|jsonl|ndjson)$/i.test(path);
    const filename = path.split("/").pop() || path;
    return {
      title: looksParquet
        ? `“${filename}” is a Parquet file, but DIG is reading it as CSV.`
        : looksJson
          ? `“${filename}” is a JSON file, but DIG is reading it as CSV.`
          : `Couldn't auto-detect the CSV dialect for “${filename}”.`,
      hint: looksParquet || looksJson
        ? "The dataset's format detection picked the wrong reader. Re-import the dataset (📥 Add dataset) so it picks the correct format. Step-level fixes can't repair an upstream dataset registration."
        : "Open the dataset's settings to set delimiter / quote / encoding, or re-import. Step-level params can't fix an upstream load error.",
      recognised: true,
      originatesUpstream: true,
    };
  }

  // ── Generic file-open / not-found IO error (dataset source moved or
  // permissions changed). Always upstream of any step.
  m = raw.match(_IO_OPEN_RE);
  if (m) {
    return {
      title: "Couldn't open the dataset's source file.",
      hint: "The file at the dataset's source URI is missing or unreadable. Check the path, then re-import the dataset. Step-level fixes can't repair an upstream load error.",
      recognised: true,
      originatesUpstream: true,
    };
  }

  // ── Polars ColumnNotFoundError (raised by df.get_column when the column
  // the user picked has been dropped or renamed by an upstream step).
  m = raw.match(_POLARS_COL_RE);
  if (m) {
    return {
      title: `Column “${m[1]}” isn't visible at this step.`,
      hint: `${_availableHint(availableColumns)} Edit the focused step's params to point at one of these.`,
      recognised: true,
    };
  }

  // ── Manifest param validation (dag.py: validate_params_against_manifests).
  m = raw.match(_PARAM_REQUIRED_RE);
  if (m) {
    return {
      title: `Required param “${m[1]}” is missing.`,
      hint: "Fill in this field — most fields auto-preview the moment you finish typing.",
      recognised: true,
    };
  }

  m = raw.match(_PARAM_TYPE_RE);
  if (m) {
    return {
      title: `“${m[1]}” needs a ${m[2]}, got ${m[3]}.`,
      hint:
        m[2] === "integer" || m[2] === "number"
          ? "Clear the field and re-enter a number — empty numeric fields fall back to defaults, but typing letters won't."
          : `Edit “${m[1]}” to a valid ${m[2]} value.`,
      recognised: true,
    };
  }

  m = raw.match(_PARAM_BOUNDS_RE);
  if (m) {
    const [, name, , , bound, limit] = m;
    return {
      title: `“${name}” is outside the allowed range.`,
      hint: `${bound} is ${bound === "min" ? "below" : "above"} the ${bound} of ${limit}. Adjust the field within bounds.`,
      recognised: true,
    };
  }

  m = raw.match(_PARAM_ENUM_RE);
  if (m) {
    return {
      title: `“${m[1]}” isn't one of the allowed choices.`,
      hint: `Got “${m[2]}”. The dropdown lists the valid options for this step.`,
      recognised: true,
    };
  }

  // "invalid params: ..." prefix without a known sub-pattern — strip the
  // prefix so the user at least sees the underlying validator message.
  if (raw.startsWith("invalid params:")) {
    return {
      title: raw.replace(/^invalid params:\s*/, "").trim() || raw,
      hint: "Edit the focused step's params to fix the validation error above.",
      recognised: true,
    };
  }

  // Pass through unrecognized errors but trim the leading "X Error:" prefix
  // that DuckDB usually prepends.
  const cleaned = raw.replace(/^[A-Z][a-z]+\s*Error:\s*/, "").trim();
  return { title: cleaned || raw, recognised: false };
}
