# 📚 DataInsightGrove — Step library

This page documents every step DIG ships with. It is **auto-generated** from each step's `manifest.json` plus optional hand-written notes under `docs/_steps/<step_id>.md` — re-run `python scripts/gen-steps-doc.py` whenever you add or change a step.

**46 steps** across ✂️ Shape (7), 🧼 Clean (8), 🪄 Derive (9), 🤝 Combine (3), 📊 Aggregate (5), 📤 Output (5).

## Index

### ✂️ Shape

- [🔍 Filter rows](#filter-rows) — Keep rows where the predicate evaluates to true.
- [✏️ Rename columns](#rename-columns) — Rename one or more columns.
- [↔️ Reorder columns](#reorder-columns) — Reorder the columns of the input.
- [🎲 Sample rows](#sample-rows) — Take a random or head/tail sample of rows.
- [📋 Select columns](#select-columns) — Keep only the chosen columns, in the chosen order.
- [↕️ Sort rows](#sort-rows) — Order rows by one or more columns.
- [✂️ Split column](#split-column) — Split a string column on a delimiter into N new columns (named col_1, col_2, …).

### 🧼 Clean

- [🔄 Cast type](#cast-type) — Change the data type of a column.
- [🧽 Clean whitespace](#clean-whitespace) — Trim leading/trailing whitespace and optionally collapse runs of internal whitespace into a single space.
- [🪢 Coalesce columns](#coalesce-columns) — First non-null wins.
- [🪞 Deduplicate](#deduplicate) — Keep one row per group of duplicates.
- [✅ Data quality expectations](#data-quality-expectations) — Assert data quality rules (column.
- [🔤 Replace text](#replace-text) — Find-and-replace inside a string column.
- [🎯 Round numeric](#round-numeric) — Round a numeric column to N decimal places.
- [🆙 Uppercase string](#uppercase-string) — Convert a string column to uppercase.

### 🪄 Derive

- [🆕 Add column](#add-column) — Add a new column with a typed default value.
- [📦 Bin numeric](#bin-numeric) — Bucket a numeric column into N equal-width bins, or into custom breakpoints.
- [🧭 Convert coordinates](#convert-coordinates) — Lossless conversion between polar, Cartesian, and geographic coordinate systems.
- [➕ Derive column](#derive-column) — Add a new column computed from a SQL expression over existing columns.
- [📅 Extract date parts](#extract-date-parts) — Pull year, month, day, day-of-week (etc.
- [🎯 Extract pattern](#extract-pattern) — Extract a regex group from a string column into a new column.
- [🧮 Math equation](#math-equation) — Add a column computed from a math expression over existing columns.
- [🌊 Rolling window](#rolling-window) — Add rolling-window aggregations (moving average, rolling sum, etc.
- [📐 Z-score](#z-score) — Add a standardized (mean=0, std=1) version of a numeric column as a new column.

### 🤝 Combine

- [🔗 Join](#join) — Combine two datasets on matching key columns.
- [🧩 Sub-pipeline](#sub-pipeline) — Embed another saved pipeline as a single step.
- [🔀 Union](#union) — Stack two datasets vertically.

### 📊 Aggregate

- [📊 Group & aggregate](#group--aggregate) — Group rows by one or more columns and compute aggregate metrics.
- [↕️ Pivot longer](#pivot-longer) — Stack multiple value columns into key/value rows.
- [↔️ Pivot wider](#pivot-wider) — Spread distinct values of a column into separate columns.
- [⏱ Resample (time bucket aggregate)](#resample-time-bucket-aggregate) — Bucket rows into fixed time intervals (e.
- [🪟 Window aggregate](#window-aggregate) — Add a column computed over a rolling/cumulative window — running sum, rank, lead/lag, etc.

### 📤 Output

- [🗃 Export to database](#export-to-database) — Write the data to a SQL database table.
- [💾 Export to file](#export-to-file) — Write the data to disk in CSV, Parquet, Excel, JSON, or NDJSON.
- [🖼 Export to image](#export-to-image) — Render the data as a PNG/SVG via matplotlib + seaborn.
- [🔌 Export to JDBC](#export-to-jdbc) — Write rows to any JDBC-accessible database — Oracle, DB2, MS SQL Server, Snowflake, Teradata, Vertica, etc.
- [🔔 Trigger webhook](#trigger-webhook) — Fire a webhook from inside this pipeline.

---

## ✂️ Shape

### 🔍 Filter rows

**ID:** `filter_rows` · **Version:** `1.0.0`

Keep rows where the predicate evaluates to true. Predicate is a SQL boolean expression over column names.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: preserves

Tags: `filter` `where`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `predicate` | expression | ✓ | — | Build conditions visually, or switch to SQL mode for full control. |


### ✏️ Rename columns

**ID:** `rename_columns` · **Version:** `1.0.0`

Rename one or more columns. Existing column names appear in the dropdown; type the new name.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `rename`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `mapping` | array |  | — | Renames |


### ↔️ Reorder columns

**ID:** `reorder_columns` · **Version:** `1.0.0`

Reorder the columns of the input. The 'order' list is the explicit final left-to-right column order. Columns that exist in the input but aren't listed are appended at the end (preserving their input order); listed columns that don't exist in the input are skipped — so the step stays robust when upstream schemas change.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `reorder` `rearrange` `move` `order`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `order` | column_refs | ✓ | — | Column order (left to right) |


### 🎲 Sample rows

**ID:** `sample_rows` · **Version:** `1.0.0`

Take a random or head/tail sample of rows. Useful for fast iteration on large data.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: preserves

Tags: `sample` `random` `head`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `kind` | enum |  | `head` | Kind |
| `n` | integer |  | `1000` | Rows |
| `n2` | integer |  | `1000` | Rows |
| `n3` | integer |  | `1000` | Rows |
| `pct` | number |  | `10` | Percent |
| `seed` | integer |  | `42` | Random seed |


### 📋 Select columns

**ID:** `select_columns` · **Version:** `1.0.0`

Keep only the chosen columns, in the chosen order.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `select` `project`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `columns` | column_refs | ✓ | — | Columns to keep |


### ↕️ Sort rows

**ID:** `sort_rows` · **Version:** `1.0.0`

Order rows by one or more columns. Each entry can be ASC or DESC.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

Tags: `sort` `order`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `by` | array |  | — | Sort keys |


### ✂️ Split column

**ID:** `split_column` · **Version:** `1.0.0`

Split a string column on a delimiter into N new columns (named col_1, col_2, …).

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `string` `split`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `column` | column_ref | ✓ | — | Column |
| `delimiter` | string |  | `,` | Delimiter |
| `parts` | integer |  | `2` | Number of parts |
| `drop` | boolean |  | `False` | Drop the original column |


---

## 🧼 Clean

### 🔄 Cast type

**ID:** `cast_type` · **Version:** `1.0.0`

Change the data type of a column. Failed casts become NULL by default.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `cast` `type`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `column` | column_ref | ✓ | — | Column |
| `targetType` | enum | ✓ | `string` | Physical types (integer / double / string / boolean / date / datetime) change the underlying storage. Meta-types map onto a precise physical storage that matches their semantics — currency and percentage use DECIMAL for exact arithmetic, uuid uses native UUID, bignum uses HUGEINT for 128-bit integers (covers hex values that overflow BIGINT). String-shape meta-types (email, url, uuid as text, ip, phone, country, color, timezone) keep VARCHAR. The cast UI shows the most likely fits first based on automatic detection. |
| `strict` | boolean |  | `False` | Off (default): values that don't fit the target type — out-of-range numbers, malformed shapes, overflowed precision — silently become NULL via TRY_CAST. The grid surfaces a 🔄 chip on any cast column with new NULLs so you can audit the loss in the profile drawer.

On: the pipeline fails on the first value that can't be cast. Use when you need a guarantee the data is clean. |


### 🧽 Clean whitespace

**ID:** `clean_whitespace` · **Version:** `1.0.0`

Trim leading/trailing whitespace and optionally collapse runs of internal whitespace into a single space.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

Tags: `string` `trim` `clean`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `column` | column_ref | ✓ | — | Column |
| `collapse` | boolean |  | `True` | Collapse internal whitespace |
| `lowercase` | boolean |  | `False` | Lowercase the result |


### 🪢 Coalesce columns

**ID:** `coalesce_columns` · **Version:** `1.0.0`

First non-null wins. Combine multiple columns into one, dropping the originals if requested.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `coalesce` `merge` `null`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `columns` | column_refs | ✓ | — | Columns (in priority order) |
| `as` | string | ✓ | — | New column name |
| `drop` | boolean |  | `False` | Drop the source columns |


### 🪞 Deduplicate

**ID:** `deduplicate` · **Version:** `1.0.0`

Keep one row per group of duplicates. By default, dedupes on every column; specify a key to dedupe on a subset.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: preserves

Tags: `distinct` `unique` `clean`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `key` | column_refs |  | — | Dedupe by these columns (empty = whole row) |


### ✅ Data quality expectations

**ID:** `expectations` · **Version:** `1.0.0`

Assert data quality rules (column.unique, column.in [...], column.between, row_count.between, etc). Each violation surfaces in the run's artifacts panel; failures can optionally fail the run.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

Tags: `dq` `data-quality` `expectations` `validation`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `rules` | array | ✓ | — | List of objects: {kind, column?, args} where kind ∈ unique \| not_null \| between \| in \| regex_match \| row_count_between. |
| `fail_on_violation` | boolean |  | `False` | If true, the step raises an error and the run is marked failed when any rule reports a violation. |

**Use case + example**

**When to use:** tripwires for data quality. Anything that should always be true about your data — uniqueness, ranges, allowed values, regex patterns — encode as an expectation. The step never modifies the data; it only reports violations and (optionally) fails the run.

**Example:**

```json
{
  "step": "expectations",
  "params": {
    "rules": [
      {"kind": "unique", "column": "customer_id"},
      {"kind": "not_null", "column": "email"},
      {"kind": "between", "column": "age", "min": 0, "max": 120},
      {"kind": "in", "column": "status", "values": ["active", "churned", "trial"]},
      {"kind": "regex_match", "column": "email", "pattern": "^[^@]+@[^@]+\\.[^@]+$"},
      {"kind": "row_count_between", "min": 1000}
    ],
    "fail_on_violation": false
  }
}
```

Each rule produces a result entry; the artifacts panel summarizes "5/6 rules passed" and lists each failure inline.

**Tip:** put `expectations` immediately *before* a sink (export) step. That way you fail fast and the bad data never lands in your downstream warehouse.


### 🔤 Replace text

**ID:** `replace_text` · **Version:** `1.0.0`

Find-and-replace inside a string column. Supports plain substring or regex.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

Tags: `string` `clean` `regex`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `column` | column_ref | ✓ | — | Column |
| `find` | string | ✓ | — | Find |
| `replace` | string |  | `` | Replace with |
| `regex` | boolean |  | `False` | Treat 'find' as regex |


### 🎯 Round numeric

**ID:** `round_to_n` · **Version:** `1.0.0`

Round a numeric column to N decimal places. The column is replaced in place. Worked example from docs/AUTHORING_GUIDE.md.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

Tags: `clean` `numeric` `round`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `column` | column_ref | ✓ | — | Numeric column to round. |
| `decimals` | integer | ✓ | `2` | Decimal places |


### 🆙 Uppercase string

**ID:** `upper_string` · **Version:** `1.0.0`

Convert a string column to uppercase. Hello-world plugin demo.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

Tags: `string` `case` `demo`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `column` | column_ref | ✓ | — | Column |


---

## 🪄 Derive

### 🆕 Add column

**ID:** `add_column` · **Version:** `1.0.0`

Add a new column with a typed default value. The column can be placed at the start or end of the schema, or before/after a chosen reference column. Leave the default blank to seed every row with NULL.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `add` `new` `column` `default` `fill` `constant`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | string | ✓ | — | New column name |
| `columnType` | enum | ✓ | `string` | Type |
| `defaultValue` | string |  | — | Cast to the chosen type at runtime. For dates use 'YYYY-MM-DD'; for booleans use 'true' / 'false'. |
| `position` | enum |  | `end` | Position |
| `reference` | column_ref |  | — | Only used when Position = before / after — ignored otherwise. |


### 📦 Bin numeric

**ID:** `bin_numeric` · **Version:** `1.0.0`

Bucket a numeric column into N equal-width bins, or into custom breakpoints.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `bucket` `discretize` `histogram`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `column` | column_ref | ✓ | — | Numeric column |
| `mode` | enum |  | `equal_width` | Mode |
| `bins` | integer |  | `5` | Number of bins |
| `breaks` | string |  | — | e.g. 0,100,500,1000 |
| `as` | string |  | `bin` | New column name |


### 🧭 Convert coordinates

**ID:** `convert_coordinates` · **Version:** `1.0.0`

Lossless conversion between polar, Cartesian, and geographic coordinate systems. Pure trig for polar↔Cartesian; WGS84 ellipsoid math for geographic↔Cartesian (ECEF).

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `spatial` `geometry` `coordinates` `convert` `polar` `cartesian` `geographic`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `fromType` | enum | ✓ | — | What system the source columns express. cartesian: (x, y[, z]); polar: (r, θ[, φ]) with θ/φ in radians; geographic: (lat, lon) in degrees. |
| `toType` | enum | ✓ | — | What system to produce. polar↔cartesian conversions are dimension-preserving (2D↔2D, 3D↔3D). geographic↔cartesian uses ECEF (Earth-Centered Earth-Fixed) on the WGS84 ellipsoid; output is 3D. |
| `sourceColumns` | array | ✓ | — | The columns carrying the source coordinates, in canonical order: cartesian: [x, y, z?]; polar: [r, theta, phi?]; geographic: [lat, lon]. |
| `outputPrefix` | string |  | `coord_` | Prepended to each generated output column name. Output names follow the canonical order of the target system: cartesian → x/y[/z]; polar → r/theta[/phi]; geographic → lat/lon. |


### ➕ Derive column

**ID:** `derive_column` · **Version:** `1.0.0`

Add a new column computed from a SQL expression over existing columns.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `derive` `compute`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | string | ✓ | — | New column name |
| `expression` | expression | ✓ | — | SQL expression, e.g. amount * 1.07 or upper(name) |


### 📅 Extract date parts

**ID:** `extract_date_parts` · **Version:** `1.0.0`

Pull year, month, day, day-of-week (etc.) out of a date or timestamp into new columns.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `date` `time` `extract`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `column` | column_ref | ✓ | — | Date column |
| `parts` | array |  | — | Parts to extract |
| `prefix` | string |  | `` | Output column prefix |


### 🎯 Extract pattern

**ID:** `extract_pattern` · **Version:** `1.0.0`

Extract a regex group from a string column into a new column. Group 0 = whole match.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `string` `regex` `extract`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `column` | column_ref | ✓ | — | Source column |
| `pattern` | regex | ✓ | — | e.g. ([A-Z]{2}) — group 1 captures two uppercase letters |
| `group` | integer |  | `1` | Capture group |
| `as` | string | ✓ | — | New column name |


### 🧮 Math equation

**ID:** `math_equation` · **Version:** `1.0.0`

Add a column computed from a math expression over existing columns. Supports arithmetic (+ - * / %), exponents (^ or pow()), and the usual math functions: sqrt, abs, log, ln, exp, sin, cos, tan, round, floor, ceil, mod, greatest, least. Reference columns by name, e.g. (price * quantity) - discount.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `math` `equation` `formula` `compute` `calculate` `arithmetic`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `resultName` | string | ✓ | — | Result column name |
| `equation` | expression | ✓ | — | Math expression — e.g. (price * quantity) - discount, sqrt(a^2 + b^2), round(amount * 1.07, 2) |
| `position` | enum |  | `end` | Position |
| `reference` | column_ref |  | — | Only used when Position = before / after — ignored otherwise. |


### 🌊 Rolling window

**ID:** `rolling` · **Version:** `1.0.0`

Add rolling-window aggregations (moving average, rolling sum, etc.) over a sorted time series. Common for smoothing noisy metrics or computing cumulative trends.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `time-series` `rolling` `moving-average` `smoothing`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `time_column` | column_ref |  | — | Sort by this before rolling. Optional — if blank, rolls over the existing row order. |
| `windows` | array | ✓ | — | List of {column, fn, window, as} where fn ∈ mean\|sum\|min\|max\|std\|count and window is e.g. 7 (rows) or '7d' (time-based, requires time_column). |
| `min_periods` | integer |  | `1` | Smallest number of observations needed to emit a value; below this, the rolling output is null. |

**Use case + example**

**When to use:** smooth a noisy time series, or look at a rolling sum / max / std deviation over a window.

**Example:** 7-day moving average of daily revenue.

```json
{
  "step": "rolling",
  "params": {
    "time_column": "date",
    "windows": [
      {"column": "revenue", "fn": "mean", "window": "7d", "as": "revenue_ma7"},
      {"column": "revenue", "fn": "max",  "window": "7d", "as": "revenue_max7"}
    ],
    "min_periods": 3
  }
}
```

**Two flavors of `window`:**

- **Time-based** (e.g. `"7d"`, `"24h"`) — uses the time column to define the window. Handles uneven spacing correctly.
- **Row-based** (an integer like `7`) — windows over the previous N rows regardless of time. Faster but assumes evenly-sampled data.

`min_periods` controls when the rolling output starts emitting a value — useful to avoid noisy values from the very first few observations.


### 📐 Z-score

**ID:** `zscore` · **Version:** `1.0.0`

Add a standardized (mean=0, std=1) version of a numeric column as a new column. Worked example from docs/AUTHORING_GUIDE.md.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `stats` `derive` `standardize`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `column` | column_ref | ✓ | — | Column |
| `output_column` | string |  | `z_score` | Output column name |


---

## 🤝 Combine

### 🔗 Join

**ID:** `join` · **Version:** `1.0.0`

Combine two datasets on matching key columns. Supports inner, left, right, full outer.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 2 · ➡️ outputs: 1 · rows: may_grow · schema: rebuilds

Tags: `join` `merge`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `how` | enum | ✓ | `inner` | Join type |
| `on` | array |  | — | Key pairs |


### 🧩 Sub-pipeline

**ID:** `subpipeline` · **Version:** `1.0.0`

Embed another saved pipeline as a single step. Output of the referenced pipeline becomes this step's output. Recursive references are detected and rejected.

🛠 engine: `polars` · ⬅️ inputs: 0–1 · ➡️ outputs: 1 · rows: unknown · schema: rebuilds

Tags: `composition` `subpipeline` `reuse`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `pipeline_id` | string | ✓ | — | ID of a saved pipeline. Open the target pipeline and copy its ID from the URL. |
| `output_id` | string |  | — | Which named output of the referenced pipeline to use. Defaults to the first / only output. |
| `sample_rows` | integer |  | — | Cap the rows pulled from the sub-pipeline. Useful when the inner pipeline is large and you only need a preview. |

**Use case + example**

**When to use:** factor a reusable transform out of one pipeline into its own pipeline, then call it from many. Encourages the same testability + ownership boundaries you'd get from a function in code.

**Example:** a "clean customer events" pipeline (filter test users, dedupe by event_id, attach country from IP) is referenced from a "weekly retention dashboard" pipeline and a "monthly cohort" pipeline.

```json
{
  "step": "subpipeline",
  "params": {
    "pipeline_id": "01J5VWPFKZTB6X2K3D8X4MN7CY",
    "output_id": "o_clean"
  }
}
```

To get the inner pipeline's id, open it in the editor — the URL is `/pipelines/<id>`.

**Cycle detection:** DIG tracks the call chain through `PolarsContext.pipeline_chain`. A pipeline that recursively references itself (directly or via a chain) raises immediately rather than spinning forever.

**Tip:** combine with the `expectations` step to enforce a contract on every consumer — the inner pipeline emits a known schema; the outer one fails-fast if that contract is violated.


### 🔀 Union

**ID:** `union` · **Version:** `1.0.0`

Stack two datasets vertically. Schemas should match by column name.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 2 · ➡️ outputs: 1 · rows: may_grow · schema: preserves

Tags: `union` `concat`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `distinct` | boolean |  | `False` | Drop duplicates (UNION vs UNION ALL) |


---

## 📊 Aggregate

### 📊 Group & aggregate

**ID:** `group_aggregate` · **Version:** `1.0.0`

Group rows by one or more columns and compute aggregate metrics.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

Tags: `aggregate` `group` `rollup`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `groupBy` | column_refs | ✓ | — | Group by |
| `aggregates` | array |  | — | Aggregates |


### ↕️ Pivot longer

**ID:** `pivot_longer` · **Version:** `1.0.0`

Stack multiple value columns into key/value rows. The inverse of pivot wider.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_grow · schema: rebuilds

Tags: `pivot` `unpivot` `long` `tidy`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `id` | column_refs | ✓ | — | Identifier columns (kept as-is) |
| `value_cols` | column_refs | ✓ | — | Columns to stack |
| `names_to` | string |  | `name` | Names column |
| `values_to` | string |  | `value` | Values column |


### ↔️ Pivot wider

**ID:** `pivot_wider` · **Version:** `1.0.0`

Spread distinct values of a column into separate columns. Aggregates a value column when collisions occur.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

Tags: `pivot` `spread` `wide`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `id` | column_refs | ✓ | — | Identifier columns (kept as-is) |
| `names` | column_ref | ✓ | — | Names from |
| `values` | column_ref | ✓ | — | Values from |
| `agg` | enum |  | `sum` | When collision |


### ⏱ Resample (time bucket aggregate)

**ID:** `resample` · **Version:** `1.0.0`

Bucket rows into fixed time intervals (e.g. 1d, 1h, 15m) and aggregate. Equivalent to a SQL date_trunc + group by, but with explicit interval semantics and gap-filling.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: unknown · schema: rebuilds

Tags: `time-series` `aggregate` `resample` `bucketize`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `time_column` | column_ref | ✓ | — | Time column |
| `interval` | string | ✓ | `1d` | Polars-style: 1d (daily), 1h (hourly), 15m, 1mo, 1y, 30s, etc. |
| `aggregations` | array | ✓ | — | List of {column, fn, as} where fn ∈ sum\|mean\|median\|min\|max\|count\|std\|first\|last. |
| `fill_gaps` | boolean |  | `True` | Insert empty rows for time intervals where no data exists (preferred for charting). |
| `fill_value` | string |  | `null` | Use 'null' or '0'. Numeric agg columns get this; non-numeric stay null. |

**Use case + example**

**When to use:** event-level data → bucketed time-series. "Show me total revenue per day" / "errors per minute" / "average latency per hour".

**Example:** events table → 5-minute buckets, count + average latency per bucket.

```json
{
  "step": "resample",
  "params": {
    "time_column": "occurred_at",
    "interval": "5m",
    "aggregations": [
      {"column": "*", "fn": "count", "as": "events"},
      {"column": "latency_ms", "fn": "mean", "as": "p_avg_ms"}
    ],
    "fill_gaps": true
  }
}
```

**Interval syntax:** Polars-style — `30s`, `5m`, `1h`, `1d`, `1mo`, `1y`.

**Why `fill_gaps`:** if a bucket has no events, the default emits no row for it. With gap-filling on, every interval between min/max gets a row; numeric agg columns get `null` (or `0` if `fill_value="0"`). Charts and forecasts assume contiguous time series, so gap-filling is usually what you want.


### 🪟 Window aggregate

**ID:** `window_aggregate` · **Version:** `1.0.0`

Add a column computed over a rolling/cumulative window — running sum, rank, lead/lag, etc.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `window` `rolling` `rank`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `fn` | enum | ✓ | `sum` | Window function |
| `column` | column_ref |  | — | Source column |
| `partitionBy` | column_refs |  | — | Partition by (groups) |
| `orderBy` | array |  | — | Order by |
| `as` | string | ✓ | — | New column name |


---

## 📤 Output

### 🗃 Export to database

**ID:** `export_to_db` · **Version:** `1.0.0`

Write the data to a SQL database table. Supports SQLite, Postgres, MySQL via standard URIs.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

Tags: `export` `sink` `database` `sql`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `uri` | string | ✓ | — | e.g. sqlite:///path/to.db · postgresql://user:pass@host/db · mysql://user:pass@host/db |
| `table` | string | ✓ | — | Table name |
| `if_exists` | enum | ✓ | `append` | If the table exists |

**Use case + example**

**When to use:** drop the final dataframe into a SQL table — your warehouse, a local SQLite, or a shared Postgres.

**Example — SQLite:**

```json
{
  "step": "export_to_db",
  "params": {
    "uri": "sqlite:///data/local.db",
    "table": "customers_clean",
    "if_exists": "replace"
  }
}
```

**Example — Postgres (production):**

```json
{
  "step": "export_to_db",
  "params": {
    "uri": "postgresql://etl_user:***@warehouse:5432/analytics",
    "table": "fact_daily_revenue",
    "if_exists": "append"
  }
}
```

**`if_exists` semantics:**

- `append` — add rows; fails if schemas don't match.
- `replace` — drop and re-create the table.
- `fail` — error if the table already exists. Safest for one-shot loads.

**Driver requirement:** DIG ships only the Polars + pyarrow base. For Postgres / MySQL install `adbc-driver-postgresql` or `adbc-driver-mysql` (or fall back to `sqlalchemy + psycopg2`). The error message tells you which one you're missing.

**Security:** the URI's password is **redacted** in the artifact card before it lands in your run history (`...://user:***@host`), so you can share screenshots without leaking credentials.


### 💾 Export to file

**ID:** `export_to_file` · **Version:** `1.0.0`

Write the data to disk in CSV, Parquet, Excel, JSON, or NDJSON. The file lands at data/outputs/<run>/<name> by default.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

Tags: `export` `sink` `file`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `format` | enum | ✓ | `parquet` | Format |
| `path` | string |  | — | Absolute path, or just a filename (writes under data/outputs/<run>/). Leave blank to auto-name. |
| `compression` | enum |  | `zstd` | Compression |

**Use case + example**

**When to use:** persist the result of your pipeline as a file on disk — CSV for humans, Parquet for downstream tools, Excel for stakeholders, NDJSON for streaming consumers.

**Example — CSV:**

```json
{
  "step": "export_to_file",
  "params": {
    "format": "csv",
    "path": "active-customers.csv"
  }
}
```

**Example — Parquet:**

```json
{
  "step": "export_to_file",
  "params": {
    "format": "parquet",
    "path": "daily-revenue.parquet"
  }
}
```

**Format trade-offs:**

| Format | Pros | Cons | Pick when |
|---|---|---|---|
| `csv` | universal, human-readable, opens in any tool | no types, big files, no nesting | sharing with humans / spreadsheets |
| `parquet` | columnar, typed, compressed (zstd default), fast | needs a parquet reader | feeding another data tool |
| `excel` | non-technical stakeholders | row limit (~1M), slow on large data | exec / finance handoffs |
| `json` | preserves nested structure | bulky | API mocks, document stores |
| `ndjson` | line-streamable, append-friendly | bulky | logs, queue feeds, kafka producers |

**Tip:** the path is resolved relative to the run output dir (`data/outputs/<run_id>/`). Use absolute paths only when you intentionally want to write outside that — e.g. into a share you've mounted.


### 🖼 Export to image

**ID:** `export_to_image` · **Version:** `1.0.0`

Render the data as a PNG/SVG via matplotlib + seaborn. Pick 1 column (distribution), 2 columns (scatter / categorical), or 3 columns (heatmap or 3-D scatter). 'auto' picks a sensible chart from the column types.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

Tags: `export` `image` `plot` `viz` `matplotlib` `seaborn`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `kind` | enum | ✓ | `auto` | 'auto' inspects the columns + types and picks one. Override for explicit control. |
| `x` | column_ref |  | — | First axis. Required for 2D/3D charts; optional for distribution charts (then samples the chosen value column). |
| `y` | column_ref |  | — | Second axis. Required for scatter / line / heatmap / scatter3d. |
| `y2` | column_ref |  | — | Y column |
| `y3` | column_ref |  | — | Y column |
| `y4` | column_ref |  | — | Y column |
| `y5` | column_ref |  | — | Y column |
| `value` | column_ref |  | — | Third channel — colors a heatmap cell or sizes a scatter marker. |
| `z` | column_ref |  | — | Z column (3-D scatter) |
| `title` | string |  | — | Title |
| `format` | enum | ✓ | `png` | Format |
| `width` | integer |  | `900` | Width (px) |
| `height` | integer |  | `600` | Height (px) |
| `dpi` | integer |  | `144` | DPI |
| `max_points` | integer |  | `50000` | If the input has more rows than this, the step samples down. Plots aren't useful past a few hundred thousand points. |
| `path` | string |  | — | Defaults to data/outputs/<run>/<step>.png |

**Use case + example**

**When to use:** end of a pipeline, when you want a chart you can paste into a slide / share / embed in a report.

DIG renders via matplotlib + seaborn — not a web charting library — so the output is publication-grade PNG (or SVG). No JS bundle weight, deterministic, headless-friendly.

**Auto-pick logic:** with `kind = "auto"` the step inspects the columns you fill in plus their types and picks a sensible chart:

| You fill | Types | Auto-picked chart |
|---|---|---|
| 1 axis | numeric | histogram (with KDE) |
| 1 axis | categorical | top-N horizontal bar |
| 2 axes | num × num | scatter |
| 2 axes | cat × num | bar (mean per category) |
| 3 axes | x × y × value | heatmap (pivot) |
| 3 axes | all numeric | 3-D scatter |

**Example — bar chart:**

```json
{
  "step": "export_to_image",
  "params": {
    "kind": "bar_counts",
    "x": "region",
    "title": "💰 Revenue by region"
  }
}
```

![bar chart by region](images/tutorials/tutorial-bar-by-region.png)

**Example — heatmap (region × product):**

```json
{
  "step": "export_to_image",
  "params": {
    "kind": "heatmap",
    "x": "region",
    "y4": "product",
    "value": "revenue",
    "title": "🔥 Revenue heatmap"
  }
}
```

![heatmap region × product](images/tutorials/tutorial-heatmap-sales.png)

**Tip:** the file is written under `data/outputs/<run_id>/<step>.png` by default. Set `path` to override (relative paths are resolved against the run dir; absolute paths land where you put them).


### 🔌 Export to JDBC

**ID:** `export_to_jdbc` · **Version:** `1.0.0`

Write rows to any JDBC-accessible database — Oracle, DB2, MS SQL Server, Snowflake, Teradata, Vertica, etc. Requires a Java runtime on the host and a path to the driver JAR. Use the standard 'Export to database' step for Postgres / MySQL / SQLite via native Python drivers.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

Tags: `export` `sink` `database` `jdbc` `java`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `url` | string | ✓ | — | Full JDBC URL — e.g. jdbc:oracle:thin:@//host:1521/ORCL · jdbc:sqlserver://host:1433;database=mydb |
| `driverClass` | string | ✓ | — | Fully-qualified Java class — oracle.jdbc.OracleDriver · com.microsoft.sqlserver.jdbc.SQLServerDriver · etc. |
| `jarPath` | string | ✓ | — | Absolute path to the .jar file (or a directory of jars). |
| `username` | string |  | — | Username |
| `password` | string |  | — | Supports ${ENV_VAR} interpolation. |
| `table` | string | ✓ | — | Schema-qualify if needed (e.g. analytics.orders). |
| `mode` | enum | ✓ | `append` | append = INSERT only · truncate_then_append = TRUNCATE then INSERT · drop_and_create = DROP then CREATE TABLE then INSERT |
| `batchSize` | integer |  | `1000` | Rows per JDBC executemany() call. Higher = faster but more memory. |


### 🔔 Trigger webhook

**ID:** `webhook_trigger` · **Version:** `1.0.0`

Fire a webhook from inside this pipeline. Pick a global webhook by label (defined in Settings → Global webhooks). Webhooks with on='triggered' only fire from this step — never auto-fire on run completion. Data passes through unchanged. If you haven't created any webhooks yet, save the step empty and pick one later.

🛠 engine: `polars` · ⚠️ non-deterministic · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

Tags: `webhook` `trigger` `notify` `side-effect` `integration`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `webhookLabel` | string |  | — | Label of the global webhook to fire. Manage webhooks in Settings → 🔔 Global webhooks. Leave blank to make this a placeholder step you'll wire up later. |
| `extraPayload` | string |  | — | Merged into the default payload — useful for tagging the call with stage info, e.g. {"stage": "after-cleansing"}. |
| `failOnError` | boolean |  | `False` | Off (default): a 5xx or timeout from the receiver is logged but the pipeline continues. On: a webhook failure aborts the pipeline at this step. |
