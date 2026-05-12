# 📚 DataInsightGrove — Step library

This page documents every step DIG ships with. It is **auto-generated** from each step's `manifest.json` plus optional hand-written notes under `docs/_steps/<step_id>.md` — re-run `python scripts/gen-steps-doc.py` whenever you add or change a step.

**218 steps** across ✂️ Shape (15), 🧼 Clean (27), 🪄 Derive (52), 🤝 Combine (6), 📊 Aggregate (23), 🔬 Analyze (35), 🧠 Model (8), ✅ Validate (15), 📈 Visualize (32), 📤 Output (4), 🧩 Custom (1).

## Index

### ✂️ Shape

- [🔍 Filter rows](#filter-rows) — Keep rows where the predicate evaluates to true.
- [📤 Flatten array](#flatten-array) — Reshape an array column.
- [🔄 Matrix inverse](#matrix-inverse) — Invert a square matrix.
- [🔁 Matrix transpose](#matrix-transpose) — Transpose a matrix.
- [📦 Pack into struct](#pack-into-struct) — Combine multiple columns into a single struct column.
- [📐 Parse geometry](#parse-geometry) — Parse a column of geometry strings (WKT or GeoJSON) into a typed geometry column.
- [📐 Parse geometry](#parse-geometry) — Parse a column of geometry strings (WKT or GeoJSON) into a typed geometry column.
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
- [⬇ CIC decimation](#cic-decimation) — Cascaded-Integrator-Comb decimation filter — efficient downsampling with built-in low-pass filtering.
- [🏥 HIPAA Safe-Harbor de-identify](#hipaa-safe-harbor-de-identify) — Apply HIPAA Safe-Harbor de-identification: drop direct identifiers (name, SSN, MRN, address, phone, email, dates of service if not year-only), generalize ZIP to 3-digit, generalize ages > 89.
- [↔️ Forward / backward fill](#forward--backward-fill) — Fill nulls by carrying the previous (forward fill) or next (backward fill) value.
- [📈 Interpolate nulls](#interpolate-nulls) — Linear or spline interpolation between known values.
- [🧬 K-Nearest-Neighbours imputation](#k-nearest-neighbours-imputation) — Fill nulls in numeric columns by averaging the K nearest non-null rows (Euclidean distance over the chosen feature columns).
- [🩹 Impute mean / median / mode](#impute-mean--median--mode) — Fill nulls in selected columns with the per-column statistic (mean, median, or mode).
- [🔁 MICE imputation (chained equations)](#mice-imputation-chained-equations) — Multiple Imputation by Chained Equations — fits a regression for each column on the others, fills nulls with predictions, repeats until convergence.
- [🔏 PII redact](#pii-redact) — Replace pattern matches in text columns with a placeholder.
- [🎭 Seeded pseudonymization](#seeded-pseudonymization) — Replace identifying values with deterministic but opaque tokens (HMAC-SHA256 with a secret seed).
- [⏳ Replace outliers](#replace-outliers) — Replace values flagged in an `is_anomaly` (or boolean) column with a rolling-median estimate.
- [🔤 Replace text](#replace-text) — Find-and-replace inside a string column.
- [🎯 Round numeric](#round-numeric) — Round a numeric column to N decimal places.
- [🧂 Salted hash](#salted-hash) — Hash columns with a per-column salt + global pepper.
- [🎯 Cluster sample](#cluster-sample) — Sample whole groups (clusters) at random rather than individual rows.
- [💧 Reservoir sample](#reservoir-sample) — Single-pass uniform sample of N rows.
- [🎯 Stratified sample](#stratified-sample) — Sample N rows preserving the proportion of each value in the strata column.
- [📐 Systematic sample](#systematic-sample) — Take every Kth row after a random start.
- [⚖️ Weighted sample](#weighted-sample) — Sample N rows where each row's selection probability is proportional to a weight column.
- [📡 Sensor resample](#sensor-resample) — Resample irregularly-spaced sensor readings to a regular time grid via linear interpolation.
- [📈 SMOTE oversample](#smote-oversample) — Synthetic Minority Oversampling — synthesises new minority-class rows by interpolating between existing nearest-neighbours.
- [📉 Undersample majority](#undersample-majority) — Randomly drop rows from the majority class until classes are balanced (or to a target ratio).
- [🆙 Uppercase string](#uppercase-string) — Convert a string column to uppercase.

### 🪄 Derive

- [🆕 Add column](#add-column) — Add a new column with a typed default value.
- [⏱ Add runtime column](#add-runtime-column) — Add a new column whose value is rendered once per run from a `{{ template }}`.
- [📏 Array length](#array-length) — Add a column with the length of an array column.
- [📝 BERTopic](#bertopic) — Modern transformer-based topic modelling via BERTopic (sentence-transformers + UMAP + HDBSCAN).
- [📦 Bin numeric](#bin-numeric) — Bucket a numeric column into N equal-width bins, or into custom breakpoints.
- [📅 Business days between](#business-days-between) — Count business days (Mon-Fri excluding holidays) between two date columns per row.
- [🚪 Churn lite](#churn-lite) — Lightweight churn flag based on inactivity.
- [🧭 Convert coordinates](#convert-coordinates) — Lossless conversion between polar, Cartesian, and geographic coordinate systems.
- [🔄 Convert units](#convert-units) — Convert a numeric column between units.
- [🏥 CPT lookup](#cpt-lookup) — Look up CPT procedure codes against a bundled mini reference table.
- [🧭 CRS / projection transform](#crs--projection-transform) — Reproject coordinates between coordinate reference systems via pyproj.
- [🧭 CRS / projection transform](#crs--projection-transform) — Reproject coordinates between coordinate reference systems via pyproj.
- [📅 Date snap](#date-snap) — Snap a date to the start (or end) of a calendar period: week, month, quarter, year.
- [➕ Derive column](#derive-column) — Add a new column computed from a SQL expression over existing columns.
- [📏 Distance matrix](#distance-matrix) — Compute pairwise distances between every pair of rows from a vector column.
- [🧠 Embed text (AI)](#embed-text-ai) — Add a vector column with embeddings of a text column.
- [📅 Extract date parts](#extract-date-parts) — Pull year, month, day, day-of-week (etc.
- [🎯 Extract pattern](#extract-pattern) — Extract a regex group from a string column into a new column.
- [📅 Fiscal year parts](#fiscal-year-parts) — Decompose a date into fiscal-year, fiscal-quarter, and fiscal-month for any fiscal-year start month.
- [🌍 Geographic distance](#geographic-distance) — Compute great-circle distance (Haversine, in metres) between two lat/lon points.
- [🌐 Geohash / H3 cell](#geohash--h3-cell) — Add a column with the spatial-index cell that contains each lat/lon point.
- [🌐 Geohash / H3 cell](#geohash--h3-cell) — Add a column with the spatial-index cell that contains each lat/lon point.
- [🏥 ICD-10 lookup](#icd-10-lookup) — Look up ICD-10 diagnosis codes against a bundled mini reference table.
- [📦 Extract from JSON](#extract-from-json) — Pull a value out of a JSON column at the given path.
- [📝 RAKE / YAKE keywords](#rake--yake-keywords) — Unsupervised keyword extraction.
- [⏪ Lag features](#lag-features) — Add lag(N) versions of selected columns.
- [📝 Language detect](#language-detect) — Detect language of each text row via langdetect (Google's language-detection lib port).
- [📝 LDA topic modelling](#lda-topic-modelling) — Latent Dirichlet Allocation via scikit-learn.
- [📊 Logistic regression](#logistic-regression) — Binary classification via logistic regression.
- [🧮 Math equation](#math-equation) — Add a column computed from a math expression over existing columns.
- [🔀 Multi-sensor fusion](#multi-sensor-fusion) — Combine readings from multiple sensors at the same timestamp via weighted average.
- [📝 NER (spaCy)](#ner-spacy) — Extract named entities (PERSON, ORG, GPE, DATE, MONEY, etc.
- [➗ Polynomial features](#polynomial-features) — Add x², x³, x·y interaction features for the chosen numeric columns.
- [📍 Reverse geocode](#reverse-geocode) — Resolve lat/lon points to country / state / city via a bundled lookup table (no external network call).
- [🌊 Rolling window](#rolling-window) — Add rolling-window aggregations (moving average, rolling sum, etc.
- [📐 Min-max scaler](#min-max-scaler) — Rescale each column to [0, 1] (or any user-specified range).
- [📐 Robust scaler](#robust-scaler) — Subtract median, divide by IQR.
- [📐 Standard scaler (z-score)](#standard-scaler-z-score) — Subtract mean, divide by standard deviation.
- [📝 Sentiment (VADER)](#sentiment-vader) — Compute VADER sentiment scores per text row.
- [📈 Stream drift detector](#stream-drift-detector) — Page-Hinkley change-point detector for streaming sensor values.
- [🎯 Target encoding](#target-encoding) — Replace each category with the mean of the target variable for that category.
- [📝 TF-IDF](#tf-idf) — Compute TF-IDF features for a text column.
- [⏱ Time to convert](#time-to-convert) — Per-user time elapsed between the first and final funnel step.
- [📝 Tokenize](#tokenize) — Split text into tokens.
- [🧭 Top-K nearest](#top-k-nearest) — Per-row top-K nearest-neighbour search over a vector column.
- [➕ Vector arithmetic](#vector-arithmetic) — Element-wise arithmetic on vector (array of numeric) columns.
- [🧭 Vector similarity](#vector-similarity) — Compute similarity / distance between two vector columns.
- [🌍 Vincenty distance](#vincenty-distance) — Compute geodesic distance (in metres) between two lat/lon points using Vincenty's formula on the WGS84 ellipsoid.
- [🌍 Vincenty distance](#vincenty-distance) — Compute geodesic distance (in metres) between two lat/lon points using Vincenty's formula on the WGS84 ellipsoid.
- [📊 Weight-of-Evidence + IV](#weight-of-evidence--iv) — Compute Weight of Evidence per category + the column-level Information Value (IV).
- [📊 Yeo-Johnson power transform](#yeo-johnson-power-transform) — Power transform that makes data more Gaussian-like.
- [📐 Z-score](#z-score) — Add a standardized (mean=0, std=1) version of a numeric column as a new column.

### 🤝 Combine

- [🔗 Join](#join) — Combine rows from two inputs by matching values in key columns.
- [🗺 Map-match (snap to nearest reference)](#map-match-snap-to-nearest-reference) — Snap each lat/lon point to the nearest point in a reference table (a separate dataset of named known locations — bus stops, stations, sensor sites, store fronts, registered addresses).
- [🔗 Spatial join](#spatial-join) — Join two inputs on a spatial predicate.
- [🔗 Spatial join](#spatial-join) — Join two inputs on a spatial predicate.
- [🧩 Sub-pipeline](#sub-pipeline) — Embed another saved pipeline as a single step.
- [🔀 Union](#union) — Stack two datasets vertically.

### 📊 Aggregate

- [🥇 First-touch attribution](#first-touch-attribution) — Assign 100% of conversion credit to each user's first touch (chronologically first row in their journey).
- [🥇 Last-touch attribution](#last-touch-attribution) — Assign 100% of conversion credit to each user's last touch before conversion (default in many ad platforms).
- [📏 Linear attribution](#linear-attribution) — Distribute conversion credit equally across all touches in each user's journey.
- [🔗 Markov-chain attribution](#markov-chain-attribution) — Build a transition matrix between channels (start → channels → conversion / null) and compute each channel's removal effect — its contribution to total conversions if removed from the graph.
- [🎯 Position-based attribution (U-shape)](#position-based-attribution-u-shape) — 40% credit to first touch, 40% to last touch, 20% split equally among middle touches.
- [⏳ Time-decay attribution](#time-decay-attribution) — Credit decays exponentially with time-from-conversion.
- [🏥 Charlson Comorbidity Index](#charlson-comorbidity-index) — Compute the Charlson Comorbidity Index per patient from a long-form (patient_id, icd_code) input.
- [👥 Cohort table](#cohort-table) — Build a classic cohort table: rows = cohort (signup period), columns = period offset, cells = retained-user count or rate.
- [🔒 DP aggregate (Gaussian)](#dp-aggregate-gaussian) — Sum a numeric column with Gaussian noise calibrated to (epsilon, delta, sensitivity) for (ε, δ)-differential privacy.
- [🔒 DP aggregate (Laplace)](#dp-aggregate-laplace) — Sum a numeric column with Laplace noise calibrated to (epsilon, sensitivity) for ε-differential privacy.
- [💧 Drop-off attribution](#drop-off-attribution) — Per funnel-step pair, compute the drop-off rate and the absolute number of users lost.
- [📊 Group & aggregate](#group--aggregate) — Group rows by one or more columns and compute aggregate metrics.
- [💰 LTV with discounting](#ltv-with-discounting) — Compute lifetime value per customer applying a per-period discount rate.
- [🔀 Multi-path funnel](#multi-path-funnel) — Funnel where users may complete steps in any order.
- [↕️ Pivot longer](#pivot-longer) — Stack multiple value columns into key/value rows.
- [↔️ Pivot wider](#pivot-wider) — Spread distinct values of a column into separate columns.
- [🔁 Repeat purchase rate](#repeat-purchase-rate) — Compute the share of customers that purchased more than N times within the analysis window.
- [⏱ Resample (time bucket aggregate)](#resample-time-bucket-aggregate) — Bucket rows into fixed time intervals (e.
- [📉 Retention curve](#retention-curve) — Compute the average retention rate per period offset (averaging across cohorts).
- [🎯 RFM score](#rfm-score) — Compute Recency / Frequency / Monetary scores per customer from a transaction log.
- [🪜 Step funnel](#step-funnel) — Count distinct users that reached each step of an ordered funnel.
- [⏳ Survival retention (KM lite)](#survival-retention-km-lite) — Kaplan-Meier-style survival curve for user retention.
- [🪟 Window aggregate](#window-aggregate) — Add a column computed over a rolling/cumulative window — running sum, rank, lead/lag, etc.

### 🔬 Analyze

- [⏳ ACF + PACF](#acf--pacf) — Compute autocorrelation (ACF) and partial autocorrelation (PACF) at lags 1.
- [⏳ Augmented Dickey-Fuller](#augmented-dickey-fuller) — Unit-root test.
- [⏳ Anomaly · rolling z-score](#anomaly--rolling-z-score) — Flag time-series points whose distance from a rolling mean exceeds N standard deviations.
- [📐 One-way ANOVA](#one-way-anova) — One-way ANOVA: does the mean of `value` differ across the levels of `group`? Returns F-statistic, p-value, between/within group sums-of-squares, η² (eta-squared) effect size.
- [⚖️ Bayes factor](#bayes-factor) — Compute the Bayes factor between two competing Beta-Binomial models (rate p0 vs rate p1) given observed successes + trials.
- [🎲 Bayesian linear regression](#bayesian-linear-regression) — Closed-form Bayesian linear regression with Normal prior on coefficients (ridge interpretation).
- [🎲 Bayesian best-arm probability](#bayesian-best-arm-probability) — For a binary-conversion A/B test with N variants, compute the posterior probability that each variant is the best (highest conversion rate).
- [🎲 Beta-Binomial posterior](#beta-binomial-posterior) — Conjugate Beta(α,β) prior + Binomial(n, p) likelihood → Beta(α+s, β+n-s) posterior.
- [📐 Bootstrap CI](#bootstrap-ci) — Distribution-free confidence interval around a statistic by resampling with replacement.
- [⏳ Changepoint detection](#changepoint-detection) — Find rows where the time series shifts in mean.
- [📐 Chi-squared test](#chi-squared-test) — Chi-squared test of independence between two categorical columns.
- [🎲 Conjugate Normal posterior](#conjugate-normal-posterior) — Normal-Normal conjugate posterior for the mean (known variance).
- [📊 Correlation matrix](#correlation-matrix) — Pairwise correlation between numeric columns.
- [⏳ Cox proportional hazards](#cox-proportional-hazards) — Cox PH regression via lifelines.
- [📐 Delta-method ratio CI](#delta-method-ratio-ci) — Confidence interval for a ratio metric (e.
- [📐 Difference-in-differences](#difference-in-differences) — Estimate the DiD effect via regression: outcome ~ treated * post + treated + post + controls.
- [📐 Effect size](#effect-size) — Effect-size measures for two-group comparisons.
- [📊 GLM logit](#glm-logit) — Logistic regression via statsmodels (full coefficient table with SE / z / p / 95% CI per feature).
- [📊 GLM Poisson](#glm-poisson) — Poisson regression for count outcomes via statsmodels.
- [📊 GLM probit](#glm-probit) — Probit regression via statsmodels.
- [📐 Instrumental variables (2SLS)](#instrumental-variables-2sls) — Two-stage least squares: first stage regresses the endogenous treatment on the instrument(s); second stage regresses the outcome on the predicted treatment.
- [⏳ Kaplan-Meier survival](#kaplan-meier-survival) — Estimate survival function from time-to-event + event-occurred data via lifelines KaplanMeierFitter.
- [⏳ KPSS test](#kpss-test) — Companion to ADF — tests the OPPOSITE null hypothesis.
- [📐 Two-sample KS test](#two-sample-ks-test) — Two-sample Kolmogorov-Smirnov test — do two groups have the same distribution at all? Distribution-free; works even when neither group is normal.
- [⏳ Log-rank test](#log-rank-test) — Compare survival between two or more groups (lifelines multivariate_logrank_test).
- [📐 Mann-Whitney U test](#mann-whitney-u-test) — Non-parametric two-sample test — works without assuming normality.
- [🎲 MCMC sampler (PyMC)](#mcmc-sampler-pymc) — General-case MCMC sampler via PyMC.
- [📊 Mixed-effects regression](#mixed-effects-regression) — Linear mixed-effects model via statsmodels MixedLM.
- [📐 Multiple-comparison correction](#multiple-comparison-correction) — Adjust p-values for multiple-test inflation.
- [🎯 Propensity-score matching](#propensity-score-matching) — Estimate propensity score (P(treatment=1 | covariates)) via logistic regression, then 1:1 nearest-neighbour match treated vs control.
- [📐 Regression discontinuity](#regression-discontinuity) — Sharp RD: fit two regressions (left and right of cutoff) on a running variable; the jump at the cutoff is the local-average treatment effect.
- [📏 Sample-size calculator](#sample-size-calculator) — Compute required sample size per variant for a two-sample test of proportions, given baseline rate, minimum detectable effect, alpha, and power.
- [⏯ Sequential SPRT](#sequential-sprt) — Wald's Sequential Probability Ratio Test for early stopping.
- [📐 Synthetic control](#synthetic-control) — Construct a synthetic counterfactual for a treated unit by weighted combination of control units.
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

- [📜 Column lineage report](#column-lineage-report) — Render a per-column lineage report describing each column's name, dtype, distinct count, null count, min/max (numeric), and provenance hint.
- [🧪 Confusion matrix](#confusion-matrix) — Compute the confusion-matrix counts table for a classification result.
- [✅ Data quality expectations](#data-quality-expectations) — Assert data quality rules (unique, not_null, between, in, regex_match, row_count_between, null_fraction, cardinality_between).
- [🥇 Golden row assert](#golden-row-assert) — Assert that specific rows (matched by an ID column) still have the expected values in named target columns.
- [🔒 K-anonymity check](#k-anonymity-check) — Verify that every combination of quasi-identifier values appears in at least K rows.
- [🧪 K-fold split](#k-fold-split) — Tag each row with a fold index (0 .
- [🔒 L-diversity check](#l-diversity-check) — For each equivalence class (defined by quasi-identifiers), verify the sensitive attribute has at least L distinct values.
- [🧪 Model metrics](#model-metrics) — Compute evaluation metrics by comparing actual and predicted columns.
- [📸 Pipeline snapshot test](#pipeline-snapshot-test) — Compute a content hash + row/column count snapshot for the input frame.
- [📋 Provenance certificate](#provenance-certificate) — Emit a signed-style certificate capturing the run's identity (run id, timestamp), the input frame's content hash, and the user-supplied source / pipeline metadata.
- [🧪 ROC curve](#roc-curve) — Compute (FPR, TPR, threshold) points along the ROC curve plus the AUC.
- [🚪 Schema gate](#schema-gate) — Assert that specific columns exist with expected dtypes.
- [🔒 T-closeness check](#t-closeness-check) — For each equivalence class, verify the per-class distribution of the sensitive attribute is within distance T of the global distribution (variation distance).
- [🔗 Tamper-evident log entry](#tamper-evident-log-entry) — Append a signed-chain log entry capturing this run's hash + the previous entry's hash (Merkle-style chaining).
- [🧪 Train/test split](#traintest-split) — Add a `split` column tagging each row as `train` or `test`.

### 📈 Visualize

- [📊 Box plot](#box-plot) — Render a box-whisker plot of one numeric column, optionally split by a categorical group column.
- [🎯 Bullet chart](#bullet-chart) — Edward Tufte's compact target-vs-actual chart.
- [📅 Calendar heatmap](#calendar-heatmap) — GitHub-style year-view heatmap.
- [🎯 Calibration curve](#calibration-curve) — How well-calibrated are the model's probabilities? Bins predictions by predicted_proba, then plots the actual fraction of positives in each bin against the mean predicted probability.
- [🕯 Candlestick / OHLC chart](#candlestick--ohlc-chart) — Financial candlestick chart from Open / High / Low / Close columns.
- [🎻 Chord diagram](#chord-diagram) — Circular relationship plot from a (source, target, value) edge list.
- [📊 Coefficient + CI plot](#coefficient--ci-plot) — Forest-style plot of regression / model coefficients with their confidence intervals.
- [🟦 Confusion matrix](#confusion-matrix) — Render a confusion matrix heatmap with per-cell counts and percentages.
- [🌲 Dendrogram](#dendrogram) — Hierarchical clustering tree from a vector column.
- [📈 Density plot](#density-plot) — Smooth distribution via Gaussian KDE.
- [📊 ECDF plot](#ecdf-plot) — Empirical Cumulative Distribution Function — every data point gets a y-value showing what fraction of the sample is ≤ it.
- [🖼 Export to image](#export-to-image) — Render the data as a PNG/SVG via matplotlib + seaborn.
- [🗺 Export to map](#export-to-map) — Render geographic data on an interactive world map.
- [📈 Funnel chart](#funnel-chart) — Sequential conversion-funnel visualisation.
- [📈 Cumulative gains chart](#cumulative-gains-chart) — Y-axis: cumulative percent of positives captured.
- [🌡 Gauge chart](#gauge-chart) — Speedometer-style single-metric gauge.
- [🪞 Horizon chart](#horizon-chart) — Compact small-multiples view for many time series.
- [🔢 KPI card](#kpi-card) — Render one or more big-number cards with a label, the headline value, and optional comparison-vs-baseline percent.
- [📊 Lift chart](#lift-chart) — How much better than random is the model at each cumulative percentile? Y-axis: ratio of (positives captured by top X%) / (random baseline).
- [🟦 Marimekko / mosaic](#marimekko--mosaic) — Two-dimensional part-to-whole.
- [🕸 Network graph](#network-graph) — Force-directed network plot from a (source, target, value) edge list.
- [📈 Pareto chart](#pareto-chart) — Sorted bar chart of category values + cumulative-percentage line on a secondary axis.
- [🥧 Pie / donut chart](#pie--donut-chart) — Classic part-to-whole pie or donut.
- [📉 Precision-Recall curve](#precision-recall-curve) — Render a Precision-Recall curve with average-precision (AP) reported in the legend.
- [📊 Q-Q plot (normality)](#q-q-plot-normality) — Quantile-Quantile plot comparing the column's quantiles to a normal distribution.
- [🌄 Ridge plot](#ridge-plot) — Stacked density plots — one row per category, KDE curve per row, all sharing the same x axis.
- [📈 ROC + AUC curve](#roc--auc-curve) — Render a Receiver Operating Characteristic curve with the AUC reported in the legend.
- [🌊 Sankey flow](#sankey-flow) — Render data-flow Sankey from (source, target, value) edges.
- [🌊 Stream graph](#stream-graph) — Stacked area chart with center-baselined symmetry (the classic 'wiggle' algorithm).
- [🟫 Treemap](#treemap) — Each row becomes a rectangle whose area is proportional to the value column.
- [📊 Violin plot](#violin-plot) — Violin plot — KDE distribution + box-plot hybrid.
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


### 📐 Parse geometry

**ID:** `parse_geometry` · **Version:** `1.0.0`

Parse a column of geometry strings (WKT or GeoJSON) into a typed geometry column. Adds three columns: geometry (a serialised shapely geometry), geometry_type (Point / LineString / Polygon / MultiPolygon / …), and geometry_valid (boolean). Required upstream of spatial_join when your input is text-encoded GIS data.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:geo_pro`

Tags: `geometry` `wkt` `geojson` `spatial` `geo` `parse`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `sourceColumn` | column_ref | ✓ | — | Source column (text) |
| `format` | enum | ✓ | `auto` | auto: detect per row (look for 'POINT(' / 'POLYGON(' / etc. for WKT, leading '{' for GeoJSON). wkt: assume Well-Known Text. geojson: assume GeoJSON Feature / Geometry strings. |
| `outputPrefix` | string |  | `` | Optional prefix prepended to the three output column names. Use to keep multiple parsed-geometry sets distinct. |


### 📐 Parse geometry

**ID:** `parse_geometry` · **Version:** `1.0.0`

Parse a column of geometry strings (WKT or GeoJSON) into a typed geometry column. Adds three columns: geometry (a serialised shapely geometry), geometry_type (Point / LineString / Polygon / MultiPolygon / …), and geometry_valid (boolean). Required upstream of spatial_join when your input is text-encoded GIS data.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:geospatial_pack`

Tags: `geometry` `wkt` `geojson` `spatial` `geo` `parse`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `sourceColumn` | column_ref | ✓ | — | Source column (text) |
| `format` | enum | ✓ | `auto` | auto: detect per row (look for 'POINT(' / 'POLYGON(' / etc. for WKT, leading '{' for GeoJSON). wkt: assume Well-Known Text. geojson: assume GeoJSON Feature / Geometry strings. |
| `outputPrefix` | string |  | `` | Optional prefix prepended to the three output column names. Use to keep multiple parsed-geometry sets distinct. |


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


### ⬇ CIC decimation

**ID:** `downsample_cic` · **Version:** `1.0.0`

Cascaded-Integrator-Comb decimation filter — efficient downsampling with built-in low-pass filtering. Standard in DSP / sensor pipelines that need to reduce sample rate by a large integer factor.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:iot_sensor_pack`

Tags: `iot` `cic` `decimation` `downsample`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `valueColumn` | column_ref | ✓ | — | Value column |
| `orderColumn` | column_ref | ✓ | — | Time/order column |
| `decimationFactor` | integer |  | `10` | Decimation factor (R) |
| `stages` | integer |  | `3` | Number of CIC stages (N) |


### 🏥 HIPAA Safe-Harbor de-identify

**ID:** `hipaa_deidentify` · **Version:** `1.0.0`

Apply HIPAA Safe-Harbor de-identification: drop direct identifiers (name, SSN, MRN, address, phone, email, dates of service if not year-only), generalize ZIP to 3-digit, generalize ages > 89.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:healthcare_pack`

Tags: `healthcare` `hipaa` `privacy` `clean`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `dropColumns` | column_refs |  | — | Direct-identifier columns to drop |
| `zipColumn` | column_ref |  | — | ZIP column (truncated to 3 digits) |
| `ageColumn` | column_ref |  | — | Age column (capped to 90+) |


### ↔️ Forward / backward fill

**ID:** `impute_forward_backward` · **Version:** `1.0.0`

Fill nulls by carrying the previous (forward fill) or next (backward fill) value. Most useful for time-series where missing readings should inherit from the prior reading. Optional sort + group preserves per-entity locality.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:imputation_pack`

Tags: `imputation` `ffill` `bfill` `time-series` `clean`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `columns` | column_refs | ✓ | — | Columns to fill |
| `direction` | enum |  | `forward` | Direction |
| `sortColumn` | column_ref |  | — | Sort rows by this column (e.g. date) before filling so 'forward' = chronological. |
| `groupColumn` | column_ref |  | — | Fill within each group separately (e.g. per device, per customer). |


### 📈 Interpolate nulls

**ID:** `impute_interpolation` · **Version:** `1.0.0`

Linear or spline interpolation between known values. Numeric columns only. Most useful for time series where missing readings should follow the trend established by surrounding observations.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:imputation_pack`

Tags: `imputation` `interpolation` `time-series` `clean`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `columns` | column_refs | ✓ | — | Numeric columns to interpolate |
| `method` | enum |  | `linear` | linear: connect known endpoints with a straight line. nearest: copy the nearer neighbour. |
| `sortColumn` | column_ref |  | — | Sort by this column before interpolating (e.g. timestamp). |


### 🧬 K-Nearest-Neighbours imputation

**ID:** `impute_knn` · **Version:** `1.0.0`

Fill nulls in numeric columns by averaging the K nearest non-null rows (Euclidean distance over the chosen feature columns). Preserves multivariate structure better than per-column statistics.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:imputation_pack`

Tags: `imputation` `knn` `missing` `multivariate` `clean`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `columns` | column_refs | ✓ | — | Numeric columns to impute (and use as features) |
| `k` | integer |  | `5` | K |


### 🩹 Impute mean / median / mode

**ID:** `impute_mean_median_mode` · **Version:** `1.0.0`

Fill nulls in selected columns with the per-column statistic (mean, median, or mode). Default behaviour: numeric columns use median, categorical/string columns use mode.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:imputation_pack`

Tags: `imputation` `missing` `fill` `clean`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `columns` | column_refs | ✓ | — | Columns to impute |
| `strategy` | enum |  | `auto` | auto = numeric→median, non-numeric→mode. |


### 🔁 MICE imputation (chained equations)

**ID:** `impute_mice` · **Version:** `1.0.0`

Multiple Imputation by Chained Equations — fits a regression for each column on the others, fills nulls with predictions, repeats until convergence. The most rigorous standard imputation strategy in research / clinical analytics.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:imputation_pack`

Tags: `imputation` `mice` `iterative` `missing` `clean`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `columns` | column_refs | ✓ | — | Numeric columns |
| `maxIter` | integer |  | `10` | Max iterations |


### 🔏 PII redact

**ID:** `pii_redact` · **Version:** `1.0.0`

Replace pattern matches in text columns with a placeholder. Built-in patterns: email, US phone, US SSN, credit card. Use as a quick sanitisation before exporting logs / freeform text.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:privacy_pack`

Tags: `privacy` `pii` `redact` `clean`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `columns` | column_refs | ✓ | — | Text columns |
| `patterns` | string |  | `email,phone,ssn,credit_card` | Patterns (comma-separated: email,phone,ssn,credit_card) |
| `replacement` | string |  | `[REDACTED]` | Replacement |


### 🎭 Seeded pseudonymization

**ID:** `pseudonymize_seeded` · **Version:** `1.0.0`

Replace identifying values with deterministic but opaque tokens (HMAC-SHA256 with a secret seed). Same input value always maps to the same token; without the seed, the mapping cannot be reversed.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:privacy_pack`

Tags: `privacy` `pseudonymize` `hmac` `clean`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `columns` | column_refs | ✓ | — | Columns to pseudonymize |
| `seed` | string | ✓ | — | Keep this secret; rotate when re-issuing pseudonyms. |
| `prefix` | string |  | `px_` | Token prefix |


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


### 🧂 Salted hash

**ID:** `salt_hash` · **Version:** `1.0.0`

Hash columns with a per-column salt + global pepper. SHA256-based. Useful for joining datasets across systems without sharing raw IDs (each system applies the same salt+pepper to get matching hashes).

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:privacy_pack`

Tags: `privacy` `hash` `salt` `clean`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `columns` | column_refs | ✓ | — | Columns to hash |
| `salt` | string | ✓ | — | Per-column-or-global salt; document elsewhere so collaborators can reproduce. |
| `truncate` | integer |  | `16` | Hex truncate length |


### 🎯 Cluster sample

**ID:** `sample_cluster` · **Version:** `1.0.0`

Sample whole groups (clusters) at random rather than individual rows. Useful when units of analysis come in groups (households, classes, stores) and you need them intact.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: preserves

📦 Source: `pack:sampling_pro`

Tags: `sampling` `cluster` `statistical`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `clusterColumn` | column_ref | ✓ | — | Cluster column |
| `numClusters` | integer |  | `10` | Number of clusters to sample |
| `seed` | integer |  | `42` | Random seed |


### 💧 Reservoir sample

**ID:** `sample_reservoir` · **Version:** `1.0.0`

Single-pass uniform sample of N rows. Useful when streaming data through DIG — you only need to see each row once. Returns exactly N rows for inputs ≥ N.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: preserves

📦 Source: `pack:sampling_pro`

Tags: `sampling` `reservoir` `streaming`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `sampleSize` | integer |  | `1000` | Sample size |
| `seed` | integer |  | `42` | Random seed |


### 🎯 Stratified sample

**ID:** `sample_stratified` · **Version:** `1.0.0`

Sample N rows preserving the proportion of each value in the strata column. Each stratum contributes (n_total × stratum_share) rows.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: preserves

📦 Source: `pack:sampling_pro`

Tags: `sampling` `stratified` `statistical`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `strataColumn` | column_ref | ✓ | — | Strata column |
| `sampleSize` | integer |  | `1000` | Total sample size |
| `seed` | integer |  | `42` | Random seed |


### 📐 Systematic sample

**ID:** `sample_systematic` · **Version:** `1.0.0`

Take every Kth row after a random start. Equivalent quality to simple random sampling for unordered data; preserves index spacing for ordered data.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: preserves

📦 Source: `pack:sampling_pro`

Tags: `sampling` `systematic`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `sampleSize` | integer |  | `1000` | Sample size |
| `seed` | integer |  | `42` | Random seed |


### ⚖️ Weighted sample

**ID:** `sample_weighted` · **Version:** `1.0.0`

Sample N rows where each row's selection probability is proportional to a weight column. Used for survey reweighting and importance sampling.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: preserves

📦 Source: `pack:sampling_pro`

Tags: `sampling` `weighted` `statistical`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `weightColumn` | column_ref | ✓ | — | Weight column |
| `sampleSize` | integer |  | `1000` | Sample size |
| `withReplacement` | boolean |  | `False` | With replacement |
| `seed` | integer |  | `42` | Random seed |


### 📡 Sensor resample

**ID:** `sensor_resample_regular` · **Version:** `1.0.0`

Resample irregularly-spaced sensor readings to a regular time grid via linear interpolation. Per-sensor when grouped.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_grow · schema: rebuilds

📦 Source: `pack:iot_sensor_pack`

Tags: `iot` `sensor` `resample`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `timestampColumn` | column_ref | ✓ | — | Timestamp column |
| `valueColumn` | column_ref | ✓ | — | Value column |
| `sensorColumn` | column_ref |  | — | Sensor ID column (optional) |
| `intervalSeconds` | number |  | `60.0` | Output interval (seconds) |


### 📈 SMOTE oversample

**ID:** `smote_oversample` · **Version:** `1.0.0`

Synthetic Minority Oversampling — synthesises new minority-class rows by interpolating between existing nearest-neighbours. Balances classification training data without duplicating rows.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_grow · schema: preserves

📦 Source: `pack:sampling_pro`

Tags: `sampling` `smote` `imbalanced` `ml`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `targetColumn` | column_ref | ✓ | — | Target (class) column |
| `featureColumns` | column_refs | ✓ | — | Feature columns (numeric) |
| `k` | integer |  | `5` | K nearest neighbours |
| `seed` | integer |  | `42` | Random seed |


### 📉 Undersample majority

**ID:** `undersample` · **Version:** `1.0.0`

Randomly drop rows from the majority class until classes are balanced (or to a target ratio). Faster + simpler than SMOTE when you have plenty of majority-class data.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: preserves

📦 Source: `pack:sampling_pro`

Tags: `sampling` `imbalanced` `undersample` `ml`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `targetColumn` | column_ref | ✓ | — | Target (class) column |
| `ratio` | number |  | `1.0` | Majority:minority ratio (1.0 = balanced) |
| `seed` | integer |  | `42` | Random seed |


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


### 📝 BERTopic

**ID:** `bertopic_topics` · **Version:** `1.0.0`

Modern transformer-based topic modelling via BERTopic (sentence-transformers + UMAP + HDBSCAN). Returns per-doc topic + per-topic representative terms. Heavy dependency — see INTERNAL_NOTES.md if install fails.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:text_nlp_pack`

Tags: `nlp` `bertopic` `topics` `transformer`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `textColumn` | column_ref | ✓ | — | Text column |
| `minTopicSize` | integer |  | `10` | Min docs per topic |


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


### 🚪 Churn lite

**ID:** `churn_lite` · **Version:** `1.0.0`

Lightweight churn flag based on inactivity. A customer is marked churned if their last transaction is older than `windowDays` from the as-of date. Use as a fast labelling pass before training a real churn model.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:rfm_pack`

Tags: `churn` `rfm` `marketing` `label`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `customerColumn` | column_ref | ✓ | — | Customer ID column |
| `dateColumn` | column_ref | ✓ | — | Transaction date column |
| `windowDays` | integer |  | `90` | Inactivity window (days) |
| `asOfDate` | string |  | — | As-of date (YYYY-MM-DD; today if blank) |


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


### 🏥 CPT lookup

**ID:** `cpt_lookup` · **Version:** `1.0.0`

Look up CPT procedure codes against a bundled mini reference table. Adds cpt_description + service_category. Mini bundle covers ~30 most-common procedure codes.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:healthcare_pack`

Tags: `healthcare` `cpt` `lookup`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `codeColumn` | column_ref | ✓ | — | CPT code column |


### 🧭 CRS / projection transform

**ID:** `crs_transform` · **Version:** `1.0.0`

Reproject coordinates between coordinate reference systems via pyproj. Convert lat/lon (EPSG:4326) into UTM zones, State Plane, Web Mercator, or any other EPSG code. Use when downstream tools expect projected coordinates (e.g. metres) or for accurate area / distance work in a specific region. Complements the built-in convert_coordinates which only handles WGS84↔ECEF cartesian.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:geo_pro`

Tags: `geo` `crs` `projection` `pyproj` `epsg` `reproject`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `xColumn` | column_ref | ✓ | — | X / longitude column |
| `yColumn` | column_ref | ✓ | — | Y / latitude column |
| `sourceCrs` | string | ✓ | `EPSG:4326` | Any pyproj-recognised string: EPSG code (EPSG:4326 = WGS84 lat/lon), PROJ string, or WKT. EPSG:4326 is the default for lat/lon data. |
| `targetCrs` | string | ✓ | `EPSG:3857` | Any pyproj-recognised CRS. Common targets: EPSG:3857 (Web Mercator, used by web maps), EPSG:32633 (UTM zone 33N), EPSG:2154 (Lambert-93 for France), EPSG:27700 (British National Grid). |
| `outputXColumn` | string | ✓ | `x_proj` | Output X column name |
| `outputYColumn` | string | ✓ | `y_proj` | Output Y column name |


### 🧭 CRS / projection transform

**ID:** `crs_transform` · **Version:** `1.0.0`

Reproject coordinates between coordinate reference systems via pyproj. Convert lat/lon (EPSG:4326) into UTM zones, State Plane, Web Mercator, or any other EPSG code. Use when downstream tools expect projected coordinates (e.g. metres) or for accurate area / distance work in a specific region. Complements the built-in convert_coordinates which only handles WGS84↔ECEF cartesian.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:geospatial_pack`

Tags: `geo` `crs` `projection` `pyproj` `epsg` `reproject`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `xColumn` | column_ref | ✓ | — | X / longitude column |
| `yColumn` | column_ref | ✓ | — | Y / latitude column |
| `sourceCrs` | string | ✓ | `EPSG:4326` | Any pyproj-recognised string: EPSG code (EPSG:4326 = WGS84 lat/lon), PROJ string, or WKT. EPSG:4326 is the default for lat/lon data. |
| `targetCrs` | string | ✓ | `EPSG:3857` | Any pyproj-recognised CRS. Common targets: EPSG:3857 (Web Mercator, used by web maps), EPSG:32633 (UTM zone 33N), EPSG:2154 (Lambert-93 for France), EPSG:27700 (British National Grid). |
| `outputXColumn` | string | ✓ | `x_proj` | Output X column name |
| `outputYColumn` | string | ✓ | `y_proj` | Output Y column name |


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


### 🌐 Geohash / H3 cell

**ID:** `geohash_cell` · **Version:** `1.0.0`

Add a column with the spatial-index cell that contains each lat/lon point. Supports the geohash and H3 indexing systems. Use as a fast group_by key for spatial aggregation, or to bucket points into discrete cells before clustering / heatmap rendering.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:geo_pro`

Tags: `geo` `geohash` `h3` `spatial-index` `bucket` `derive`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `latColumn` | column_ref | ✓ | — | Latitude column |
| `lonColumn` | column_ref | ✓ | — | Longitude column |
| `system` | enum | ✓ | `h3` | geohash: 32-character base-32 string. Cell size shrinks per character. h3: Uber's hexagonal grid; cells are roughly equal-area which is better for heatmaps. Both are widely supported by downstream tooling. |
| `precision` | integer | ✓ | `7` | geohash: 1-12 (1 ≈ 5000km, 7 ≈ 76m, 12 ≈ 3.7cm). h3: 0-15 (0 ≈ continent-scale, 7 ≈ 1.2km hexes, 12 ≈ 5m hexes). Higher = more granular = more cells. |
| `outputColumn` | string | ✓ | `cell` | Output column name |


### 🌐 Geohash / H3 cell

**ID:** `geohash_cell` · **Version:** `1.0.0`

Add a column with the spatial-index cell that contains each lat/lon point. Supports the geohash and H3 indexing systems. Use as a fast group_by key for spatial aggregation, or to bucket points into discrete cells before clustering / heatmap rendering.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:geospatial_pack`

Tags: `geo` `geohash` `h3` `spatial-index` `bucket` `derive`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `latColumn` | column_ref | ✓ | — | Latitude column |
| `lonColumn` | column_ref | ✓ | — | Longitude column |
| `system` | enum | ✓ | `h3` | geohash: 32-character base-32 string. Cell size shrinks per character. h3: Uber's hexagonal grid; cells are roughly equal-area which is better for heatmaps. Both are widely supported by downstream tooling. |
| `precision` | integer | ✓ | `7` | geohash: 1-12 (1 ≈ 5000km, 7 ≈ 76m, 12 ≈ 3.7cm). h3: 0-15 (0 ≈ continent-scale, 7 ≈ 1.2km hexes, 12 ≈ 5m hexes). Higher = more granular = more cells. |
| `outputColumn` | string | ✓ | `cell` | Output column name |


### 🏥 ICD-10 lookup

**ID:** `icd10_lookup` · **Version:** `1.0.0`

Look up ICD-10 diagnosis codes against a bundled mini reference table. Adds icd_description + chapter columns. The bundled table covers ~50 most-common codes; for full coverage, mount a complete ICD-10 file as a dataset and join.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:healthcare_pack`

Tags: `healthcare` `icd10` `lookup`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `codeColumn` | column_ref | ✓ | — | ICD-10 code column |


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


### 📝 RAKE / YAKE keywords

**ID:** `keyword_rake_yake` · **Version:** `1.0.0`

Unsupervised keyword extraction. RAKE: Rapid Automatic Keyword Extraction (co-occurrence-based). YAKE: Yet Another Keyword Extractor (statistical). Returns top-K keywords per document.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:text_nlp_pack`

Tags: `nlp` `keywords` `rake` `yake`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `textColumn` | column_ref | ✓ | — | Text column |
| `algorithm` | enum |  | `rake` | Algorithm |
| `topK` | integer |  | `5` | Top-K keywords |


### ⏪ Lag features

**ID:** `lag_features` · **Version:** `1.0.0`

Add lag(N) versions of selected columns. Each new column is named <col>_lag<N>. Use as the building block for time-series ML features.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:feature_engineering`

Tags: `feature` `lag` `time-series` `ml`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `columns` | column_refs | ✓ | — | Columns to lag |
| `lags` | string | ✓ | `1` | Lag offsets (comma-separated, e.g. 1,7,30) |
| `sortColumn` | column_ref |  | — | Sort column |
| `groupColumn` | column_ref |  | — | Group column (optional) |


### 📝 Language detect

**ID:** `language_detect` · **Version:** `1.0.0`

Detect language of each text row via langdetect (Google's language-detection lib port). Returns ISO-639 code + confidence.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:text_nlp_pack`

Tags: `nlp` `language` `detect` `langdetect`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `textColumn` | column_ref | ✓ | — | Text column |


### 📝 LDA topic modelling

**ID:** `lda_topics` · **Version:** `1.0.0`

Latent Dirichlet Allocation via scikit-learn. Returns per-document dominant topic + per-topic top terms.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:text_nlp_pack`

Tags: `nlp` `lda` `topics`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `textColumn` | column_ref | ✓ | — | Text column |
| `nTopics` | integer |  | `5` | Number of topics |
| `seed` | integer |  | `42` | Random seed |


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


### 🔀 Multi-sensor fusion

**ID:** `multi_sensor_fusion` · **Version:** `1.0.0`

Combine readings from multiple sensors at the same timestamp via weighted average. The fusion column represents an estimate that's more accurate than any single sensor.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:iot_sensor_pack`

Tags: `iot` `fusion` `sensor`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `sensorColumns` | column_refs | ✓ | — | Sensor reading columns |
| `weights` | string |  | — | e.g. 0.5,0.3,0.2 — must match the sensor column count. |
| `outputColumn` | string |  | `fused` | Output column |


### 📝 NER (spaCy)

**ID:** `ner_spacy` · **Version:** `1.0.0`

Extract named entities (PERSON, ORG, GPE, DATE, MONEY, etc.) from a text column via spaCy's en_core_web_sm model. Heavy dependency — see INTERNAL_NOTES.md if install fails.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:text_nlp_pack`

Tags: `nlp` `ner` `spacy`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `textColumn` | column_ref | ✓ | — | Text column |


### ➗ Polynomial features

**ID:** `polynomial_features` · **Version:** `1.0.0`

Add x², x³, x·y interaction features for the chosen numeric columns. Useful for linear models that need to capture curvature.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:feature_engineering`

Tags: `feature` `polynomial` `ml`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `columns` | column_refs | ✓ | — | Numeric columns |
| `degree` | integer |  | `2` | Max degree |
| `includeInteractions` | boolean |  | `True` | Include cross-term interactions |


### 📍 Reverse geocode

**ID:** `reverse_geocode` · **Version:** `1.0.0`

Resolve lat/lon points to country / state / city via a bundled lookup table (no external network call). Uses the natural-earth admin-0 + admin-1 polygon set; resolution is country + first-level subdivision (state, province, prefecture). For street-level reverse geocoding, an external service is required.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:geospatial_pack`

Tags: `geo` `reverse-geocode` `country` `state` `lookup`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `latColumn` | column_ref | ✓ | — | Latitude column |
| `lonColumn` | column_ref | ✓ | — | Longitude column |
| `level` | enum |  | `country` | country: ISO-A3 country code + name. state: country + first-level subdivision (US state, Canadian province, German Land, etc.). |
| `countryColumn` | string |  | `country` | Output country column name |
| `stateColumn` | string |  | `state` | Output state/region column name |


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


### 📐 Min-max scaler

**ID:** `scale_minmax` · **Version:** `1.0.0`

Rescale each column to [0, 1] (or any user-specified range).

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:feature_engineering`

Tags: `feature` `scaler` `minmax` `ml`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `columns` | column_refs | ✓ | — | Numeric columns |
| `rangeMin` | number |  | `0.0` | Output range min |
| `rangeMax` | number |  | `1.0` | Output range max |
| `suffix` | string |  | `_minmax` | Output suffix |


### 📐 Robust scaler

**ID:** `scale_robust` · **Version:** `1.0.0`

Subtract median, divide by IQR. Robust to outliers (vs. standard z-score which is dragged by extremes).

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:feature_engineering`

Tags: `feature` `scaler` `robust` `ml`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `columns` | column_refs | ✓ | — | Numeric columns |
| `suffix` | string |  | `_robust` | Output suffix |


### 📐 Standard scaler (z-score)

**ID:** `scale_standard` · **Version:** `1.0.0`

Subtract mean, divide by standard deviation. Per-column. Standard ML preprocessing for distance-based models.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:feature_engineering`

Tags: `feature` `scaler` `zscore` `ml`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `columns` | column_refs | ✓ | — | Numeric columns |
| `suffix` | string |  | `_scaled` | Output suffix |


### 📝 Sentiment (VADER)

**ID:** `sentiment_vader` · **Version:** `1.0.0`

Compute VADER sentiment scores per text row. Adds compound, positive, negative, neutral columns. Designed for social-media / short-text content.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:text_nlp_pack`

Tags: `nlp` `sentiment` `vader`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `textColumn` | column_ref | ✓ | — | Text column |


### 📈 Stream drift detector

**ID:** `stream_drift_detect` · **Version:** `1.0.0`

Page-Hinkley change-point detector for streaming sensor values. Flags rows where the cumulative deviation from the running mean exceeds a threshold.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:iot_sensor_pack`

Tags: `iot` `drift` `page-hinkley` `streaming`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `valueColumn` | column_ref | ✓ | — | Value column |
| `orderColumn` | column_ref | ✓ | — | Time/order column |
| `threshold` | number |  | `50.0` | Detection threshold |
| `delta` | number |  | `0.005` | Allowable magnitude |


### 🎯 Target encoding

**ID:** `target_encoding` · **Version:** `1.0.0`

Replace each category with the mean of the target variable for that category. Optional smoothing blends per-group mean toward the global mean to control overfitting on rare categories.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:feature_engineering`

Tags: `feature` `encoding` `target` `ml`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `categoryColumn` | column_ref | ✓ | — | Category column |
| `targetColumn` | column_ref | ✓ | — | Target column |
| `smoothing` | number |  | `10.0` | Smoothing |
| `outputColumn` | string |  | `target_encoded` | Output column |


### 📝 TF-IDF

**ID:** `tfidf` · **Version:** `1.0.0`

Compute TF-IDF features for a text column. Returns top-K terms per document by TF-IDF weight.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:text_nlp_pack`

Tags: `nlp` `tfidf`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `textColumn` | column_ref | ✓ | — | Text column |
| `topK` | integer |  | `5` | Top-K terms per row |
| `maxFeatures` | integer |  | `1000` | Max vocabulary size |


### ⏱ Time to convert

**ID:** `time_to_convert` · **Version:** `1.0.0`

Per-user time elapsed between the first and final funnel step. Output: per-user record + summary distribution.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:funnel_pack`

Tags: `funnel` `time` `conversion`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `userColumn` | column_ref | ✓ | — | User ID |
| `timestampColumn` | column_ref | ✓ | — | Event timestamp |
| `eventColumn` | column_ref | ✓ | — | Event name |
| `firstEvent` | string | ✓ | — | First event |
| `lastEvent` | string | ✓ | — | Last event |


### 📝 Tokenize

**ID:** `tokenize` · **Version:** `1.0.0`

Split text into tokens. Modes: word (whitespace + punctuation strip), sentence (regex), or n-gram (sliding window of size N).

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:text_nlp_pack`

Tags: `nlp` `tokenize`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `textColumn` | column_ref | ✓ | — | Text column |
| `mode` | enum |  | `word` | Mode |
| `ngramSize` | integer |  | `2` | N for n-gram mode |
| `lowercase` | boolean |  | `True` | Lowercase |
| `outputColumn` | string |  | `tokens` | Output column |


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


### 🌍 Vincenty distance

**ID:** `vincenty_distance` · **Version:** `1.0.0`

Compute geodesic distance (in metres) between two lat/lon points using Vincenty's formula on the WGS84 ellipsoid. More accurate than Haversine for long distances and near the poles, where Haversine's spherical-earth assumption introduces error up to ~0.5%. Use for aviation, maritime, and continent-scale distance work; Haversine (the built-in geo_distance step) is fine for sub-100 km distances.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:geo_pro`

Tags: `geo` `distance` `vincenty` `geodesic` `wgs84` `derive`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `lat1Column` | column_ref | ✓ | — | Point A latitude |
| `lon1Column` | column_ref | ✓ | — | Point A longitude |
| `lat2Column` | column_ref | ✓ | — | Point B latitude |
| `lon2Column` | column_ref | ✓ | — | Point B longitude |
| `outputColumn` | string | ✓ | `distance_m` | Output column name |
| `outputBearing` | boolean |  | `False` | Adds a second column with the initial heading from A to B (0 = north, 90 = east). |


### 🌍 Vincenty distance

**ID:** `vincenty_distance` · **Version:** `1.0.0`

Compute geodesic distance (in metres) between two lat/lon points using Vincenty's formula on the WGS84 ellipsoid. More accurate than Haversine for long distances and near the poles, where Haversine's spherical-earth assumption introduces error up to ~0.5%. Use for aviation, maritime, and continent-scale distance work; Haversine (the built-in geo_distance step) is fine for sub-100 km distances.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:geospatial_pack`

Tags: `geo` `distance` `vincenty` `geodesic` `wgs84` `derive`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `lat1Column` | column_ref | ✓ | — | Point A latitude |
| `lon1Column` | column_ref | ✓ | — | Point A longitude |
| `lat2Column` | column_ref | ✓ | — | Point B latitude |
| `lon2Column` | column_ref | ✓ | — | Point B longitude |
| `outputColumn` | string | ✓ | `distance_m` | Output column name |
| `outputBearing` | boolean |  | `False` | Adds a second column with the initial heading from A to B (0 = north, 90 = east). |


### 📊 Weight-of-Evidence + IV

**ID:** `woe_iv` · **Version:** `1.0.0`

Compute Weight of Evidence per category + the column-level Information Value (IV). Standard credit-risk feature ranking technique. WoE = ln(P(category | good) / P(category | bad)).

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:feature_engineering`

Tags: `feature` `woe` `iv` `credit` `ml`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `categoryColumn` | column_ref | ✓ | — | Category column |
| `targetColumn` | column_ref | ✓ | — | Binary target column |
| `outputColumn` | string |  | `woe` | WoE output column |


### 📊 Yeo-Johnson power transform

**ID:** `yeo_johnson` · **Version:** `1.0.0`

Power transform that makes data more Gaussian-like. Handles negative values (unlike Box-Cox). Useful before linear models when features are skewed.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:feature_engineering`

Tags: `feature` `transform` `gaussian` `ml`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `columns` | column_refs | ✓ | — | Numeric columns |
| `suffix` | string |  | `_yj` | Output suffix |


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


### 🗺 Map-match (snap to nearest reference)

**ID:** `map_match` · **Version:** `1.0.0`

Snap each lat/lon point to the nearest point in a reference table (a separate dataset of named known locations — bus stops, stations, sensor sites, store fronts, registered addresses). Returns the matched reference's id + label + the great-circle distance in metres. Lightweight alternative to road-network map-matching for cases where a point cloud of known locations is enough.

🛠 engine: `polars` · ⬅️ inputs: 2 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:geospatial_pack`

Tags: `geo` `map-match` `snap` `join` `nearest`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `latColumn` | column_ref | ✓ | — | Latitude column (input) |
| `lonColumn` | column_ref | ✓ | — | Longitude column (input) |
| `refLatColumn` | column_ref | ✓ | — | Reference latitude column |
| `refLonColumn` | column_ref | ✓ | — | Reference longitude column |
| `refIdColumn` | column_ref | ✓ | — | Reference ID / name column |
| `matchedIdColumn` | string |  | `matched_id` | Matched ID output column |
| `matchedDistanceColumn` | string |  | `matched_distance_m` | Matched distance (m) column |


### 🔗 Spatial join

**ID:** `spatial_join` · **Version:** `1.0.0`

Join two inputs on a spatial predicate. Each row from the left is matched with rows from the right whose geometry satisfies the predicate (within / contains / intersects / touches). Use parse_geometry first to convert WKT or GeoJSON text into the geometry columns.

🛠 engine: `polars` · ⬅️ inputs: 2 · ➡️ outputs: 1 · rows: may_grow · schema: rebuilds

📦 Source: `pack:geo_pro`

Tags: `spatial` `join` `point-in-polygon` `geo` `geometry` `intersect`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `leftGeometry` | column_ref | ✓ | — | Left geometry column |
| `rightGeometry` | column_ref | ✓ | — | Right geometry column |
| `predicate` | enum | ✓ | `within` | within: left geometry inside right (point-in-polygon). contains: right inside left. intersects: any overlap. touches: share a boundary but no interior. covers / covered_by: like contains/within but boundary points count as inside. |
| `joinType` | enum | ✓ | `inner` | inner: only emit rows where the predicate matched. left_outer: keep every left row; right columns are NULL when no match. |
| `rightSuffix` | string |  | `_r` | Suffix for right-side column collisions |


### 🔗 Spatial join

**ID:** `spatial_join` · **Version:** `1.0.0`

Join two inputs on a spatial predicate. Each row from the left is matched with rows from the right whose geometry satisfies the predicate (within / contains / intersects / touches). Use parse_geometry first to convert WKT or GeoJSON text into the geometry columns.

🛠 engine: `polars` · ⬅️ inputs: 2 · ➡️ outputs: 1 · rows: may_grow · schema: rebuilds

📦 Source: `pack:geospatial_pack`

Tags: `spatial` `join` `point-in-polygon` `geo` `geometry` `intersect`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `leftGeometry` | column_ref | ✓ | — | Left geometry column |
| `rightGeometry` | column_ref | ✓ | — | Right geometry column |
| `predicate` | enum | ✓ | `within` | within: left geometry inside right (point-in-polygon). contains: right inside left. intersects: any overlap. touches: share a boundary but no interior. covers / covered_by: like contains/within but boundary points count as inside. |
| `joinType` | enum | ✓ | `inner` | inner: only emit rows where the predicate matched. left_outer: keep every left row; right columns are NULL when no match. |
| `rightSuffix` | string |  | `_r` | Suffix for right-side column collisions |


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

### 🥇 First-touch attribution

**ID:** `attribution_first_touch` · **Version:** `1.0.0`

Assign 100% of conversion credit to each user's first touch (chronologically first row in their journey).

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:marketing_attribution`

Tags: `attribution` `marketing`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `userColumn` | column_ref | ✓ | — | User ID |
| `channelColumn` | column_ref | ✓ | — | Channel |
| `timestampColumn` | column_ref | ✓ | — | Touch timestamp |
| `convertedColumn` | column_ref | ✓ | — | Converted (0/1) column |


### 🥇 Last-touch attribution

**ID:** `attribution_last_touch` · **Version:** `1.0.0`

Assign 100% of conversion credit to each user's last touch before conversion (default in many ad platforms).

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:marketing_attribution`

Tags: `attribution` `marketing`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `userColumn` | column_ref | ✓ | — | User ID |
| `channelColumn` | column_ref | ✓ | — | Channel |
| `timestampColumn` | column_ref | ✓ | — | Touch timestamp |
| `convertedColumn` | column_ref | ✓ | — | Converted (0/1) |


### 📏 Linear attribution

**ID:** `attribution_linear` · **Version:** `1.0.0`

Distribute conversion credit equally across all touches in each user's journey. Credit per touch = 1 / (number of touches).

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:marketing_attribution`

Tags: `attribution` `marketing` `linear`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `userColumn` | column_ref | ✓ | — | User ID |
| `channelColumn` | column_ref | ✓ | — | Channel |
| `convertedColumn` | column_ref | ✓ | — | Converted (0/1) |


### 🔗 Markov-chain attribution

**ID:** `attribution_markov` · **Version:** `1.0.0`

Build a transition matrix between channels (start → channels → conversion / null) and compute each channel's removal effect — its contribution to total conversions if removed from the graph. The data-driven attribution baseline.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:marketing_attribution`

Tags: `attribution` `markov` `removal-effect` `data-driven`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `userColumn` | column_ref | ✓ | — | User ID |
| `channelColumn` | column_ref | ✓ | — | Channel |
| `timestampColumn` | column_ref | ✓ | — | Touch timestamp |
| `convertedColumn` | column_ref | ✓ | — | Converted (0/1) |


### 🎯 Position-based attribution (U-shape)

**ID:** `attribution_position_based` · **Version:** `1.0.0`

40% credit to first touch, 40% to last touch, 20% split equally among middle touches. The classic U-shape model when both intro and conversion are weighted heavily.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:marketing_attribution`

Tags: `attribution` `u-shape` `marketing`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `userColumn` | column_ref | ✓ | — | User ID |
| `channelColumn` | column_ref | ✓ | — | Channel |
| `timestampColumn` | column_ref | ✓ | — | Touch timestamp |
| `convertedColumn` | column_ref | ✓ | — | Converted (0/1) |
| `firstWeight` | number |  | `0.4` | First touch weight |
| `lastWeight` | number |  | `0.4` | Last touch weight |


### ⏳ Time-decay attribution

**ID:** `attribution_time_decay` · **Version:** `1.0.0`

Credit decays exponentially with time-from-conversion. The closer a touch is to the conversion event, the more credit it gets. Half-life parameter controls the decay rate.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:marketing_attribution`

Tags: `attribution` `marketing` `time-decay`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `userColumn` | column_ref | ✓ | — | User ID |
| `channelColumn` | column_ref | ✓ | — | Channel |
| `timestampColumn` | column_ref | ✓ | — | Touch timestamp |
| `convertedColumn` | column_ref | ✓ | — | Converted (0/1) |
| `halfLifeDays` | number |  | `7.0` | Half-life (days) |


### 🏥 Charlson Comorbidity Index

**ID:** `charlson_index` · **Version:** `1.0.0`

Compute the Charlson Comorbidity Index per patient from a long-form (patient_id, icd_code) input. Uses the standard Quan / Deyo weighting with bundled ICD-10 mappings for the 17 included conditions.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:healthcare_pack`

Tags: `healthcare` `charlson` `comorbidity`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `patientColumn` | column_ref | ✓ | — | Patient ID |
| `codeColumn` | column_ref | ✓ | — | ICD-10 code |


### 👥 Cohort table

**ID:** `cohort_table` · **Version:** `1.0.0`

Build a classic cohort table: rows = cohort (signup period), columns = period offset, cells = retained-user count or rate. Drives any retention chart.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:cohort_retention`

Tags: `cohort` `retention` `product-analytics`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `userColumn` | column_ref | ✓ | — | User ID column |
| `signupDateColumn` | column_ref | ✓ | — | Signup date column |
| `activityDateColumn` | column_ref | ✓ | — | Activity date column |
| `period` | enum |  | `month` | Period |
| `output` | enum |  | `rate` | Cell value |


### 🔒 DP aggregate (Gaussian)

**ID:** `dp_aggregate_gaussian` · **Version:** `1.0.0`

Sum a numeric column with Gaussian noise calibrated to (epsilon, delta, sensitivity) for (ε, δ)-differential privacy. Less noise per query than Laplace at large epsilon.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:privacy_pack`

Tags: `privacy` `dp` `gaussian` `compliance`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `valueColumn` | column_ref | ✓ | — | Value column |
| `groupColumn` | column_ref |  | — | Group column (optional) |
| `epsilon` | number |  | `1.0` | Epsilon |
| `delta` | number |  | `1e-05` | Delta |
| `sensitivity` | number | ✓ | — | Sensitivity |
| `seed` | integer |  | `42` | Random seed |


### 🔒 DP aggregate (Laplace)

**ID:** `dp_aggregate_laplace` · **Version:** `1.0.0`

Sum a numeric column with Laplace noise calibrated to (epsilon, sensitivity) for ε-differential privacy. Use to publish aggregates without revealing per-row contributions.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:privacy_pack`

Tags: `privacy` `dp` `laplace` `compliance`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `valueColumn` | column_ref | ✓ | — | Value column |
| `groupColumn` | column_ref |  | — | Group column (optional) |
| `epsilon` | number |  | `1.0` | Epsilon (privacy budget) |
| `sensitivity` | number | ✓ | — | Sensitivity (max single-row contribution) |
| `seed` | integer |  | `42` | Random seed |


### 💧 Drop-off attribution

**ID:** `drop_off_attribution` · **Version:** `1.0.0`

Per funnel-step pair, compute the drop-off rate and the absolute number of users lost. Surfaces which step bleeds the most users.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:funnel_pack`

Tags: `funnel` `dropoff` `attribution`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `userColumn` | column_ref | ✓ | — | User ID |
| `eventColumn` | column_ref | ✓ | — | Event name |
| `funnelSteps` | string | ✓ | — | Ordered funnel steps |


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


### 💰 LTV with discounting

**ID:** `ltv_with_discount` · **Version:** `1.0.0`

Compute lifetime value per customer applying a per-period discount rate. LTV = sum(period_revenue / (1+r)^t).

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:cohort_retention`

Tags: `ltv` `discount` `npv` `customer`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `customerColumn` | column_ref | ✓ | — | Customer ID |
| `periodColumn` | column_ref | ✓ | — | Period offset (0 = signup period) |
| `revenueColumn` | column_ref | ✓ | — | Period revenue |
| `discountRate` | number |  | `0.05` | Per-period discount rate |


### 🔀 Multi-path funnel

**ID:** `multi_path_funnel` · **Version:** `1.0.0`

Funnel where users may complete steps in any order. Counts how many users completed N out of M target steps, regardless of sequence.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:funnel_pack`

Tags: `funnel` `multi-path` `unordered`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `userColumn` | column_ref | ✓ | — | User ID |
| `eventColumn` | column_ref | ✓ | — | Event name |
| `targetSteps` | string | ✓ | — | Order doesn't matter; counted as a set. |


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


### 🔁 Repeat purchase rate

**ID:** `repeat_purchase_rate` · **Version:** `1.0.0`

Compute the share of customers that purchased more than N times within the analysis window. The classic engagement KPI: "what fraction of our customers come back?".

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:rfm_pack`

Tags: `rfm` `marketing` `engagement` `repeat`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `customerColumn` | column_ref | ✓ | — | Customer ID column |
| `dateColumn` | column_ref | ✓ | — | Transaction date column |
| `minPurchases` | integer |  | `2` | Min purchases to count as 'repeat' |
| `groupColumn` | column_ref |  | — | Compute the rate per group (e.g. by acquisition channel). |


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


### 📉 Retention curve

**ID:** `retention_curve` · **Version:** `1.0.0`

Compute the average retention rate per period offset (averaging across cohorts). Output: one row per offset with mean retention + cohort count.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:cohort_retention`

Tags: `cohort` `retention` `curve`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `userColumn` | column_ref | ✓ | — | User ID column |
| `signupDateColumn` | column_ref | ✓ | — | Signup date |
| `activityDateColumn` | column_ref | ✓ | — | Activity date |
| `period` | enum |  | `month` | Period |
| `maxPeriods` | integer |  | `12` | Max periods |


### 🎯 RFM score

**ID:** `rfm_score` · **Version:** `1.0.0`

Compute Recency / Frequency / Monetary scores per customer from a transaction log. Each axis is bucketed into N quantile bins (default 5); the per-customer output is one row carrying r_score, f_score, m_score (1=worst, N=best) plus the combined rfm_segment string (e.g. "5-5-5" = champions).

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:rfm_pack`

Tags: `rfm` `segmentation` `marketing` `customer` `cohort`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `customerColumn` | column_ref | ✓ | — | Customer ID column |
| `dateColumn` | column_ref | ✓ | — | Transaction date column |
| `amountColumn` | column_ref | ✓ | — | Transaction amount column |
| `asOfDate` | string |  | — | Recency = days between this date and the customer's most recent transaction. |
| `bins` | integer |  | `5` | Number of quantile bins per axis |


### 🪜 Step funnel

**ID:** `step_funnel` · **Version:** `1.0.0`

Count distinct users that reached each step of an ordered funnel. Output: one row per step with users + conversion rate vs first step.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:funnel_pack`

Tags: `funnel` `conversion`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `userColumn` | column_ref | ✓ | — | User ID |
| `eventColumn` | column_ref | ✓ | — | Event/step name |
| `funnelSteps` | string | ✓ | — | Event names in funnel order, e.g. 'visit,add_to_cart,checkout,purchase' |


### ⏳ Survival retention (KM lite)

**ID:** `survival_retention` · **Version:** `1.0.0`

Kaplan-Meier-style survival curve for user retention. Each user has a 'tenure' (days until churn or last seen) and a 'churned' flag. Output: survival probability per day.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:cohort_retention`

Tags: `retention` `survival` `kaplan-meier`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `tenureColumn` | column_ref | ✓ | — | Tenure (days) column |
| `eventColumn` | column_ref | ✓ | — | 1 = churned (event observed), 0 = censored (still active at last observation). |


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


### ⚖️ Bayes factor

**ID:** `bayes_factor` · **Version:** `1.0.0`

Compute the Bayes factor between two competing Beta-Binomial models (rate p0 vs rate p1) given observed successes + trials. BF > 1 favours the alternative; > 10 is strong evidence (Jeffreys).

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:bayesian_pack`

Tags: `bayesian` `bayes-factor` `model-comparison`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `successColumn` | column_ref | ✓ | — | Successes |
| `trialsColumn` | column_ref | ✓ | — | Trials |
| `p0` | number | ✓ | — | H0 rate |
| `p1` | number | ✓ | — | H1 rate |


### 🎲 Bayesian linear regression

**ID:** `bayesian_regression` · **Version:** `1.0.0`

Closed-form Bayesian linear regression with Normal prior on coefficients (ridge interpretation). Returns per-coefficient posterior mean + 95% credible interval.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:bayesian_pack`

Tags: `bayesian` `regression` `ridge`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `targetColumn` | column_ref | ✓ | — | Target |
| `featureColumns` | column_refs | ✓ | — | Features |
| `priorPrecision` | number |  | `1.0` | Prior precision (1/σ²) on coefficients |


### 🎲 Bayesian best-arm probability

**ID:** `best_bayesian_ab` · **Version:** `1.0.0`

For a binary-conversion A/B test with N variants, compute the posterior probability that each variant is the best (highest conversion rate). Beta(1,1) prior; Monte Carlo from posterior.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:ab_test_pack`

Tags: `ab-test` `bayesian` `best-arm`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `variantColumn` | column_ref | ✓ | — | Variant column |
| `convertedColumn` | column_ref | ✓ | — | Converted (0/1) |
| `samples` | integer |  | `50000` | Monte Carlo samples |
| `seed` | integer |  | `42` | Random seed |


### 🎲 Beta-Binomial posterior

**ID:** `beta_binomial_posterior` · **Version:** `1.0.0`

Conjugate Beta(α,β) prior + Binomial(n, p) likelihood → Beta(α+s, β+n-s) posterior. Per-group output: posterior parameters, mean, 95% credible interval.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:bayesian_pack`

Tags: `bayesian` `conjugate` `beta` `binomial`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `groupColumn` | column_ref | ✓ | — | Group column |
| `successColumn` | column_ref | ✓ | — | Successes column |
| `trialsColumn` | column_ref | ✓ | — | Trials column |
| `priorAlpha` | number |  | `1.0` | Prior α |
| `priorBeta` | number |  | `1.0` | Prior β |


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


### 🎲 Conjugate Normal posterior

**ID:** `conjugate_normal` · **Version:** `1.0.0`

Normal-Normal conjugate posterior for the mean (known variance). Per-group: posterior mean μ', posterior precision, 95% credible interval.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:bayesian_pack`

Tags: `bayesian` `conjugate` `normal`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `groupColumn` | column_ref |  | — | Group column (optional) |
| `valueColumn` | column_ref | ✓ | — | Value column |
| `priorMean` | number |  | `0.0` | Prior mean |
| `priorVariance` | number |  | `100.0` | Prior variance |
| `likelihoodVariance` | number |  | `1.0` | Known likelihood variance |


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


### ⏳ Cox proportional hazards

**ID:** `cox_proportional_hazards` · **Version:** `1.0.0`

Cox PH regression via lifelines. For each feature: hazard ratio, 95% CI, p-value. The standard survival-analysis model in clinical / actuarial work.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:stats_research`

Tags: `statistics` `survival` `cox` `hazards` `lifelines`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `durationColumn` | column_ref | ✓ | — | Duration column |
| `eventColumn` | column_ref | ✓ | — | Event observed (0/1) |
| `featureColumns` | column_refs | ✓ | — | Covariates |


### 📐 Delta-method ratio CI

**ID:** `delta_method_ratio` · **Version:** `1.0.0`

Confidence interval for a ratio metric (e.g. revenue / visit) using the delta method, accounting for the correlation between numerator and denominator.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:ab_test_pack`

Tags: `ab-test` `ratio` `ci` `delta-method`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `groupColumn` | column_ref | ✓ | — | Variant column (control/treatment) |
| `numeratorColumn` | column_ref | ✓ | — | Numerator (e.g. revenue) |
| `denominatorColumn` | column_ref | ✓ | — | Denominator (e.g. visits) |
| `confidence` | number |  | `0.95` | Confidence level |


### 📐 Difference-in-differences

**ID:** `diff_in_diff` · **Version:** `1.0.0`

Estimate the DiD effect via regression: outcome ~ treated * post + treated + post + controls. Coefficient on treated:post is the causal estimate.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:causal_inference`

Tags: `causal` `did` `regression`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `outcomeColumn` | column_ref | ✓ | — | Outcome |
| `treatedColumn` | column_ref | ✓ | — | Treated (0/1) |
| `postColumn` | column_ref | ✓ | — | Post-period (0/1) |
| `controlColumns` | column_refs |  | — | Optional control covariates |


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


### 📊 GLM logit

**ID:** `glm_logit` · **Version:** `1.0.0`

Logistic regression via statsmodels (full coefficient table with SE / z / p / 95% CI per feature). Different from sklearn's LogisticRegression: research-flavored output suitable for papers.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:stats_research`

Tags: `statistics` `glm` `logistic` `regression`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `targetColumn` | column_ref | ✓ | — | Target (binary) |
| `featureColumns` | column_refs | ✓ | — | Features |


### 📊 GLM Poisson

**ID:** `glm_poisson` · **Version:** `1.0.0`

Poisson regression for count outcomes via statsmodels. Use when the target is a count (admissions, claims, events).

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:stats_research`

Tags: `statistics` `glm` `poisson` `count`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `targetColumn` | column_ref | ✓ | — | Target (count) |
| `featureColumns` | column_refs | ✓ | — | Features |


### 📊 GLM probit

**ID:** `glm_probit` · **Version:** `1.0.0`

Probit regression via statsmodels. Same shape as Logit but with the probit link function — standard in economics for binary choice models.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:stats_research`

Tags: `statistics` `glm` `probit` `regression`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `targetColumn` | column_ref | ✓ | — | Target (binary) |
| `featureColumns` | column_refs | ✓ | — | Features |


### 📐 Instrumental variables (2SLS)

**ID:** `instrumental_variables` · **Version:** `1.0.0`

Two-stage least squares: first stage regresses the endogenous treatment on the instrument(s); second stage regresses the outcome on the predicted treatment. Identifies a causal effect when the instrument is exogenous.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:causal_inference`

Tags: `causal` `iv` `2sls` `econometrics`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `outcomeColumn` | column_ref | ✓ | — | Outcome |
| `endogenousColumn` | column_ref | ✓ | — | Endogenous treatment |
| `instrumentColumns` | column_refs | ✓ | — | Instruments |
| `controlColumns` | column_refs |  | — | Optional exogenous controls |


### ⏳ Kaplan-Meier survival

**ID:** `kaplan_meier` · **Version:** `1.0.0`

Estimate survival function from time-to-event + event-occurred data via lifelines KaplanMeierFitter. Output: per-time survival probability, lower/upper 95% CI.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:stats_research`

Tags: `statistics` `survival` `kaplan-meier` `lifelines`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `durationColumn` | column_ref | ✓ | — | Duration column |
| `eventColumn` | column_ref | ✓ | — | Event observed (0/1) |
| `groupColumn` | column_ref |  | — | Group column (optional) |


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


### ⏳ Log-rank test

**ID:** `log_rank_test` · **Version:** `1.0.0`

Compare survival between two or more groups (lifelines multivariate_logrank_test). Returns chi-squared statistic + p-value testing the null that all groups have the same survival.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:stats_research`

Tags: `statistics` `survival` `logrank` `lifelines`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `durationColumn` | column_ref | ✓ | — | Duration column |
| `eventColumn` | column_ref | ✓ | — | Event observed (0/1) |
| `groupColumn` | column_ref | ✓ | — | Group column |


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


### 🎲 MCMC sampler (PyMC)

**ID:** `mcmc_pymc` · **Version:** `1.0.0`

General-case MCMC sampler via PyMC. Fits a normal-likelihood model with priors on mean + std; returns posterior summary (mean, std, 94% HDI) per parameter. Requires the optional pymc dependency — see INTERNAL_NOTES.md if install fails.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:bayesian_pack`

Tags: `bayesian` `mcmc` `pymc`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `valueColumn` | column_ref | ✓ | — | Value column |
| `draws` | integer |  | `1000` | MCMC draws |
| `chains` | integer |  | `2` | Chains |


### 📊 Mixed-effects regression

**ID:** `mixed_effects` · **Version:** `1.0.0`

Linear mixed-effects model via statsmodels MixedLM. Random intercept per group + fixed effects on features. Standard for repeated-measures / multi-site clinical trial data.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:stats_research`

Tags: `statistics` `mixed-effects` `random-effects` `regression`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `targetColumn` | column_ref | ✓ | — | Target (continuous) |
| `featureColumns` | column_refs | ✓ | — | Fixed-effect features |
| `groupColumn` | column_ref | ✓ | — | Random-effect group |


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


### 🎯 Propensity-score matching

**ID:** `propensity_score_matching` · **Version:** `1.0.0`

Estimate propensity score (P(treatment=1 | covariates)) via logistic regression, then 1:1 nearest-neighbour match treated vs control. Returns matched-pair frame for downstream ATE estimation.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:causal_inference`

Tags: `causal` `psm` `matching`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `treatmentColumn` | column_ref | ✓ | — | Treatment (0/1) |
| `covariateColumns` | column_refs | ✓ | — | Covariates |
| `caliper` | number |  | `0.1` | Max distance (caliper) |


### 📐 Regression discontinuity

**ID:** `regression_discontinuity` · **Version:** `1.0.0`

Sharp RD: fit two regressions (left and right of cutoff) on a running variable; the jump at the cutoff is the local-average treatment effect.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:causal_inference`

Tags: `causal` `rdd` `quasi-experimental`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `outcomeColumn` | column_ref | ✓ | — | Outcome |
| `runningColumn` | column_ref | ✓ | — | Running variable (assignment) |
| `cutoff` | number | ✓ | — | Cutoff value |
| `bandwidth` | number |  | — | Restrict to [cutoff-bw, cutoff+bw]. Blank = use all data. |


### 📏 Sample-size calculator

**ID:** `sample_size_calc` · **Version:** `1.0.0`

Compute required sample size per variant for a two-sample test of proportions, given baseline rate, minimum detectable effect, alpha, and power. Pure parameter calc — input frame is ignored.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:ab_test_pack`

Tags: `ab-test` `sample-size` `power`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `baselineRate` | number | ✓ | — | Baseline conversion rate |
| `mde` | number | ✓ | — | Minimum detectable effect (absolute) |
| `alpha` | number |  | `0.05` | Alpha |
| `power` | number |  | `0.8` | Power |


### ⏯ Sequential SPRT

**ID:** `sequential_sprt` · **Version:** `1.0.0`

Wald's Sequential Probability Ratio Test for early stopping. Two competing hypotheses (H0: p = p0, H1: p = p1); after each observation, the log-likelihood ratio either crosses an upper bound (accept H1) or lower bound (accept H0), or continues sampling.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:ab_test_pack`

Tags: `ab-test` `sequential` `sprt` `early-stopping`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `convertedColumn` | column_ref | ✓ | — | Converted (0/1) |
| `orderColumn` | column_ref | ✓ | — | Order (timestamp / row index) |
| `p0` | number | ✓ | — | H0 conversion rate |
| `p1` | number | ✓ | — | H1 conversion rate |
| `alpha` | number |  | `0.05` | Alpha |
| `beta` | number |  | `0.2` | Beta |


### 📐 Synthetic control

**ID:** `synthetic_control` · **Version:** `1.0.0`

Construct a synthetic counterfactual for a treated unit by weighted combination of control units. Returns the estimated effect over the post-treatment period.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:causal_inference`

Tags: `causal` `synthetic-control`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `unitColumn` | column_ref | ✓ | — | Unit ID |
| `timeColumn` | column_ref | ✓ | — | Time period |
| `outcomeColumn` | column_ref | ✓ | — | Outcome |
| `treatedUnit` | string | ✓ | — | ID of treated unit |
| `treatmentTime` | number | ✓ | — | First treated period |


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

### 📜 Column lineage report

**ID:** `column_lineage_report` · **Version:** `1.0.0`

Render a per-column lineage report describing each column's name, dtype, distinct count, null count, min/max (numeric), and provenance hint. Pass-through on the data; a side-effect JSON + CSV artifact carries the report for compliance reviews.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:audit_pack`

Tags: `audit` `lineage` `compliance` `reproducibility`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `stageLabel` | string |  | `post-pipeline` | Free-form label for the report — e.g. 'after-cleansing', 'pre-export'. |


### 🧪 Confusion matrix

**ID:** `confusion_matrix` · **Version:** `1.0.0`

Compute the confusion-matrix counts table for a classification result. Returns one row per (actual, predicted) pair with the count and the row-normalised rate. Pair with export_to_image (heatmap) to render visually.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:ml_eval_pack`

Tags: `ml` `evaluation`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `actual` | column_ref | ✓ | — | Actual column |
| `predicted` | column_ref | ✓ | — | Predicted column |


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


### 🥇 Golden row assert

**ID:** `golden_row_assert` · **Version:** `1.0.0`

Assert that specific rows (matched by an ID column) still have the expected values in named target columns. Use to lock in the computed value of a small handful of canonical rows that exercise edge cases.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:pipeline_test_pack`

Tags: `test` `golden` `regression` `assert`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `idColumn` | column_ref | ✓ | — | ID column |
| `expectations` | string | ✓ | — | JSON array of objects: [{"id": 42, "revenue": 1200, "is_premium": true}, …]. Each object MUST contain the ID column value plus the columns to assert. |
| `tolerance` | number |  | `0.0` | Allowed absolute difference for float comparisons. 0 = exact match. |


### 🔒 K-anonymity check

**ID:** `k_anonymity_check` · **Version:** `1.0.0`

Verify that every combination of quasi-identifier values appears in at least K rows. Reports the smallest equivalence-class size + the rows that violate the K threshold.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:privacy_pack`

Tags: `privacy` `k-anonymity` `compliance`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `quasiIdentifiers` | column_refs | ✓ | — | Quasi-identifier columns |
| `k` | integer |  | `5` | Minimum equivalence class size |


### 🧪 K-fold split

**ID:** `kfold_split` · **Version:** `1.0.0`

Tag each row with a fold index (0 .. k-1) for k-fold cross-validation. Use stratified k-fold when you have a target column with class imbalance.

🛠 engine: `polars` · ⚠️ non-deterministic · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:ml_eval_pack`

Tags: `ml` `evaluation` `cross-validation`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `n_splits` | integer |  | `5` | Number of folds |
| `stratify_by` | column_ref |  | — | Stratify by (optional) |
| `seed` | integer |  | `42` | Random seed |
| `output_column` | string |  | `fold` | Output column name |


### 🔒 L-diversity check

**ID:** `l_diversity_check` · **Version:** `1.0.0`

For each equivalence class (defined by quasi-identifiers), verify the sensitive attribute has at least L distinct values. Stronger than k-anonymity against attribute-disclosure attacks.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:privacy_pack`

Tags: `privacy` `l-diversity` `compliance`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `quasiIdentifiers` | column_refs | ✓ | — | Quasi-identifier columns |
| `sensitiveColumn` | column_ref | ✓ | — | Sensitive attribute |
| `l` | integer |  | `3` | L (min distinct sensitive values per class) |


### 🧪 Model metrics

**ID:** `model_metrics` · **Version:** `1.0.0`

Compute evaluation metrics by comparing actual and predicted columns. Auto-detects regression vs. classification from the actual column's type. Returns a one-row DataFrame with the appropriate metrics.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:ml_eval_pack`

Tags: `ml` `evaluation` `metrics`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `actual` | column_ref | ✓ | — | Actual column |
| `predicted` | column_ref | ✓ | — | Predicted column |
| `task` | enum |  | `auto` | Task |
| `probability_column` | column_ref |  | — | If set + task is classification, also computes ROC AUC and log loss. |


### 📸 Pipeline snapshot test

**ID:** `pipeline_snapshot_test` · **Version:** `1.0.0`

Compute a content hash + row/column count snapshot for the input frame. Compare against an expected snapshot (provided as a JSON string in params). Pass-through when matched; raises an error with the diff when not. Use as a pipeline regression guard.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:pipeline_test_pack`

Tags: `test` `regression` `snapshot` `validate`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `expectedSnapshot` | string |  | — | JSON object {"rows": N, "cols": M, "hash": "..."} produced by a previous run. Leave blank on first run; the artifact emits the snapshot to copy back into this param. |
| `tolerance` | number |  | `0.0` | 0 = exact match. 5 = allow ±5% row count drift before failing. |


### 📋 Provenance certificate

**ID:** `provenance_certificate` · **Version:** `1.0.0`

Emit a signed-style certificate capturing the run's identity (run id, timestamp), the input frame's content hash, and the user-supplied source / pipeline metadata. The artifact is a JSON object suitable for archiving alongside exported data.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:audit_pack`

Tags: `audit` `provenance` `certificate` `compliance`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `issuer` | string |  | `DataInsightGrove` | Issuer (org / team) |
| `datasetName` | string | ✓ | — | Human-readable name for the data being certified. |
| `intendedUse` | string |  | — | Optional. e.g. 'Q4 board report', 'monthly compliance pack'. |


### 🧪 ROC curve

**ID:** `roc_curve` · **Version:** `1.0.0`

Compute (FPR, TPR, threshold) points along the ROC curve plus the AUC. Output is a long-form DataFrame ready to feed export_to_image (line) for plotting. Binary classification only.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:ml_eval_pack`

Tags: `ml` `evaluation` `auc`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `actual` | column_ref | ✓ | — | Actual column (0/1 or True/False) |
| `probability` | column_ref | ✓ | — | Probability column |
| `positive_label` | string |  | `1` | Value in `actual` that represents the positive class. Defaults to 1. |


### 🚪 Schema gate

**ID:** `schema_gate` · **Version:** `1.0.0`

Assert that specific columns exist with expected dtypes. Fails the pipeline run if a required column is missing or has the wrong type. Use immediately after an ingest step to catch upstream schema changes early.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:pipeline_test_pack`

Tags: `test` `schema` `validate` `gate` `contract`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `requiredColumns` | string | ✓ | — | e.g. customer_id,order_date,revenue |
| `expectedTypes` | string |  | — | Optional. e.g. customer_id:Int64,order_date:Date,revenue:Float64. Leave blank to skip dtype check. |
| `allowExtraColumns` | boolean |  | `True` | When false, the gate also fails if the input has columns NOT in requiredColumns. |


### 🔒 T-closeness check

**ID:** `t_closeness` · **Version:** `1.0.0`

For each equivalence class, verify the per-class distribution of the sensitive attribute is within distance T of the global distribution (variation distance). Stronger than l-diversity for skewed sensitive attributes.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: may_reduce · schema: rebuilds

📦 Source: `pack:privacy_pack`

Tags: `privacy` `t-closeness` `compliance`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `quasiIdentifiers` | column_refs | ✓ | — | Quasi-identifier columns |
| `sensitiveColumn` | column_ref | ✓ | — | Sensitive attribute |
| `t` | number |  | `0.2` | Maximum allowed variation distance |


### 🔗 Tamper-evident log entry

**ID:** `tamper_evident_log` · **Version:** `1.0.0`

Append a signed-chain log entry capturing this run's hash + the previous entry's hash (Merkle-style chaining). The log file lives at the configured path; tampering with any past entry invalidates every subsequent hash. Use to build an auditable history of pipeline runs.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:audit_pack`

Tags: `audit` `tamper-evident` `chain` `log`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `logPath` | string | ✓ | `audit_log.jsonl` | Relative paths resolve under data/outputs/<run>/. Each line is one chained entry. |
| `annotation` | string |  | — | Free-form note appended to this entry (e.g. 'monthly close'). Goes into the chain. |


### 🧪 Train/test split

**ID:** `train_test_split` · **Version:** `1.0.0`

Add a `split` column tagging each row as `train` or `test`. Optionally stratifies by a categorical column so the train and test sets have the same class balance.

🛠 engine: `polars` · ⚠️ non-deterministic · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: modifies

📦 Source: `pack:ml_eval_pack`

Tags: `ml` `evaluation`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `test_size` | number |  | `0.2` | Test fraction |
| `stratify_by` | column_ref |  | — | Stratify by (optional) |
| `seed` | integer |  | `42` | Random seed |
| `output_column` | string |  | `split` | Output column name |


---

## 📈 Visualize

### 📊 Box plot

**ID:** `box_plot` · **Version:** `1.0.0`

Render a box-whisker plot of one numeric column, optionally split by a categorical group column. Shows median, quartiles, whiskers, and outlier dots — distribution shape at a glance.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:diagnostic_charts`

Tags: `chart` `diagnostic`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `value` | column_ref | ✓ | — | Value column |
| `group` | column_ref |  | — | Group column (optional) |
| `title` | string |  | `Box plot` | Title |
| `output_path` | string |  | — | Defaults to data/outputs/<run>/<step>.png |


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


### 📅 Calendar heatmap

**ID:** `calendar_heatmap` · **Version:** `1.0.0`

GitHub-style year-view heatmap. Each cell is one day, rows are weekdays, columns are weeks. Color intensity = the value column. Reveals day-of-week / week-of-year patterns at a glance — engagement tracking, hospital admissions, sales, IoT readings.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:analytics_charts`

Tags: `chart` `calendar` `time-series` `heatmap` `github`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `dateColumn` | column_ref | ✓ | — | Date column |
| `valueColumn` | column_ref | ✓ | — | Numeric column. Multiple rows on the same date are summed. |
| `year` | integer |  | — | Restrict to a single year. Leave blank to render every year present in the data, stacked. |
| `color_scale` | enum |  | `Greens` | Color scale |
| `title` | string |  | `Calendar heatmap` | Title |
| `format` | enum | ✓ | `png` | Format |
| `width` | integer |  | `1600` | Width (px) |
| `height` | integer |  | `500` | Height (px) |


### 🎯 Calibration curve

**ID:** `calibration_curve` · **Version:** `1.0.0`

How well-calibrated are the model's probabilities? Bins predictions by predicted_proba, then plots the actual fraction of positives in each bin against the mean predicted probability. A perfectly calibrated classifier sits on the diagonal — predicted probability of 0.7 means 70% of those samples are actually positive.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:ml_eval_pack`

Tags: `chart` `ml` `evaluation` `calibration` `reliability`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `actualColumn` | column_ref | ✓ | — | Actual (true class) column |
| `probaColumn` | column_ref | ✓ | — | Predicted probability column |
| `bins` | integer |  | `10` | Number of probability bins |
| `strategy` | enum |  | `uniform` | uniform: equal-width bins on [0,1]. quantile: equal-count bins (more robust when predictions cluster). |
| `title` | string |  | `Calibration curve` | Title |
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


### 🎻 Chord diagram

**ID:** `chord_diagram` · **Version:** `1.0.0`

Circular relationship plot from a (source, target, value) edge list. Use for many-to-many flows where source and target draw from the same set of categories — international trade, social network ties, transaction graphs.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:analytics_charts`

Tags: `chart` `chord` `network` `relationships`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `sourceColumn` | column_ref | ✓ | — | Source category column |
| `targetColumn` | column_ref | ✓ | — | Target category column |
| `valueColumn` | column_ref | ✓ | — | Edge value column |
| `title` | string |  | `Chord diagram` | Title |
| `format` | enum | ✓ | `png` | Format |
| `width` | integer |  | `1200` | Width (px) |
| `height` | integer |  | `1200` | Height (px) |


### 📊 Coefficient + CI plot

**ID:** `coefficient_ci_plot` · **Version:** `1.0.0`

Forest-style plot of regression / model coefficients with their confidence intervals. Each row in the input is one feature; columns carry the point estimate and the lower / upper CI bounds. Coefficients are sorted by magnitude.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:analytics_charts`

Tags: `chart` `regression` `coefficients` `confidence interval` `forest plot`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `featureColumn` | column_ref | ✓ | — | Feature name column |
| `estimateColumn` | column_ref | ✓ | — | Coefficient (point estimate) column |
| `lowerColumn` | column_ref | ✓ | — | CI lower bound column |
| `upperColumn` | column_ref | ✓ | — | CI upper bound column |
| `title` | string |  | `Coefficients with 95% CI` | Title |
| `format` | enum | ✓ | `png` | Format |
| `width` | integer |  | `1000` | Width (px) |
| `height` | integer |  | `800` | Height (px) |


### 🟦 Confusion matrix

**ID:** `confusion_matrix` · **Version:** `1.0.0`

Render a confusion matrix heatmap with per-cell counts and percentages. Use to set the operational classification threshold (how many false positives are tolerable?).

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:analytics_charts`

Tags: `chart` `classification` `ml` `confusion` `evaluation`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `actualColumn` | column_ref | ✓ | — | Actual class column |
| `predictedColumn` | column_ref | ✓ | — | Predicted class column |
| `normalize` | enum |  | `counts` | counts: raw cell counts. row_percent: each actual-class row sums to 100% (recall view). column_percent: each predicted-class column sums to 100% (precision view). all_percent: cells sum to 100%. |
| `title` | string |  | `Confusion Matrix` | Title |
| `format` | enum | ✓ | `png` | Format |
| `width` | integer |  | `900` | Width (px) |
| `height` | integer |  | `800` | Height (px) |


### 🌲 Dendrogram

**ID:** `dendrogram` · **Version:** `1.0.0`

Hierarchical clustering tree from a vector column. Use to discover natural groupings — gene expression cohorts, customer segments, document similarity. Pair with the built-in distance_matrix step when you have pairwise distances rather than feature vectors.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:analytics_charts`

Tags: `chart` `hierarchical` `clustering` `tree` `linkage`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `vectorColumn` | column_ref | ✓ | — | List-of-numbers column. Each row is one observation; the dendrogram clusters across rows. |
| `labelColumn` | column_ref |  | — | Used as leaf labels. Defaults to integer row index. |
| `method` | enum |  | `ward` | ward (default): minimises within-cluster variance. average: UPGMA. complete: max distance. single: chain-style nearest-neighbour. |
| `metric` | enum |  | `euclidean` | Distance between observations. 'ward' linkage requires euclidean; using a non-euclidean metric with ward falls back to complete. |
| `title` | string |  | `Dendrogram` | Title |
| `format` | enum | ✓ | `png` | Format |
| `width` | integer |  | `1600` | Width (px) |
| `height` | integer |  | `800` | Height (px) |


### 📈 Density plot

**ID:** `density_plot` · **Version:** `1.0.0`

Smooth distribution via Gaussian KDE. Use when N is large enough that histogram bin choice starts to dominate the appearance of the data. Optional grouping draws one curve per category.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:diagnostic_charts`

Tags: `chart` `diagnostic` `kde` `density`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `value` | column_ref | ✓ | — | Value column |
| `group` | column_ref |  | — | Draw one density curve per category in this column. |
| `fill` | boolean |  | `True` | Fill under curve |
| `title` | string |  | `Density` | Title |
| `output_path` | string |  | — | Defaults to data/outputs/<run>/<step>.png |


### 📊 ECDF plot

**ID:** `ecdf_plot` · **Version:** `1.0.0`

Empirical Cumulative Distribution Function — every data point gets a y-value showing what fraction of the sample is ≤ it. Optionally split by a categorical group column to compare distributions.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:diagnostic_charts`

Tags: `chart` `diagnostic`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `value` | column_ref | ✓ | — | Value column |
| `group` | column_ref |  | — | Group column (optional) |
| `title` | string |  | `ECDF` | Title |
| `output_path` | string |  | — | Output path |


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


### 📈 Cumulative gains chart

**ID:** `gain_chart` · **Version:** `1.0.0`

Y-axis: cumulative percent of positives captured. X-axis: cumulative percent of population (sorted by predicted_proba descending). Shows how many of the positive class you'd reach by targeting only the top X% of the model's most confident predictions. Standard marketing-uplift / churn-targeting chart.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:ml_eval_pack`

Tags: `chart` `ml` `evaluation` `gains` `uplift`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `actualColumn` | column_ref | ✓ | — | Actual (true class) column |
| `probaColumn` | column_ref | ✓ | — | Predicted probability column |
| `title` | string |  | `Cumulative gains` | Title |
| `output_path` | string |  | — | Defaults to data/outputs/<run>/<step>.png |


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


### 🔢 KPI card

**ID:** `kpi_card` · **Version:** `1.0.0`

Render one or more big-number cards with a label, the headline value, and optional comparison-vs-baseline percent. Each row in the input is one card. Use as the top-row of an executive dashboard or a campaign-results report.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:analytics_charts`

Tags: `chart` `kpi` `card` `dashboard` `scorecard`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `labelColumn` | column_ref | ✓ | — | Label column |
| `valueColumn` | column_ref | ✓ | — | Value column |
| `baselineColumn` | column_ref |  | — | Compute and display percent change vs this baseline. Green up arrow when current > baseline, red down arrow when below. |
| `format_value` | enum |  | `raw` | Value formatting |
| `title` | string |  | — | Title |
| `format` | enum | ✓ | `png` | Format |
| `width` | integer |  | `1600` | Width (px) |
| `height` | integer |  | `400` | Height (px) |


### 📊 Lift chart

**ID:** `lift_chart` · **Version:** `1.0.0`

How much better than random is the model at each cumulative percentile? Y-axis: ratio of (positives captured by top X%) / (random baseline). Lift = 1 means random performance; lift > 2 at 10% means the model is twice as effective as random in the top decile.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:ml_eval_pack`

Tags: `chart` `ml` `evaluation` `lift` `uplift`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `actualColumn` | column_ref | ✓ | — | Actual (true class) column |
| `probaColumn` | column_ref | ✓ | — | Predicted probability column |
| `buckets` | integer |  | `10` | Number of buckets (deciles by default) |
| `title` | string |  | `Lift chart` | Title |
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


### 🕸 Network graph

**ID:** `network_graph` · **Version:** `1.0.0`

Force-directed network plot from a (source, target, value) edge list. Use for fraud rings, social-network analysis, supply-chain dependencies. Different from chord_diagram (which assumes source + target draw from the same set); network_graph supports arbitrary node sets and reveals communities via spring layout.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:analytics_charts`

Tags: `chart` `network` `graph` `force-directed` `community`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `sourceColumn` | column_ref | ✓ | — | Source node column |
| `targetColumn` | column_ref | ✓ | — | Target node column |
| `valueColumn` | column_ref |  | — | If set, edge widths are proportional to this value. |
| `communityDetection` | boolean |  | `True` | Run greedy modularity community detection and color each node by its assigned community. |
| `title` | string |  | `Network graph` | Title |
| `format` | enum | ✓ | `png` | Format |
| `width` | integer |  | `1400` | Width (px) |
| `height` | integer |  | `1000` | Height (px) |


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


### 📉 Precision-Recall curve

**ID:** `pr_curve` · **Version:** `1.0.0`

Render a Precision-Recall curve with average-precision (AP) reported in the legend. Better than ROC when the positive class is rare (fraud, churn, anomaly). Pairs with logistic_regression.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:analytics_charts`

Tags: `chart` `classification` `ml` `precision` `recall` `average precision`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `actualColumn` | column_ref | ✓ | — | Actual (true class) column |
| `probaColumn` | column_ref | ✓ | — | Predicted probability column |
| `title` | string |  | `Precision-Recall Curve` | Title |
| `format` | enum | ✓ | `png` | Format |
| `width` | integer |  | `1000` | Width (px) |
| `height` | integer |  | `800` | Height (px) |


### 📊 Q-Q plot (normality)

**ID:** `qq_plot` · **Version:** `1.0.0`

Quantile-Quantile plot comparing the column's quantiles to a normal distribution. Points on the diagonal = normal; deviations show what kind of non-normality you have (heavy tails, skew, etc.). The companion to Shapiro-Wilk.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:diagnostic_charts`

Tags: `chart` `diagnostic` `normality`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `value` | column_ref | ✓ | — | Value column |
| `title` | string |  | `Q-Q plot vs. normal` | Title |
| `output_path` | string |  | — | Output path |


### 🌄 Ridge plot

**ID:** `ridge_plot` · **Version:** `1.0.0`

Stacked density plots — one row per category, KDE curve per row, all sharing the same x axis. Best for comparing 5-30 distributions side by side. Iconic for 'temperature by month', 'page-load time by browser', any 'shape comparison across many groups'.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:diagnostic_charts`

Tags: `chart` `diagnostic` `kde` `density` `comparison`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `value` | column_ref | ✓ | — | Value column |
| `group` | column_ref | ✓ | — | One density curve drawn per distinct value in this column. |
| `color_scale` | enum |  | `viridis` | Color scale |
| `overlap` | number |  | `0.5` | 0 = curves don't overlap; 1 = full overlap. The classic 'Joy Division cover' look is around 0.7. |
| `title` | string |  | `Ridge plot` | Title |
| `output_path` | string |  | — | Defaults to data/outputs/<run>/<step>.png |


### 📈 ROC + AUC curve

**ID:** `roc_curve` · **Version:** `1.0.0`

Render a Receiver Operating Characteristic curve with the AUC reported in the legend. Pairs with logistic_regression: feed `actual` (the true 0/1 column) and `predicted_proba` (the probability column the classifier produced).

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:analytics_charts`

Tags: `chart` `classification` `ml` `roc` `auc` `evaluation`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `actualColumn` | column_ref | ✓ | — | The true 0/1 (or true/false) outcome column. |
| `probaColumn` | column_ref | ✓ | — | The classifier's predicted probability of the positive class — output of logistic_regression's predicted_proba. |
| `title` | string |  | `ROC Curve` | Title |
| `format` | enum | ✓ | `png` | Format |
| `width` | integer |  | `1000` | Width (px) |
| `height` | integer |  | `800` | Height (px) |


### 🌊 Sankey flow

**ID:** `sankey_flow` · **Version:** `1.0.0`

Render data-flow Sankey from (source, target, value) edges. Use for user journeys, attribution flows, A/B test cohort transitions, supply chains, energy / material flows. Distinct from the lineage Sankey in the editor — this one renders a static PNG of your data.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:analytics_charts`

Tags: `chart` `sankey` `flow` `alluvial` `transitions`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `sourceColumn` | column_ref | ✓ | — | Source node column |
| `targetColumn` | column_ref | ✓ | — | Target node column |
| `valueColumn` | column_ref | ✓ | — | Numeric flow magnitude. Multiple rows with the same (source, target) are summed. |
| `title` | string |  | `Sankey flow` | Title |
| `format` | enum | ✓ | `png` | Format |
| `width` | integer |  | `1600` | Width (px) |
| `height` | integer |  | `900` | Height (px) |


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


### 🟫 Treemap

**ID:** `treemap` · **Version:** `1.0.0`

Each row becomes a rectangle whose area is proportional to the value column. Use for portfolio composition, market-cap, file-system browsers — anywhere part-to-whole over many categories matters.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:analytics_charts`

Tags: `chart` `treemap` `composition` `part-to-whole`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `labelColumn` | column_ref | ✓ | — | Label column |
| `valueColumn` | column_ref | ✓ | — | Value (size) column |
| `colorColumn` | column_ref |  | — | Optional categorical column to color rectangles by group. |
| `title` | string |  | `Treemap` | Title |
| `format` | enum | ✓ | `png` | Format |
| `width` | integer |  | `1400` | Width (px) |
| `height` | integer |  | `900` | Height (px) |


### 📊 Violin plot

**ID:** `violin_plot` · **Version:** `1.0.0`

Violin plot — KDE distribution + box-plot hybrid. Shows the SHAPE of the distribution (bimodality, skew, fat tails) that a box plot hides. Optionally split by a categorical group column.

🛠 engine: `polars` · ⬅️ inputs: 1 · ➡️ outputs: 1 · rows: preserves · schema: preserves

📦 Source: `pack:diagnostic_charts`

Tags: `chart` `diagnostic`

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `value` | column_ref | ✓ | — | Value column |
| `group` | column_ref |  | — | Group column (optional) |
| `title` | string |  | `Violin plot` | Title |
| `output_path` | string |  | — | Output path |


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
