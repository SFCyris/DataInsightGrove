# 📚 DataInsightGrove — Step library

This page documents every step DIG ships with. It is **auto-generated** from each step's `manifest.json` plus optional hand-written notes under `docs/_steps/<step_id>.md` — re-run `python scripts/gen-steps-doc.py` whenever you add or change a step.

**93 steps** across ✂️ Shape (13), 🧼 Clean (9), 🪄 Derive (23), 🤝 Combine (3), 📊 Aggregate (5), 🔬 Analyze (14), 🧠 Model (8), ✅ Validate (1), 📈 Visualize (12), 📤 Output (4), 🧩 Custom (1).

## Index

### ✂️ Shape

- [🔍 Filter rows](#filter-rows) — Keep rows where the predicate evaluates to true.
- [📤 Flatten array](#flatten-array) — Reshape an array column.
- [🔄 Matrix inverse](#matrix-inverse) — Invert a square matrix.
- [🔁 Matrix transpose](#matrix-transpose) — Transpose a matrix.
- [📦 Pack into struct](#pack-into-struct) — Combine multiple columns into a single struct column.
- [✏️ Rename columns](#rename-columns) — Rename one or more columns.
- [↔️ Reorder columns](#reorder-columns) — Reorder the columns of the input.
- [🎲 Sample rows](#sample-rows) — Take a random or head/tail sample of rows.
- [📋 Select columns](#select-columns) — Keep only the chosen columns, in the chosen order.
- [↕️ Sort rows](#sort-rows) — Order rows by one or more columns.
- [✂️ Split column](#split-column) — Split a string column on a delimiter into N new columns (named col_1, col_2, …).
- [💥 Unnest array](#unnest-array) — Explode an array column into rows — one row per element.
- [📤 Unpack struct](#unpack-struct) — Explode a struct column into one column per field.

### 🧼 Clean

- [🔄 Cast type](#cast-type) — Change the data type of a column.
- [🧪 Data quality check](#data-quality-check) — Assert a column-level rule on the data — fails or warns if violated.
- [🧽 Clean whitespace](#clean-whitespace) — Trim leading/trailing whitespace and optionally collapse runs of internal whitespace into a single space.
- [🪢 Coalesce columns](#coalesce-columns) — First non-null wins.
- [🪞 Deduplicate](#deduplicate) — Keep one row per group of duplicates.
- [⏳ Replace outliers](#replace-outliers) — Replace values flagged in an `is_anomaly` (or boolean) column with a rolling-median estimate.
- [🔤 Replace text](#replace-text) — Find-and-replace inside a string column.
- [🎯 Round numeric](#round-numeric) — Round a numeric column to N decimal places.
- [🆙 Uppercase string](#uppercase-string) — Convert a string column to uppercase.

### 🪄 Derive

- [🆕 Add column](#add-column) — Add a new column with a typed default value.
- [⏱ Add runtime column](#add-runtime-column) — Add a new column whose value is rendered once per run from a `{{ template }}`.
- [📏 Array length](#array-length) — Add a column with the length of an array column.
- [📦 Bin numeric](#bin-numeric) — Bucket a numeric column into N equal-width bins, or into custom breakpoints.
- [📅 Business days between](#business-days-between) — Count business days (Mon-Fri excluding holidays) between two date columns per row.
- [🧭 Convert coordinates](#convert-coordinates) — Lossless conversion between polar, Cartesian, and geographic coordinate systems.
- [🔄 Convert units](#convert-units) — Convert a numeric column between units.
- [📅 Date snap](#date-snap) — Snap a date to the start (or end) of a calendar period: week, month, quarter, year.
- [➕ Derive column](#derive-column) — Add a new column computed from a SQL expression over existing columns.
- [📏 Distance matrix](#distance-matrix) — Compute pairwise distances between every pair of rows from a vector column.
- [🧠 Embed text (AI)](#embed-text-ai) — Add a vector column with embeddings of a text column.
- [📅 Extract date parts](#extract-date-parts) — Pull year, month, day, day-of-week (etc.
- [🎯 Extract pattern](#extract-pattern) — Extract a regex group from a string column into a new column.
- [📅 Fiscal year parts](#fiscal-year-parts) — Decompose a date into fiscal-year, fiscal-quarter, and fiscal-month for any fiscal-year start month.
- [🌍 Geographic distance](#geographic-distance) — Compute great-circle distance (Haversine, in metres) between two lat/lon points.
- [📦 Extract from JSON](#extract-from-json) — Pull a value out of a JSON column at the given path.
- [📊 Logistic regression](#logistic-regression) — Binary classification via logistic regression.
- [🧮 Math equation](#math-equation) — Add a column computed from a math expression over existing columns.
- [🌊 Rolling window](#rolling-window) — Add rolling-window aggregations (moving average, rolling sum, etc.
- [🧭 Top-K nearest](#top-k-nearest) — Per-row top-K nearest-neighbour search over a vector column.
- [➕ Vector arithmetic](#vector-arithmetic) — Element-wise arithmetic on vector (array of numeric) columns.
- [🧭 Vector similarity](#vector-similarity) — Compute similarity / distance between two vector columns.
- [📐 Z-score](#z-score) — Add a standardized (mean=0, std=1) version of a numeric column as a new column.

### 🤝 Combine

- [🔗 Join](#join) — Combine rows from two inputs by matching values in key columns.
- [🧩 Sub-pipeline](#sub-pipeline) — Embed another saved pipeline as a single step.
- [🔀 Union](#union) — Stack two datasets vertically.

### 📊 Aggregate

- [📊 Group & aggregate](#group--aggregate) — Group rows by one or more columns and compute aggregate metrics.
- [↕️ Pivot longer](#pivot-longer) — Stack multiple value columns into key/value rows.
- [↔️ Pivot wider](#pivot-wider) — Spread distinct values of a column into separate columns.
- [⏱ Resample (time bucket aggregate)](#resample-time-bucket-aggregate) — Bucket rows into fixed time intervals (e.
- [🪟 Window aggregate](#window-aggregate) — Add a column computed over a rolling/cumulative window — running sum, rank, lead/lag, etc.

### 🔬 Analyze

- [⏳ ACF + PACF](#acf--pacf) — Compute autocorrelation (ACF) and partial autocorrelation (PACF) at lags 1.
- [⏳ Augmented Dickey-Fuller](#augmented-dickey-fuller) — Unit-root test.
- [⏳ Anomaly · rolling z-score](#anomaly--rolling-z-score) — Flag time-series points whose distance from a rolling mean exceeds N standard deviations.
- [📐 One-way ANOVA](#one-way-anova) — One-way ANOVA: does the mean of `value` differ across the levels of `group`? Returns F-statistic, p-value, between/within group sums-of-squares, η² (eta-squared) effect size.
- [📐 Bootstrap CI](#bootstrap-ci) — Distribution-free confidence interval around a statistic by resampling with replacement.
- [⏳ Changepoint detection](#changepoint-detection) — Find rows where the time series shifts in mean.
- [📐 Chi-squared test](#chi-squared-test) — Chi-squared test of independence between two categorical columns.
- [📊 Correlation matrix](#correlation-matrix) — Pairwise correlation between numeric columns.
- [📐 Effect size](#effect-size) — Effect-size measures for two-group comparisons.
- [⏳ KPSS test](#kpss-test) — Companion to ADF — tests the OPPOSITE null hypothesis.
- [📐 Two-sample KS test](#two-sample-ks-test) — Two-sample Kolmogorov-Smirnov test — do two groups have the same distribution at all? Distribution-free; works even when neither group is normal.
- [📐 Mann-Whitney U test](#mann-whitney-u-test) — Non-parametric two-sample test — works without assuming normality.
- [📐 Multiple-comparison correction](#multiple-comparison-correction) — Adjust p-values for multiple-test inflation.
- [📐 Two-sample t-test](#two-sample-t-test) — Welch's two-sample independent t-test.

### 🧠 Model

- [🌌 DBSCAN clustering](#dbscan-clustering) — Density-based clustering — finds clusters of arbitrary shape and labels low-density points as noise (cluster id = -1).
- [🔮 Forecast (time-series)](#forecast-time-series) — Project a time series N steps into the future.
- [🔮 K-Means clustering](#k-means-clustering) — Partitions rows into K clusters by minimizing within-cluster variance.
- [📐 Linear regression](#linear-regression) — Ordinary least squares — fit y = β·X + ε.
- [🧬 PCA (dimensionality reduction)](#pca-dimensionality-reduction) — Principal Component Analysis — reduces N numeric columns to K orthogonal components ordered by variance explained.
- [🔂 Seasonal decomposition](#seasonal-decomposition) — Decompose a time series into trend, seasonal, and residual components (additive or multiplicative).
- [🌠 t-SNE (2-D embedding)](#t-sne-2-d-embedding) — t-distributed Stochastic Neighbor Embedding — non-linear dimensionality reduction great for visualizing high-dimensional clusters.
- [🌌 UMAP (2-D embedding)](#umap-2-d-embedding) — Uniform Manifold Approximation and Projection — modern non-linear dim reduction that preserves both local + global structure better than t-SNE and scales to 100k+ rows.

### ✅ Validate

- [✅ Data quality expectations](#data-quality-expectations) — Assert data quality rules (unique, not_null, between, in, regex_match, row_count_between, null_fraction, cardinality_between).

### 📈 Visualize

- [🎯 Bullet chart](#bullet-chart) — Edward Tufte's compact target-vs-actual chart.
- [🕯 Candlestick / OHLC chart](#candlestick--ohlc-chart) — Financial candlestick chart from Open / High / Low / Close columns.
- [🖼 Export to image](#export-to-image) — Render the data as a PNG/SVG via matplotlib + seaborn.
- [🗺 Export to map](#export-to-map) — Render geographic data on an interactive world map.
- [📈 Funnel chart](#funnel-chart) — Sequential conversion-funnel visualisation.
- [🌡 Gauge chart](#gauge-chart) — Speedometer-style single-metric gauge.
- [🪞 Horizon chart](#horizon-chart) — Compact small-multiples view for many time series.
- [🟦 Marimekko / mosaic](#marimekko--mosaic) — Two-dimensional part-to-whole.
- [📈 Pareto chart](#pareto-chart) — Sorted bar chart of category values + cumulative-percentage line on a secondary axis.
- [🥧 Pie / donut chart](#pie--donut-chart) — Classic part-to-whole pie or donut.
- [🌊 Stream graph](#stream-graph) — Stacked area chart with center-baselined symmetry (the classic 'wiggle' algorithm).
- [📈 Waterfall chart](#waterfall-chart) — Cumulative-contribution chart.

### 📤 Output

- [🗃 Export to database](#export-to-database) — Write the data to a SQL database table.
- [💾 Export to file](#export-to-file) — Write the data to disk in CSV, Parquet, Excel, JSON, or NDJSON.
- [🔌 Export to JDBC](#export-to-jdbc) — Write rows to any JDBC-accessible database — Oracle, DB2, MS SQL Server, Snowflake, Teradata, Vertica, etc.
- [🔔 Trigger webhook](#trigger-webhook) — Fire a webhook from inside this pipeline.

### 🧩 Custom

- [🪆 Passthrough](#passthrough) — Identity step — emits its input unchanged.

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


### 📤 Flatten array

**ID:** `flatten_array` · **Version:** `1.0.0`

Reshape an array column. Three modes: flatten one level of nesting (list-of-list → list); fully flatten (any depth → list of leaves); unnest to rows (one row per element). Use unnest_to_rows when downstream steps expect scalar values; use flatten_one_level / fully_flatten when you need to keep one row per parent entity.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_grow · schema: modifies

Tags: `array` `list` `flatten` `unnest` `reshape` `explode`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `arrayColumn` | column_ref | ✓ | — | Array column |
| `mode` | enum | ✓ | `flatten_one_level` | flatten_one_level: [[1,2],[3]] → [1,2,3]. fully_flatten: any nesting depth → flat list. unnest_to_rows: each element becomes its own row, other columns repeat. |
| `outputColumn` | string |  | — | Defaults to overwriting the source column. For unnest_to_rows, this is the new scalar column name. |
| `keepEmpty` | boolean |  | `False` | When unnesting, default behaviour drops rows whose array is empty or NULL. Set true to keep them with NULL in the output column. |


### 🔄 Matrix inverse

**ID:** `matrix_inverse` · **Version:** `1.0.0`

Invert a square matrix. Supports two input shapes: a column-grid (M rows × M columns of numbers) and a nested-list column (each row carries a full square matrix). Singular matrices raise a clear error; the pseudoinverse option falls back to numpy.linalg.pinv for non-invertible inputs.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `matrix` `inverse` `linalg` `pinv`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `mode` | enum | ✓ | `column_grid` | column_grid: pick M numeric columns from M input rows. nested_list: each row carries a full square matrix in a single nested-list column. |
| `valueColumns` | column_refs |  | — | The M columns × M rows matrix to invert. Required for mode = column_grid. |
| `nestedListColumn` | column_ref |  | — | A list-of-list-of-number column. Each cell must be a square matrix. Required for mode = nested_list. |
| `outputColumn` | string |  | `inverse` | Output column name (nested_list mode) |
| `pseudoinverse` | boolean |  | `False` | When the matrix is singular (non-invertible), fall back to numpy.linalg.pinv (Moore-Penrose pseudoinverse) instead of erroring. Useful when working with rank-deficient inputs. |


### 🔁 Matrix transpose

**ID:** `matrix_transpose` · **Version:** `1.0.0`

Transpose a matrix. Two input shapes are supported: a column-grid (pick N numeric columns; each row becomes a column in the output) and a nested-list column (each row already carries a [[…],[…]] matrix; transpose preserves the row count).

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: unknown · schema: rebuilds

Tags: `matrix` `transpose` `linalg` `shape` `rotate`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `mode` | enum | ✓ | `column_grid` | column_grid: pick N columns. The M rows × N columns form an M×N matrix; output is N rows × M columns. nested_list: each row is already a full matrix in a single nested-list column; transpose row by row. |
| `valueColumns` | column_refs |  | — | The columns forming the matrix rows. Required for mode = column_grid. Must all be numeric. |
| `nestedListColumn` | column_ref |  | — | A list-of-list-of-number column. Each cell is one matrix; the result column carries each cell's transpose. Required for mode = nested_list. |
| `outputColumn` | string |  | `transposed` | Output column name (nested_list mode) |


### 📦 Pack into struct

**ID:** `pack_struct` · **Version:** `1.0.0`

Combine multiple columns into a single struct column. Use to build cartesian / polar / geographic columns from the raw (x, y) / (lat, lon) inputs they're stored in.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `struct` `pack` `spatial` `compose`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `outputColumn` | string | ✓ | — | Name of the new struct column. The original component columns are preserved unless you also use Drop column afterwards. |
| `fields` | array | ✓ | — | Source columns in order. For cartesian2d use [x, y]; for cartesian3d [x, y, z]; for polar2d [r, theta]; for polar3d [r, theta, phi]; for geographic [lat, lon]. |


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


### 💥 Unnest array

**ID:** `unnest_array` · **Version:** `1.0.0`

Explode an array column into rows — one row per element. The other columns are duplicated for each exploded row.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_grow · schema: modifies

Tags: `array` `unnest` `explode` `shape`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `column` | column_ref | ✓ | — | Array column |
| `outputColumn` | string |  | — | Defaults to the original column name if blank. |
| `preserveNulls` | boolean |  | `True` | On (default): rows with NULL / empty arrays produce a single row with NULL in the output column. Off: those rows are dropped entirely. |


### 📤 Unpack struct

**ID:** `unpack_struct` · **Version:** `1.0.0`

Explode a struct column into one column per field. Inverse of pack_struct.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `struct` `unpack` `explode` `spatial` `decompose`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `column` | column_ref | ✓ | — | Struct column |
| `fields` | array | ✓ | — | Names of the struct fields to pull out as separate columns. The original struct column is dropped from the output. |
| `outputPrefix` | string |  | `` | Optional. Prepended to each generated column name to avoid collisions with existing columns. |


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


### 🧪 Data quality check

**ID:** `check_data` · **Version:** `1.0.0`

Assert a column-level rule on the data — fails or warns if violated. Mirrors dbt's tests and Great Expectations' assertions in spirit; gives DIG users a way to declare expectations inline as a pipeline step.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

Tags: `check` `test` `assertion` `quality` `validate`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `column` | column_ref | ✓ | — | The column the rule is evaluated against. For checks that don't need a single column (e.g. row count thresholds), point at any column — the rule simply ignores it. |
| `check` | enum | ✓ | `not_null` | not_null  → no NULLs · unique → no duplicates · between → numeric range · in_set → value must be one of N · regex → must match a pattern · expression → custom SQL predicate (rule passes when expression is TRUE) |
| `min` | number |  | — | Inclusive lower bound for `between` checks. Leave blank to skip the lower bound. |
| `max` | number |  | — | Inclusive upper bound for `between` checks. Leave blank to skip the upper bound. |
| `set` | string |  | — | Comma-separated list of values, e.g. `paid, pending, cancelled`. Each value is compared as text — surround with quotes if it contains a comma. |
| `pattern` | string |  | — | DuckDB regex pattern (POSIX-style). The rule passes if every non-NULL value matches. |
| `expression` | string |  | — | Free-form SQL predicate. The rule passes when the expression returns TRUE for every row. Reference the column with its quoted name. Same security validator as filter_rows / derive_column. |
| `severity` | enum |  | `warn` | warn → emit a `data.quality.violation` event (notifications panel); pipeline keeps running.

error → emit + the run is marked failed if any violations are found. |
| `name` | string |  | — | Optional. Shows up in the notification + run history. e.g. `revenue_must_be_positive`. |


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


### ⏳ Replace outliers

**ID:** `replace_outliers` · **Version:** `1.0.0`

Replace values flagged in an `is_anomaly` (or boolean) column with a rolling-median estimate. Use this AFTER `anomaly_zscore` to clean a series before forecasting — otherwise outliers leak into the seasonal/trend decomposition and skew the forecast intervals.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:time_series_pro`

Tags: `time-series` `outlier` `clean`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `value` | column_ref | ✓ | — | Value column to clean |
| `flag` | column_ref | ✓ | — | Typically the `is_anomaly` column from the anomaly_zscore step. |
| `window` | integer |  | `7` | Number of nearby rows used to compute the replacement median. Smaller = more local; larger = smoother. |
| `output_column` | string |  | `value_clean` | Name for the cleaned column. Original value column is preserved. |


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


### ⏱ Add runtime column

**ID:** `add_runtime_column` · **Version:** `1.0.0`

Add a new column whose value is rendered once per run from a `{{ template }}`. Use for timestamps, run identifiers, derived report labels, etc. The template is evaluated against the run's variable namespace (today, now, run_id, pipeline_name, vars.*, …). See docs/VARIABLES.md for the full namespace and filter list.

🛠 engine: `polars` · ⚠️ non-deterministic · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `template` `timestamp` `runtime` `derive`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | string | ✓ | — | New column name |
| `template` | string | ✓ | — | Examples: `{{ today }}`, `Report run at {{ utime }} UTC`, `{{ today \| strftime('%Y/%m/%d') }}`, `{{ vars.region }}`. |
| `columnType` | enum | ✓ | `string` | Type |
| `position` | enum |  | `end` | Position |


### 📏 Array length

**ID:** `array_length` · **Version:** `1.0.0`

Add a column with the length of an array column. Returns 0 for empty arrays and NULL for NULL arrays.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `array` `length` `count` `derive`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `column` | column_ref | ✓ | — | Array column |
| `outputColumn` | string | ✓ | `length` | Output column name |


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


### 📅 Business days between

**ID:** `business_days_between` · **Version:** `1.0.0`

Count business days (Mon-Fri excluding holidays) between two date columns per row. Honours country-specific holiday calendars via the `holidays` library. Adds `bdays` column with the integer count.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:dates_pack`

Tags: `dates` `business`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `start_column` | column_ref | ✓ | — | Start date column |
| `end_column` | column_ref | ✓ | — | End date column |
| `country` | string |  | `US` | US, GB, DE, FR, JP, etc. See https://python-holidays.readthedocs.io/. |
| `output_column` | string |  | `bdays` | Output column name |


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


### 🔄 Convert units

**ID:** `convert_units` · **Version:** `1.0.0`

Convert a numeric column between units. Supports temperature, length, mass, volume, time, pressure, energy, power, force, speed, angle, frequency, data sizes, and chemistry (mol / molarity). Both source and target unit must be in the same category — see the unit dropdown for the full list.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `convert` `units` `temperature` `length` `mass` `physics` `chemistry`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `column` | column_ref | ✓ | — | Numeric column holding values in the FROM unit. |
| `from_unit` | enum | ✓ | — | Unit the source column is currently in. |
| `to_unit` | enum | ✓ | — | Target unit. Must be in the same category as the FROM unit. |
| `output_column` | string |  | — | Name for the converted column. Leave empty to overwrite the source column. |


### 📅 Date snap

**ID:** `date_snap` · **Version:** `1.0.0`

Snap a date to the start (or end) of a calendar period: week, month, quarter, year. Useful for grouping daily data into weeks-starting-Monday, months-starting-1st, etc. Output is added as a new column or replaces the original.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:dates_pack`

Tags: `dates`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `date_column` | column_ref | ✓ | — | Date column |
| `period` | enum |  | `week` | Period |
| `boundary` | enum |  | `start` | Snap to |
| `output_column` | string |  | `snapped_date` | Output column name |


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


### 📏 Distance matrix

**ID:** `distance_matrix` · **Version:** `1.0.0`

Compute pairwise distances between every pair of rows from a vector column. Output is either a long-form (i, j, distance) table or a square N×N table. Use as input to hierarchical clustering, multidimensional scaling, k-medoids, or just to explore which rows are closest to which.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_grow · schema: rebuilds

Tags: `distance` `matrix` `pairwise` `linalg` `clustering` `mds` `knn`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `vectorColumn` | column_ref | ✓ | — | Vector column |
| `metric` | enum | ✓ | `euclidean` | euclidean: L2 (straight-line) distance. cosine: 1 - cosine similarity (range 0-2). manhattan: L1 (city-block). chebyshev: max element-wise distance. |
| `outputFormat` | enum | ✓ | `long` | long: one row per (i, j) pair with columns row_i, row_j, distance. square: an N×N table where the value at (i, j) is the distance from row i to row j. |
| `labelColumn` | column_ref |  | — | Use this column's values instead of row indices to identify rows in the output. Defaults to integer row index. |
| `maxRows` | integer |  | `1000` | N rows produces an N² result. The cap prevents accidentally materialising a 10,000² = 100M-row distance matrix. Raise consciously if you really want that. |


### 🧠 Embed text (AI)

**ID:** `embed_text` · **Version:** `1.0.0`

Add a vector column with embeddings of a text column. Calls an OpenAI-compatible /v1/embeddings endpoint (works with OpenAI, Cohere via compat layer, Ollama, Together, vLLM, llama.cpp). Costs API credits for paid providers; free with a local Ollama embedding model.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `embedding` `vector` `ml` `openai` `ollama` `ai`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `textColumn` | column_ref | ✓ | — | Text column |
| `outputColumn` | string | ✓ | `embedding` | Output vector column name |
| `endpoint` | string | ✓ | `https://api.openai.com/v1/embeddings` | OpenAI: https://api.openai.com/v1/embeddings · Ollama: http://localhost:11434/v1/embeddings · Together / Groq / OpenRouter: see their docs. |
| `model` | string | ✓ | `text-embedding-3-small` | OpenAI: text-embedding-3-small (1536d, cheap) or text-embedding-3-large (3072d). Ollama: nomic-embed-text (768d), mxbai-embed-large (1024d). Cohere: embed-english-v3.0. |
| `apiKey` | string |  | `` | Bearer token. Local Ollama doesn't need one. The key is sent ONLY to the configured endpoint. |
| `batchSize` | integer |  | `100` | Texts per API call. Lower = more requests + slower; higher = fewer requests but risks 'request too large' errors. OpenAI accepts up to 2048. |


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


### 📅 Fiscal year parts

**ID:** `fiscal_year_parts` · **Version:** `1.0.0`

Decompose a date into fiscal-year, fiscal-quarter, and fiscal-month for any fiscal-year start month. Common values: 1 (calendar year), 4 (UK government), 7 (Australia), 10 (US federal). Output columns: fy_year, fy_quarter (1-4), fy_month (1-12).

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:dates_pack`

Tags: `dates`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `date_column` | column_ref | ✓ | — | Date column |
| `fy_start_month` | integer |  | `1` | 1 = calendar; 4 = UK gov; 7 = Australia; 10 = US federal. |
| `prefix` | string |  | `fy_` | Output column prefix |


### 🌍 Geographic distance

**ID:** `geo_distance` · **Version:** `1.0.0`

Compute great-circle distance (Haversine, in metres) between two lat/lon points. Add as a new column.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `spatial` `geographic` `distance` `haversine` `derive`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `lat1Column` | column_ref | ✓ | — | First point — latitude (degrees) |
| `lon1Column` | column_ref | ✓ | — | First point — longitude (degrees) |
| `lat2Column` | column_ref | ✓ | — | Second point — latitude (degrees) |
| `lon2Column` | column_ref | ✓ | — | Second point — longitude (degrees) |
| `outputColumn` | string | ✓ | `distance_m` | Name of the new column. Values are in metres on a sphere of radius 6,371,000 m (mean Earth radius). |


### 📦 Extract from JSON

**ID:** `json_extract` · **Version:** `1.0.0`

Pull a value out of a JSON column at the given path. e.g. '$.user.email' from {"user": {"email": "alice@example.com"}}.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `json` `extract` `path` `derive`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `column` | column_ref | ✓ | — | JSON column |
| `path` | string | ✓ | `$.` | JSONPath syntax. Examples: $.field, $.user.email, $.items[0].name. Use $ to refer to the root. |
| `outputColumn` | string | ✓ | — | Output column name |
| `asText` | boolean |  | `False` | Off (default): preserves the JSON type — numbers become numbers, booleans become booleans. On: always returns the value as a string (useful when the field's type is inconsistent across rows). |


### 📊 Logistic regression

**ID:** `logistic_regression` · **Version:** `1.0.0`

Binary classification via logistic regression. Fits a model to predict a 0/1 (or true/false) target from numeric features, adds predicted_class + predicted_proba columns, and emits per-feature coefficients + intercept + accuracy as a side-effect artifact.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:stats_pro`

Tags: `statistics` `ml` `classification` `logistic` `regression`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `targetColumn` | column_ref | ✓ | — | The 0/1 (or true/false) outcome column to predict. |
| `featureColumns` | column_refs | ✓ | — | Numeric columns to use as predictors. Encode categoricals via the one-hot or cast_type steps first. |
| `regularization` | enum | ✓ | `l2` | l2: ridge (default, shrinks coefficients). l1: lasso (drops weak features to zero). none: pure unregularised fit; can overfit on small / collinear data. |
| `c` | number |  | `1.0` | Inverse of regularization weight — smaller C = stronger regularization. Ignored when regularization = none. |
| `predictedClassColumn` | string |  | `predicted_class` | Predicted class column |
| `predictedProbaColumn` | string |  | `predicted_proba` | Predicted probability column |


### 🧮 Math equation

**ID:** `math_equation` · **Version:** `1.1.0`

Add a column computed from a math expression over existing columns. Supports arithmetic (+ - * / %), exponents (^ or pow()), and the standard math functions: sqrt, abs, log, ln, exp, sin, cos, tan, asin, acos, atan, atan2(y, x), sinh, cosh, tanh, asinh, acosh, atanh, round, floor, ceil, mod, greatest, least. Reference columns by name, e.g. (price * quantity) - discount, atan2(dy, dx) for bearing.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `math` `equation` `formula` `compute` `calculate` `arithmetic`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `resultName` | string | ✓ | — | Result column name |
| `equation` | expression | ✓ | — | Math expression — e.g. (price * quantity) - discount, sqrt(a^2 + b^2), atan2(dy, dx), round(amount * 1.07, 2) |
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


### 🧭 Top-K nearest

**ID:** `top_k_similar` · **Version:** `1.0.0`

Per-row top-K nearest-neighbour search over a vector column. For each row, find the K most similar other rows and add two array columns: top_k_indices (the matching row indices or labels) and top_k_scores (the similarity / distance values). Use as the reduction step after embed_text + vector_similarity to power RAG retrieval, recommendation, and document-deduplication workflows.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `vector` `knn` `nearest` `top-k` `retrieval` `rag` `recommend`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `vectorColumn` | column_ref | ✓ | — | Vector column |
| `k` | integer | ✓ | `5` | K (neighbours per row) |
| `metric` | enum | ✓ | `cosine` | cosine: angular similarity, best for embeddings (highest = most similar). euclidean: L2 distance (lowest = most similar). dot: inner product (highest = most similar; assumes normalised vectors). |
| `labelColumn` | column_ref |  | — | Use this column's values to identify neighbours instead of integer row indices. |
| `includeSelf` | boolean |  | `False` | By default each row's top-K excludes the row itself (cosine similarity 1.0 with self is uninteresting). Enable to keep self in the results. |
| `indicesColumn` | string |  | `top_k_indices` | Indices output column |
| `scoresColumn` | string |  | `top_k_scores` | Scores output column |


### ➕ Vector arithmetic

**ID:** `vector_arithmetic` · **Version:** `1.0.0`

Element-wise arithmetic on vector (array of numeric) columns. Add or subtract two vector columns, scale a vector by a constant, compute the magnitude, or L2-normalise a vector. Use cases: sensor fusion, embedding arithmetic, feature engineering for ML.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `vector` `arithmetic` `embedding` `math` `derive` `linalg`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `op` | enum | ✓ | `add` | add/subtract/multiply/divide: element-wise between two vector columns of equal length. scalar_*: apply a constant to every element. normalize_l2: divide each element by the vector's L2 norm. magnitude: scalar L2 norm of the vector. |
| `leftColumn` | column_ref | ✓ | — | The (left) vector column. Required for every operation. |
| `rightColumn` | column_ref |  | — | Required for add / subtract / multiply / divide. Ignored for scalar_*, normalize_l2, magnitude. |
| `scalar` | number |  | `1.0` | The constant to apply for scalar_multiply / scalar_add. |
| `outputColumn` | string | ✓ | `vector_result` | Output column name |


### 🧭 Vector similarity

**ID:** `vector_similarity` · **Version:** `1.0.0`

Compute similarity / distance between two vector columns. Cosine for embeddings (range [-1, 1]; 1 = identical), dot product for raw scoring, Euclidean / Manhattan for spatial distance.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `vector` `embedding` `similarity` `knn` `ml` `derive`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `leftColumn` | column_ref | ✓ | — | Left vector column |
| `rightColumn` | column_ref | ✓ | — | Right vector column |
| `metric` | enum | ✓ | `cosine` | cosine: angular similarity, best for embeddings (range [-1, 1]). dot: raw inner product (use when vectors are normalized). euclidean: L2 distance, lower = closer. manhattan: L1 distance. |
| `outputColumn` | string | ✓ | `similarity` | Output column name |


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

**ID:** `join` · **Version:** `1.3.0`

Combine rows from two inputs by matching values in key columns. Cardinality strip surfaces row-count consequences before you commit; suggestions auto-detect likely keys; per-key match-quality bars catch wrong-column-picked, type-coercion, and zero-overlap cases upfront. The Result columns panel makes provenance (left/right/coalesced) glanceable and lets each column be excluded or renamed inline.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 2 · ➡️ outputs: 1 · rows: unknown · schema: rebuilds

Tags: `join` `combine` `merge`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `kind` | enum | ✓ | `inner` | inner = matching rows only; left/right = keep all of one side; full = keep both sides' rows (NULLs where unmatched); anti_left = rows on the left WITHOUT a match; anti_right = mirror. |
| `keys` | array | ✓ | — | Keys |
| `columnCollisions` | enum |  | `keep_both` | How to resolve columns that exist on both sides (and aren't keys). 'keep_both' suffixes them; 'coalesce' uses left, falling back to right when null; 'keep_left'/'keep_right' drops one side. |
| `suffixes` | array |  | `['_left', '_right']` | Two-element list — first applied to left's collision, second to right's. |
| `outputColumns` | object |  | `{'excluded': [], 'renames': {}}` | Per-column include + rename for the joined output. Defaults to every column at its natural name. Provenance IDs key on the source side: 'L:<col>' for left, 'R:<col>' for right, 'C:<col>' for coalesced (when collision rule = coalesce). |


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

## 🔬 Analyze

### ⏳ ACF + PACF

**ID:** `acf_pacf` · **Version:** `1.0.0`

Compute autocorrelation (ACF) and partial autocorrelation (PACF) at lags 1..N. Output is a long-form DataFrame ready to feed export_to_image (line) for the classic ACF/PACF stem plots used in ARIMA(p,d,q) order selection.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:time_series_pro`

Tags: `time-series` `diagnostics`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `value` | column_ref | ✓ | — | Time-series value column |
| `max_lag` | integer |  | `40` | Max lag |


### ⏳ Augmented Dickey-Fuller

**ID:** `adf_test` · **Version:** `1.0.0`

Unit-root test. H0: series has a unit root (= non-stationary). Rejecting H0 (small p-value) means the series is stationary. Required check before ARIMA — non-stationary inputs need differencing first.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:time_series_pro`

Tags: `time-series` `stationarity`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `value` | column_ref | ✓ | — | Time-series value column |
| `regression` | enum |  | `c` | c = constant; ct = constant + linear trend; ctt = + quadratic; n = no constant. |


### ⏳ Anomaly · rolling z-score

**ID:** `anomaly_zscore` · **Version:** `1.0.0`

Flag time-series points whose distance from a rolling mean exceeds N standard deviations. Robust to slow drift (it's relative to the local window) and surfaces both isolated spikes and short bursts. Adds `zscore` and `is_anomaly` columns; doesn't drop rows so downstream steps decide what to do.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:time_series_pro`

Tags: `time-series` `anomaly` `outlier` `zscore`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `value` | column_ref | ✓ | — | Time-series value column |
| `window` | integer |  | `30` | Number of rows behind each point used to compute the local mean + stddev. Larger window = slower to react but more stable baseline. |
| `threshold` | number |  | `3.0` | Points whose \|z-score\| exceeds this are flagged. 2σ ≈ 5% of normal data; 3σ ≈ 0.3%; 4σ ≈ 0.006%. |
| `min_periods` | integer |  | `10` | Don't flag the first N rows where the rolling stats haven't stabilized yet. |


### 📐 One-way ANOVA

**ID:** `anova` · **Version:** `1.0.0`

One-way ANOVA: does the mean of `value` differ across the levels of `group`? Returns F-statistic, p-value, between/within group sums-of-squares, η² (eta-squared) effect size.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:stats_pro`

Tags: `statistics`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `value` | column_ref | ✓ | — | Value column |
| `group` | column_ref | ✓ | — | Group column |


### 📐 Bootstrap CI

**ID:** `bootstrap_ci` · **Version:** `1.0.0`

Distribution-free confidence interval around a statistic by resampling with replacement. Works when the data isn't normal and parametric CIs would lie. Returns mean/median estimate, lower bound, upper bound, and width at the requested confidence level.

🛠 engine: `polars` · ⚠️ non-deterministic · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:stats_pro`

Tags: `statistics`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `value` | column_ref | ✓ | — | Value column |
| `statistic` | enum |  | `mean` | Statistic |
| `confidence` | number |  | `0.95` | Confidence level |
| `n_iter` | integer |  | `2000` | Bootstrap iterations |
| `seed` | integer |  | `0` | Set to a non-zero value for reproducible CIs. |


### ⏳ Changepoint detection

**ID:** `changepoint_detection` · **Version:** `1.0.0`

Find rows where the time series shifts in mean. Uses a rolling-window CUSUM approach — distribution-free, no scipy required. Returns a `is_changepoint` boolean column flagging the rows where the change occurred plus a `cusum` column for the test statistic so you can plot it.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:time_series_pro`

Tags: `time-series` `anomaly`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `value` | column_ref | ✓ | — | Time-series value column |
| `threshold` | number |  | `5.0` | CUSUM threshold (in σ). Higher = fewer detected changes. Default 5σ flags only large shifts. |


### 📐 Chi-squared test

**ID:** `chi_square` · **Version:** `1.0.0`

Chi-squared test of independence between two categorical columns. Builds the contingency table, returns chi² statistic, p-value, degrees of freedom, and Cramér's V effect size.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:stats_pro`

Tags: `statistics` `categorical`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `row` | column_ref | ✓ | — | Row column |
| `col` | column_ref | ✓ | — | Column column |


### 📊 Correlation matrix

**ID:** `correlation_matrix` · **Version:** `1.0.0`

Pairwise correlation between numeric columns. Outputs a long-form table (col_a, col_b, r) and renders a heatmap as a side-effect artifact.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

Tags: `stats` `ml` `correlation` `exploratory`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `columns` | column_refs |  | — | Numeric columns to correlate. Empty = all numeric columns. |
| `method` | enum | ✓ | `pearson` | Method |
| `render` | boolean |  | `True` | Render heatmap |
| `title` | string |  | `Correlation matrix` | Title |

**Use case + example**

**When to use:** quick sanity check before modeling — which numeric columns move together, which are independent, which redundant.

**Example:** stock returns. Compute pairwise correlation across 5 tickers' close-price columns; spot any pair with |r| > 0.9 that you can drop or combine.

```json
{
  "step": "correlation_matrix",
  "params": {
    "columns": ["AAPL", "MSFT", "NVDA", "AMD", "GOOG"],
    "method": "pearson",
    "title": "Tech basket — daily returns"
  }
}
```

**Output:** a long-form `(col_a, col_b, r)` table you can filter further. The rendered heatmap is added to the run's artifacts panel.

![correlation heatmap](images/tutorials/tutorial-pca-flowers.png)

(Sample image is from PCA — the correlation heatmap looks similar but with red/blue divergent palette centered at 0.)


### 📐 Effect size

**ID:** `effect_size` · **Version:** `1.0.0`

Effect-size measures for two-group comparisons. Cohen's d (standardized mean difference), Hedges' g (small-sample-corrected d), and Glass' delta. A p-value tells you whether a difference exists; effect size tells you how big it is.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:stats_pro`

Tags: `statistics`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `value` | column_ref | ✓ | — | Value column |
| `group` | column_ref | ✓ | — | Group column (binary) |


### ⏳ KPSS test

**ID:** `kpss_test` · **Version:** `1.0.0`

Companion to ADF — tests the OPPOSITE null hypothesis. H0: series is stationary. Rejecting (small p-value) means non-stationary. Best practice: run BOTH ADF and KPSS; if both agree, you have a confident verdict.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:time_series_pro`

Tags: `time-series` `stationarity`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `value` | column_ref | ✓ | — | Time-series value column |
| `regression` | enum |  | `c` | c = level-stationary; ct = trend-stationary. |


### 📐 Two-sample KS test

**ID:** `ks_test` · **Version:** `1.0.0`

Two-sample Kolmogorov-Smirnov test — do two groups have the same distribution at all? Distribution-free; works even when neither group is normal. Use this instead of t_test when you can't assume normality, or as a follow-up when t_test is significant and you want to understand whether the distributions differ in shape (not just mean).

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:statspack`

Tags: `statistics` `hypothesis-test` `distribution`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `value` | column_ref | ✓ | — | Value column (numeric) |
| `group` | column_ref | ✓ | — | Categorical column with exactly two distinct non-null values. |
| `alternative` | enum |  | `two-sided` | two-sided = distributions differ; less / greater = one-sided test on the cumulative distribution function. |


### 📐 Mann-Whitney U test

**ID:** `mann_whitney` · **Version:** `1.0.0`

Non-parametric two-sample test — works without assuming normality. Use this when t_test's assumptions don't hold or when you have ordinal data. Returns U statistic, p-value, rank-biserial correlation effect size.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:stats_pro`

Tags: `statistics` `non-parametric`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `value` | column_ref | ✓ | — | Value column |
| `group` | column_ref | ✓ | — | Group column (binary) |
| `alternative` | enum |  | `two-sided` | Alternative |


### 📐 Multiple-comparison correction

**ID:** `multiple_comparison_correction` · **Version:** `1.0.0`

Adjust p-values for multiple-test inflation. Takes a column of raw p-values, returns adjusted p-values + significance flags under the chosen method (Bonferroni, Holm, Benjamini-Hochberg FDR). Without correction, running 20 tests at α=0.05 yields a 64% chance of a false positive somewhere.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:stats_pro`

Tags: `statistics` `correction`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `p_column` | column_ref | ✓ | — | p-value column |
| `method` | enum |  | `fdr_bh` | fdr_bh = Benjamini-Hochberg (most common); bonferroni = strictest; holm = step-down Bonferroni; fdr_by = Benjamini-Yekutieli (no independence assumption). |
| `alpha` | number |  | `0.05` | α |


### 📐 Two-sample t-test

**ID:** `t_test` · **Version:** `1.0.0`

Welch's two-sample independent t-test. Compares the mean of `value` between the two groups in `group`, returns t, p-value, df, per-group means + sample sizes. Assumes the value column is roughly normal within each group; use ks_test if you can't assume that.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:statspack`

Tags: `statistics` `hypothesis-test` `compare-groups`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `value` | column_ref | ✓ | — | Value column (numeric) |
| `group` | column_ref | ✓ | — | Categorical column with exactly two distinct non-null values. |
| `alternative` | enum |  | `two-sided` | two-sided = means differ; less = group A < group B; greater = group A > group B (alphabetical order). |
| `equal_var` | boolean |  | `False` | Off (default) = Welch's t (recommended). On = classical Student's t — only correct when both groups have similar variance. |


---

## 🧠 Model

### 🌌 DBSCAN clustering

**ID:** `dbscan` · **Version:** `1.0.0`

Density-based clustering — finds clusters of arbitrary shape and labels low-density points as noise (cluster id = -1). Adds a 'cluster' column and renders a scatter.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `stats` `ml` `clustering` `dbscan` `density`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `columns` | column_refs |  | — | Feature columns |
| `eps` | number |  | `0.5` | Two points are neighbors if their distance is below ε. Run on standardized data: 0.3–0.8 is a typical starting range. |
| `min_samples` | integer |  | `5` | Minimum points within ε for a point to be considered a core point. Heuristic: dim×2. |
| `scale` | boolean |  | `True` | Standardize features |
| `output_column` | string |  | `cluster` | Output column name |
| `render` | boolean |  | `True` | Render scatter plot |
| `title` | string |  | `DBSCAN clusters` | Title |


### 🔮 Forecast (time-series)

**ID:** `forecast` · **Version:** `1.0.0`

Project a time series N steps into the future. Uses Holt-Winters exponential smoothing (handles trend + seasonality) by default. Output extends the source with future timestamps + a 'forecast' column and 95% prediction intervals.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_grow · schema: modifies

Tags: `time-series` `forecast` `prediction` `holt-winters`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `time_column` | column_ref | ✓ | — | Time column |
| `value_column` | column_ref | ✓ | — | Value column |
| `horizon` | integer | ✓ | `30` | Steps to forecast |
| `method` | enum |  | `auto` | 'auto' picks holt_winters when seasonality is plausible, else ets. 'naive' is last-observation-carried-forward. |
| `seasonal_period` | integer |  | `0` | Observations per season (e.g. 7 for weekly cycles in daily data, 12 for yearly cycles in monthly). 0 = auto-detect. |
| `render` | boolean |  | `True` | Render forecast plot |
| `title` | string |  | `Forecast` | Title |

**Use case + example**

**When to use:** project a daily/weekly/monthly time series N steps into the future, with prediction intervals.

**Example:** 30-day stock close forecast.

```json
{
  "step": "forecast",
  "params": {
    "time_column": "date",
    "value_column": "close",
    "horizon": 30,
    "method": "holt_winters",
    "seasonal_period": 7
  }
}
```

The output extends the input frame: existing rows get `forecast = null`, new future rows have `forecast` + `forecast_lo` / `forecast_hi` 95% prediction intervals. The artifact image overlays observed + forecast + shaded interval:

![stock forecast](images/tutorials/tutorial-forecast-stock.png)

**Method selection:** `auto` picks `holt_winters` when the seasonal period is plausible, else `ets`. Set explicitly for reproducibility. `naive` (last-observation-carried-forward) is the baseline you should beat.


### 🔮 K-Means clustering

**ID:** `kmeans` · **Version:** `1.0.0`

Partitions rows into K clusters by minimizing within-cluster variance. Adds a 'cluster' column and renders a 2-D scatter (uses PCA for dimensionality > 2).

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `stats` `ml` `clustering` `kmeans` `unsupervised`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `columns` | column_refs |  | — | Numeric columns used for clustering. Empty = all numeric columns. |
| `k` | integer | ✓ | `4` | Number of clusters (k) |
| `scale` | boolean |  | `True` | Standardize features |
| `seed` | integer |  | `42` | Random seed |
| `output_column` | string |  | `cluster` | Output column name |
| `render` | boolean |  | `True` | Render scatter plot |
| `title` | string |  | `K-Means clusters` | Title |

**Use case + example**

**When to use:** group customers / products / sensors into K behavioral clusters. Output is a new `cluster` column you can join back, filter, or render.

**Example:** segment customers by spend + tenure.

```json
{
  "step": "kmeans",
  "params": {
    "columns": ["monthly_revenue", "tenure_days"],
    "k": 4,
    "scale": true,
    "output_column": "segment"
  }
}
```

If you give kmeans more than 2 features, the auto-rendered scatter projects via PCA so you can still visualize the clusters. The cluster summary (sizes, inertia) lands in the run's artifacts panel.

**Tip:** combine with `correlation_matrix` and the `kmeans` `inertia` metric across several values of K (the elbow heuristic) to pick K. DIG's `k` param doesn't auto-pick K — that's a deliberate decision so you can see the trade-off, not a magic number.


### 📐 Linear regression

**ID:** `linear_regression` · **Version:** `1.0.0`

Ordinary least squares — fit y = β·X + ε. Adds a 'predicted' and 'residual' column. Renders the fit (single feature) or actual-vs-predicted (multiple features).

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `stats` `ml` `regression` `linear` `ols`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `y` | column_ref | ✓ | — | Target column (y) |
| `x_columns` | column_refs | ✓ | — | Feature columns (X) |
| `fit_intercept` | boolean |  | `True` | Fit intercept |
| `predicted_column` | string |  | `predicted` | Predicted column name |
| `residual_column` | string |  | `residual` | Residual column name |
| `render` | boolean |  | `True` | Render fit / actual-vs-predicted |
| `title` | string |  | `Linear regression` | Title |


### 🧬 PCA (dimensionality reduction)

**ID:** `pca` · **Version:** `1.0.0`

Principal Component Analysis — reduces N numeric columns to K orthogonal components ordered by variance explained. Adds PC1..PCK columns to the data and renders a 2-D scatter of the first two components.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `stats` `ml` `dimensionality-reduction` `pca`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `columns` | column_refs |  | — | Numeric columns to project. Empty = all numeric columns. |
| `n_components` | integer |  | `2` | Number of components |
| `scale` | boolean |  | `True` | Strongly recommended unless your columns are already on the same scale. |
| `color_by` | column_ref |  | — | Optional categorical or numeric column used to color points in the rendered scatter. |
| `render` | boolean |  | `True` | Render 2-D scatter (PC1 × PC2) |
| `title` | string |  | `PCA` | Title |

**Use case + example**

**When to use:** dataset has many numeric columns and you want a 2-D view that captures most of the variance. PCA is fast, deterministic, linear — best baseline for "what does my data look like?".

**Example:** flowers dataset (`samples/flowers-demo.csv`). Project the 4 morphological measurements onto 2 components, color by species.

```json
{
  "step": "pca",
  "params": {
    "columns": ["petal_length", "petal_width", "sepal_length", "sepal_width"],
    "n_components": 2,
    "color_by": "species",
    "title": "Flowers — PCA"
  }
}
```

The output frame keeps every row and adds `PC1`, `PC2` columns. The rendered scatter shows the components labeled with variance explained:

![PCA scatter](images/tutorials/tutorial-pca-flowers.png)

When >2 components are useful, raise `n_components` — the additional `PC3..PCK` columns are still added to the data, you can use them for downstream `kmeans` / `linear_regression` etc.


### 🔂 Seasonal decomposition

**ID:** `seasonal_decompose` · **Version:** `1.0.0`

Decompose a time series into trend, seasonal, and residual components (additive or multiplicative). Adds 3 new columns and renders a 4-panel plot.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

Tags: `time-series` `seasonal` `decompose` `trend`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `time_column` | column_ref | ✓ | — | Time column |
| `value_column` | column_ref | ✓ | — | Value column |
| `model` | enum | ✓ | `additive` | Use 'additive' if seasonal amplitude is roughly constant; 'multiplicative' if it grows/shrinks with the level. |
| `period` | integer |  | `0` | Number of observations per season (e.g. 7 for daily data with weekly seasonality, 12 for monthly with yearly). 0 = auto-detect from time column frequency. |
| `render` | boolean |  | `True` | Render decomposition plot |
| `title` | string |  | `Seasonal decomposition` | Title |

**Use case + example**

**When to use:** understand why a time series looks the way it does — separate the slow trend, the periodic seasonal pattern, and the residual noise.

**Example:** is the recent uptick in our daily revenue real growth, or just the typical month-end seasonal bump?

```json
{
  "step": "seasonal_decompose",
  "params": {
    "time_column": "date",
    "value_column": "revenue",
    "model": "additive",
    "period": 7
  }
}
```

The output adds `trend`, `seasonal`, `residual` columns. The rendered 4-panel plot lets you eyeball the decomposition:

![seasonal decomposition](images/tutorials/tutorial-seasonal-stock.png)

Use `additive` when seasonal amplitude is roughly constant over time; `multiplicative` when the swings grow / shrink with the level (e.g. growing exponential trend).


### 🌠 t-SNE (2-D embedding)

**ID:** `tsne` · **Version:** `1.0.0`

t-distributed Stochastic Neighbor Embedding — non-linear dimensionality reduction great for visualizing high-dimensional clusters. Adds tSNE_1 / tSNE_2 columns and renders a scatter.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: modifies

Tags: `stats` `ml` `embedding` `dimensionality-reduction` `tsne`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `columns` | column_refs |  | — | Feature columns |
| `perplexity` | number |  | `30` | Roughly: number of nearest neighbors per point. 5–50 is common; higher for larger datasets. |
| `max_rows` | integer |  | `5000` | t-SNE is O(n²); above ~10k points is impractical. Larger samples are downsampled. |
| `scale` | boolean |  | `True` | Standardize features |
| `seed` | integer |  | `42` | Random seed |
| `color_by` | column_ref |  | — | Color points by |
| `render` | boolean |  | `True` | Render scatter |
| `title` | string |  | `t-SNE` | Title |


### 🌌 UMAP (2-D embedding)

**ID:** `umap` · **Version:** `1.0.0`

Uniform Manifold Approximation and Projection — modern non-linear dim reduction that preserves both local + global structure better than t-SNE and scales to 100k+ rows. Adds UMAP_1 / UMAP_2 columns and renders a scatter.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: modifies

Tags: `stats` `ml` `embedding` `dimensionality-reduction` `umap`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `columns` | column_refs |  | — | Feature columns |
| `n_neighbors` | integer |  | `15` | Smaller → more local structure; larger → more global. 5–50 is typical. |
| `min_dist` | number |  | `0.1` | How tightly UMAP is allowed to pack points; lower → tighter clumps. |
| `max_rows` | integer |  | `50000` | Max rows (sampled) |
| `scale` | boolean |  | `True` | Standardize features |
| `seed` | integer |  | `42` | Random seed |
| `color_by` | column_ref |  | — | Color points by |
| `render` | boolean |  | `True` | Render scatter |
| `title` | string |  | `UMAP` | Title |


---

## ✅ Validate

### ✅ Data quality expectations

**ID:** `expectations` · **Version:** `1.1.0`

Assert data quality rules (unique, not_null, between, in, regex_match, row_count_between, null_fraction, cardinality_between). Failures surface in the run's artifacts; optionally fail the run, fire a Slack-compatible webhook, or both. Per-rule severity (error|warning) controls run-failure semantics.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

Tags: `dq` `data-quality` `expectations` `validation` `slack` `webhook`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `rules` | array | ✓ | — | List of {kind, column?, args, severity?, label?}. severity ∈ error \| warning (default error). label is a human-readable name for the rule. |
| `fail_on_violation` | boolean |  | `False` | If true, the step raises and the run is marked failed when any error-severity rule fails. Warning-severity violations never fail the run. |
| `notify_webhook_url` | string |  | `` | URL to POST a Slack-compatible payload when any rule fails. Works with Slack incoming webhooks, Discord, Mattermost, generic HTTP receivers. |
| `notify_on` | enum |  | `any_failure` | never: webhook is disabled. any_failure: any rule failure (warning or error). error_only: error-severity only. |

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


---

## 📈 Visualize

### 🎯 Bullet chart

**ID:** `bullet_chart` · **Version:** `1.0.0`

Edward Tufte's compact target-vs-actual chart. A single horizontal bar shows the actual value; a thin marker shows the target; quantitative bands (poor / OK / good) shade the background. One row per row in the input.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:business_charts`

Tags: `chart` `business` `kpi` `target` `bullet`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `labelColumn` | column_ref | ✓ | — | Label column |
| `actualColumn` | column_ref | ✓ | — | Actual value column |
| `targetColumn` | column_ref | ✓ | — | Target column |
| `poorMaxColumn` | column_ref |  | — | Poor band upper bound (optional) |
| `okMaxColumn` | column_ref |  | — | OK band upper bound (optional) |
| `goodMaxColumn` | column_ref |  | — | Good band upper bound (optional) |
| `title` | string |  | `Performance vs target` | Title |
| `output_path` | string |  | — | Defaults to data/outputs/<run>/<step>.png |


### 🕯 Candlestick / OHLC chart

**ID:** `candlestick_chart` · **Version:** `1.0.0`

Financial candlestick chart from Open / High / Low / Close columns. Each row is one bar; green for rise (close >= open), red for fall. The standard chart for any financial reporting deliverable.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:time_series_pro`

Tags: `chart` `time-series` `finance` `candlestick` `ohlc`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `dateColumn` | column_ref | ✓ | — | Date column |
| `openColumn` | column_ref | ✓ | — | Open column |
| `highColumn` | column_ref | ✓ | — | High column |
| `lowColumn` | column_ref | ✓ | — | Low column |
| `closeColumn` | column_ref | ✓ | — | Close column |
| `volumeColumn` | column_ref |  | — | If set, draws a volume bar chart in a sub-panel below the candles. |
| `title` | string |  | `Candlestick chart` | Title |
| `output_path` | string |  | — | Defaults to data/outputs/<run>/<step>.png |


### 🖼 Export to image

**ID:** `export_to_image` · **Version:** `1.1.0`

Render the data as a PNG/SVG via matplotlib + seaborn. Distribution charts (histogram / density / box / violin), categorical charts (bar / stacked / percent stacked), bivariate (scatter / line / hexbin / heatmap / joint), multivariate (pair plot / scatter3d / bubble). 'auto' picks a sensible chart from the column types.

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
| `columns` | column_refs |  | — | Numeric columns to include in the scatter matrix. Required for kind = pair. 2-8 columns is the practical range. |
| `hue` | column_ref |  | — | Optional grouping column. Box / violin / pair / joint / bubble use it to color rows by category. |
| `title` | string |  | — | Title |
| `format` | enum | ✓ | `png` | Format |
| `width` | integer |  | `1600` | Width (px) |
| `height` | integer |  | `1200` | Height (px) |
| `dpi` | integer |  | `144` | 144 ≈ Retina; 300 = print quality. The live preview caps at 144 even when set higher (300-DPI raster scaled to a small preview pane makes labels look oversized); your full Run honors the value as-set. |
| `font_scale` | number |  | — | Multiplier on label / tick / legend fonts. Leave blank for auto — the renderer picks a seaborn context (paper / notebook / talk) sized to the figure dimensions. Set explicitly to override (1.0 = notebook baseline). |
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


### 🗺 Export to map

**ID:** `export_to_map` · **Version:** `1.1.0`

Render geographic data on an interactive world map. Four modes: points (markers), choropleth (color-coded polygons), heat (kernel-density overlay), arc (origin → destination lines). Optional polygon overlay layer combines any base mode with district / zone outlines. Output is interactive Leaflet HTML or static matplotlib PNG.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

Tags: `export` `map` `geo` `leaflet` `viz` `world` `longitude` `latitude`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `mode` | enum | ✓ | `points` | points: one marker per row at lat/lon (default). choropleth: color polygon regions by a numeric value (needs a parsed geometry column + value column). heat: kernel-density heat overlay from lat/lon. arc: origin → destination lines (needs origin lat/lon + destination lat/lon). |
| `format` | enum | ✓ | `lat_lon` | How the location column encodes coordinates. 'lat_lon' = '37.77,-122.42' (Google / Apple style), 'lon_lat' = '-122.42,37.77' (GeoJSON / WKT axis order), 'wkt_point' = 'POINT(-122.42 37.77)', 'separate_columns' = pick a lat column and a lon column separately. |
| `location` | column_ref |  | — | The column with the geographical coordinates. Required unless format = 'separate_columns' (then leave blank and pick lat_col + lon_col instead). |
| `lat_col` | column_ref |  | — | Latitude column |
| `lon_col` | column_ref |  | — | Longitude column |
| `name_col` | column_ref |  | — | Column used as the bold tooltip headline. If blank, the row index is used. |
| `comment_col` | column_ref |  | — | Column rendered underneath the headline. Free-form text. |
| `geometry_col` | column_ref |  | — | WKB-bytes column from parse_geometry. Required for choropleth mode and for the polygon-overlay layer. |
| `value_col` | column_ref |  | — | Numeric column. Choropleth: colors each polygon. Heat: weights the kernel density. |
| `origin_lat_col` | column_ref |  | — | Origin latitude column |
| `origin_lon_col` | column_ref |  | — | Origin longitude column |
| `dest_lat_col` | column_ref |  | — | Destination latitude column |
| `dest_lon_col` | column_ref |  | — | Destination longitude column |
| `color_scale` | enum |  | `viridis` | Sequential color ramp used to map the value column to polygon fills (choropleth) or heat intensity (heat). |
| `overlay_polygon_col` | column_ref |  | — | Optional WKB-bytes geometry column drawn as outlined polygons on top of the base mode. Use to place markers / heat / arcs over named zones. |
| `title` | string |  | — | Title |
| `marker_color` | string |  | `#10b981` | Any valid CSS color — hex, rgb(), or named. Default emerald (#10b981) matches the DIG palette. |
| `marker_radius` | integer |  | `6` | Marker radius (px) |
| `tile_provider` | enum |  | `carto-light` | Tile basemap. Carto Light is the cleanest for data overlays; OSM has the most labels; Esri NatGeo is the prettiest but heaviest. |
| `max_points` | integer |  | `20000` | If the input has more rows than this, the step samples down. Browsers struggle past ~50K markers. |
| `format_out` | enum |  | `html` | 'html' produces an interactive Leaflet map (hover tooltips, zoom, pan). 'png' produces a static rasterised view — useful for headless CI. |
| `width` | integer |  | `1200` | Width (px) |
| `height` | integer |  | `800` | Height (px) |
| `path` | string |  | — | Defaults to data/outputs/<run>/<step>.html (or .png). |


### 📈 Funnel chart

**ID:** `funnel_chart` · **Version:** `1.0.0`

Sequential conversion-funnel visualisation. Each row is a stage; the bar shrinks step-by-step. Drop-off labels show the percentage retained vs. the previous stage.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:business_charts`

Tags: `chart` `business` `conversion`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `stage` | column_ref | ✓ | — | Stage column |
| `value` | column_ref | ✓ | — | Count / value column |
| `title` | string |  | `Funnel` | Title |
| `output_path` | string |  | — | Output path |


### 🌡 Gauge chart

**ID:** `gauge_chart` · **Version:** `1.0.0`

Speedometer-style single-metric gauge. The needle points to the actual value within a min-to-max range; colored arcs (red / amber / green by default) show good/bad zones. One row per row in the input.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:business_charts`

Tags: `chart` `business` `kpi` `gauge` `speedometer`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `labelColumn` | column_ref | ✓ | — | Label column |
| `valueColumn` | column_ref | ✓ | — | Value column |
| `minValue` | number |  | `0.0` | Min |
| `maxValue` | number |  | `100.0` | Max |
| `redMax` | number |  | — | Defaults to 30% of (max-min). |
| `amberMax` | number |  | — | Defaults to 70% of (max-min). |
| `title` | string |  | `Gauge` | Title |
| `output_path` | string |  | — | Defaults to data/outputs/<run>/<step>.png |


### 🪞 Horizon chart

**ID:** `horizon_chart` · **Version:** `1.0.0`

Compact small-multiples view for many time series. Each series is rendered as a colored band wrapped at fixed thresholds — three bands of progressively darker color above the median, mirrored below. Lets you eyeball ~50+ series in the vertical space a single line chart would need.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:time_series_pro`

Tags: `chart` `time-series` `horizon` `small-multiples`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `dateColumn` | column_ref | ✓ | — | Date column |
| `groupColumn` | column_ref | ✓ | — | Series (group) column |
| `valueColumn` | column_ref | ✓ | — | Value column |
| `bands` | integer |  | `3` | Number of bands |
| `title` | string |  | `Horizon chart` | Title |
| `output_path` | string |  | — | Defaults to data/outputs/<run>/<step>.png |


### 🟦 Marimekko / mosaic

**ID:** `mosaic_marimekko` · **Version:** `1.0.0`

Two-dimensional part-to-whole. Column widths proportional to the row group's total; column heights proportional to the column group's share within that row. Use for revenue × channel × segment, market share × geography × time.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:business_charts`

Tags: `chart` `business` `composition` `marimekko` `mosaic`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `rowGroup` | column_ref | ✓ | — | Row group (x-axis category) |
| `columnGroup` | column_ref | ✓ | — | Stack group (y stacking category) |
| `valueColumn` | column_ref | ✓ | — | Value column |
| `title` | string |  | `Marimekko` | Title |
| `output_path` | string |  | — | Defaults to data/outputs/<run>/<step>.png |


### 📈 Pareto chart

**ID:** `pareto_chart` · **Version:** `1.0.0`

Sorted bar chart of category values + cumulative-percentage line on a secondary axis. The 80/20 chart — useful for showing which few categories drive most of the total.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:business_charts`

Tags: `chart` `business`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `label` | column_ref | ✓ | — | Label column |
| `value` | column_ref | ✓ | — | Value column |
| `top_n` | integer |  | `20` | Top N categories |
| `title` | string |  | `Pareto` | Title |
| `output_path` | string |  | — | Output path |


### 🥧 Pie / donut chart

**ID:** `pie_donut` · **Version:** `1.0.0`

Classic part-to-whole pie or donut. Each row contributes one slice; slice angle proportional to the value column. Donut variant has a hole in the middle for a center label.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:business_charts`

Tags: `chart` `business` `composition` `pie` `donut`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `labelColumn` | column_ref | ✓ | — | Label column |
| `valueColumn` | column_ref | ✓ | — | Value column |
| `variant` | enum |  | `donut` | Variant |
| `centerLabel` | string |  | — | Center label (donut only) |
| `showPercents` | boolean |  | `True` | Show percent labels |
| `title` | string |  | `Composition` | Title |
| `output_path` | string |  | — | Defaults to data/outputs/<run>/<step>.png |


### 🌊 Stream graph

**ID:** `stream_graph` · **Version:** `1.0.0`

Stacked area chart with center-baselined symmetry (the classic 'wiggle' algorithm). Use for displaying multi-series totals over time where the *shape* of each series matters more than absolute zero — music genres over time, browser market share, social-media topic mix.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:time_series_pro`

Tags: `chart` `time-series` `stream` `stacked area`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `dateColumn` | column_ref | ✓ | — | Date / x-axis column |
| `groupColumn` | column_ref | ✓ | — | Series (group) column |
| `valueColumn` | column_ref | ✓ | — | Value column |
| `color_scale` | enum |  | `viridis` | Color scale |
| `title` | string |  | `Stream graph` | Title |
| `output_path` | string |  | — | Defaults to data/outputs/<run>/<step>.png |


### 📈 Waterfall chart

**ID:** `waterfall_chart` · **Version:** `1.0.0`

Cumulative-contribution chart. Each row is one bar: positives stack up, negatives stack down, ending at the final total. Bonus row at the right shows the total. Common for revenue / cost-bridge analyses.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:business_charts`

Tags: `chart` `business`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `label` | column_ref | ✓ | — | Label column |
| `value` | column_ref | ✓ | — | Value column (signed) |
| `title` | string |  | `Waterfall` | Title |
| `output_path` | string |  | — | Output path |


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


---

## 🧩 Custom

### 🪆 Passthrough

**ID:** `passthrough` · **Version:** `1.0.0`

Identity step — emits its input unchanged. Used internally by the sub-pipeline inliner to keep the wrapper node id alive in the flat DAG so callers (compile terminal selection, downstream wiring, lineage) don't need to know about inlining.

🛠 engine: `sql` · 🌐 browser: `sql` · ⬅️ inputs: 1 · ➡️ outputs: 1

**Parameters**

_(no parameters)_
