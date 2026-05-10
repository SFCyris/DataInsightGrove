# Prior-Art Map

Comprehensive mapping of every notable DIG feature to publicly-available
prior art. Maintained as a defensive-evidence document: for each feature
DIG implements, this file points to predecessors that establish the
technique as known, freely-available, or unpatentable subject matter.

> **This document is not a legal opinion.** It is a structured pointer
> to publicly observable prior art compiled by the project maintainers.
> A real freedom-to-operate (FTO) review for commercial deployment
> requires a registered patent attorney with access to professional
> patent search databases, conducting per-claim analysis against
> jurisdiction-specific filings.

When adding a new feature, append a row to the relevant section with
links to ≥ 2 unrelated prior-art sources (academic + open-source is
ideal). Prefer permanent, citable URLs (project repos, archived papers,
Wikipedia revisions); avoid blog posts that may rotate.

---

## 1. Visual Pipeline Editor (boxes-and-arrows DAG)

The fundamental "drag boxes onto a canvas, connect them with arrows,
each box represents a transformation" pattern is decades old.

| Predecessor | Year | License | Link |
|---|---|---|---|
| LabVIEW | 1986 | proprietary, 38-year track record | [Wikipedia](https://en.wikipedia.org/wiki/LabVIEW) |
| Yahoo! Pipes | 2007 | proprietary, defunct, freely documented | [Wikipedia](https://en.wikipedia.org/wiki/Yahoo!_Pipes) |
| KNIME Analytics Platform | 2004 | GPLv3 | [knime.com](https://www.knime.com/) · [GitHub](https://github.com/knime/knime-core) |
| Apache NiFi | 2014 | Apache 2.0 | [nifi.apache.org](https://nifi.apache.org/) · [GitHub](https://github.com/apache/nifi) |
| Apache Airflow | 2014 | Apache 2.0 | [airflow.apache.org](https://airflow.apache.org/) · [GitHub](https://github.com/apache/airflow) |
| dbt | 2016 | Apache 2.0 | [getdbt.com](https://www.getdbt.com/) · [GitHub](https://github.com/dbt-labs/dbt-core) |
| Dagster | 2018 | Apache 2.0 | [dagster.io](https://dagster.io/) · [GitHub](https://github.com/dagster-io/dagster) |
| Prefect | 2018 | Apache 2.0 | [prefect.io](https://www.prefect.io/) · [GitHub](https://github.com/PrefectHQ/prefect) |
| RapidMiner / Altair AI Studio | 2001 | proprietary, freely documented | [Wikipedia](https://en.wikipedia.org/wiki/RapidMiner) |
| Orange Data Mining | 1996 | GPLv3 | [orangedatamining.com](https://orangedatamining.com/) · [GitHub](https://github.com/biolab/orange3) |
| Apache Beam | 2016 | Apache 2.0 | [beam.apache.org](https://beam.apache.org/) · [GitHub](https://github.com/apache/beam) |

**DIG underlying library:** [xyflow / @xyflow/react](https://github.com/xyflow/xyflow) (MIT)

---

## 2. Topological / Layered Graph Auto-Layout

Algorithm for arranging DAG nodes into columns + rows.

| Predecessor | Year | License | Link |
|---|---|---|---|
| Sugiyama et al. (1981) algorithm — original layered layout paper | 1981 | academic | [IEEE record](https://ieeexplore.ieee.org/document/4308636) |
| Graphviz `dot` | 1991 | EPL 1.0 | [graphviz.org](https://graphviz.org/) · [GitLab](https://gitlab.com/graphviz/graphviz) |
| Dagre.js | 2012 | MIT | [GitHub](https://github.com/dagrejs/dagre) |
| ELK (Eclipse Layout Kernel) | 2008 | EPL 2.0 | [eclipse.dev/elk](https://eclipse.dev/elk/) · [GitHub](https://github.com/eclipse/elk) |
| Reactflow built-in `getLayoutedElements` examples | 2020+ | MIT | [reactflow.dev](https://reactflow.dev/examples/layout) |

---

## 3. Plugin / Step / Operator Architecture

Pluggable transformation nodes loaded from a registry.

| Predecessor | Year | License | Link |
|---|---|---|---|
| KNIME nodes | 2004 | GPLv3 | [knime.com docs](https://docs.knime.com/) |
| Apache NiFi processors | 2014 | Apache 2.0 | [nifi.apache.org docs](https://nifi.apache.org/docs.html) |
| Airflow operators | 2014 | Apache 2.0 | [Airflow docs](https://airflow.apache.org/docs/apache-airflow/stable/concepts.html#operators) |
| dbt packages | 2017 | Apache 2.0 | [hub.getdbt.com](https://hub.getdbt.com/) |
| Dagster ops & graphs | 2018 | Apache 2.0 | [Dagster docs](https://docs.dagster.io/concepts/ops-jobs-graphs) |

---

## 4. Live Data Grid with Profile-Driven Types

Grid that shows data alongside per-column type / quality information.

| Predecessor | Year | License | Link |
|---|---|---|---|
| OpenRefine (formerly Google Refine) | 2010 | BSD 3-Clause | [openrefine.org](https://openrefine.org/) · [GitHub](https://github.com/OpenRefine/OpenRefine) |
| pandas DataFrame `.head()` / `_repr_html_` | 2008 | BSD 3-Clause | [pandas.pydata.org](https://pandas.pydata.org/) |
| Apache Spark `df.show()` / Jupyter integration | 2014 | Apache 2.0 | [spark.apache.org](https://spark.apache.org/) |
| Observable Plot grid view | 2021 | ISC | [observablehq.com/plot](https://observablehq.com/plot/) |
| Glide Data Grid | 2021 | MIT | [GitHub](https://github.com/glideapps/glide-data-grid) |
| AG Grid Community | 2016 | MIT | [ag-grid.com](https://www.ag-grid.com/) · [GitHub](https://github.com/ag-grid/ag-grid) |

---

## 5. Column Profiling & Logical Type Detection

Automatic detection of column "meaning" beyond physical dtype (currency,
percentage, email, etc.).

| Predecessor | Year | License | Link |
|---|---|---|---|
| pandas-profiling / ydata-profiling | 2016 | MIT | [GitHub](https://github.com/ydataai/ydata-profiling) |
| Great Expectations Profiler | 2018 | Apache 2.0 | [GitHub](https://github.com/great-expectations/great_expectations) |
| Apache Spark `df.describe()` / `.summary()` | 2014 | Apache 2.0 | [Spark docs](https://spark.apache.org/docs/latest/api/python/reference/pyspark.sql/api/pyspark.sql.DataFrame.summary.html) |
| OpenRefine "Common Transforms" detection | 2010 | BSD 3-Clause | [openrefine.org docs](https://docs.openrefine.org/) |
| dataprep.eda | 2020 | MIT | [GitHub](https://github.com/sfu-db/dataprep) |
| `csvkit` / `csvstat` | 2011 | MIT | [csvkit.rtfd.io](https://csvkit.readthedocs.io/) |

---

## 6. Sankey / Volume Flow Diagrams

Visualisation of flow magnitudes via bands of variable thickness.

| Predecessor | Year | License | Link |
|---|---|---|---|
| Captain Henry Sankey (steam-engine efficiency) | 1898 | public domain (>120 years) | [Wikipedia: Sankey diagram](https://en.wikipedia.org/wiki/Sankey_diagram) |
| Charles Joseph Minard's Russian campaign chart | 1869 | public domain | [Wikipedia: Minard](https://en.wikipedia.org/wiki/Charles_Joseph_Minard) |
| Mike Bostock's d3-sankey | 2012 | BSD 3-Clause | [GitHub](https://github.com/d3/d3-sankey) · [Observable example](https://observablehq.com/@d3/sankey-diagram) |
| Apache ECharts Sankey | 2013 | Apache 2.0 | [echarts.apache.org](https://echarts.apache.org/examples/en/index.html#chart-type-sankey) |
| Plotly Sankey | 2015 | MIT | [plotly.com docs](https://plotly.com/python/sankey-diagram/) |
| Sankeymatic | 2016 | MIT | [sankeymatic.com](https://sankeymatic.com/) · [GitHub](https://github.com/nowthis/sankeymatic) |
| Google Charts Sankey | 2014 | proprietary, freely documented | [developers.google.com/chart/sankey](https://developers.google.com/chart/interactive/docs/gallery/sankey) |

**DIG underlying library:** [d3/d3-sankey](https://github.com/d3/d3-sankey) (BSD-3-Clause)

### 6.1 Sankey UX Patterns

| Pattern | Predecessor | Link |
|---|---|---|
| Hover-tooltip with flow value | every Plotly/ECharts demo since launch | [ECharts Sankey events](https://echarts.apache.org/handbook/en/concepts/event/) |
| Click to isolate path | Total Sankey, Flourish Sankey templates | [total-sankey.vercel.app](https://total-sankey.vercel.app/) |
| Source→target gradient bands | d3-sankey gradient examples | [Observable example](https://observablehq.com/@d3/sankey-with-gradient) |
| Row-count badges directly on bands | Plotly + ECharts default render label option | [Plotly Sankey labels](https://plotly.com/python/sankey-diagram/) |
| Op-kind colour coding | KNIME node category colours, Dagster asset colours | [Dagster asset graph](https://docs.dagster.io/concepts/assets/software-defined-assets) |
| Sink filter (hide terminal nodes) | Tableau / Power BI filter pane patterns | [Power BI filters docs](https://learn.microsoft.com/en-us/power-bi/) |

---

## 7. Bipartite Computation Graphs (Column DNA-style)

Visual distinction between data nodes (rectangles) and operation nodes
(diamonds / chips) within a single graph.

| Predecessor | Year | License | Link |
|---|---|---|---|
| TensorBoard graph visualizer | 2015 | Apache 2.0 | [tensorflow.org/tensorboard/graphs](https://www.tensorflow.org/tensorboard/graphs) · [GitHub](https://github.com/tensorflow/tensorboard) |
| Theano computation graph (academic) | 2010 | BSD-3 | [Wikipedia](https://en.wikipedia.org/wiki/Theano_(software)) |
| PyTorch `torchviz` | 2018 | MIT | [GitHub](https://github.com/szagoruyko/pytorchviz) |
| Dataflow programming visualisation | foundational | various | [Wikipedia: Dataflow](https://en.wikipedia.org/wiki/Dataflow_programming) |
| Cheney provenance survey ("Provenance in Databases: Why, How, and Where") | 2009 | academic | [now publishers](https://www.nowpublishers.com/article/Details/DBS-007) |
| Trio system (Stanford) | 2002 | academic | [Stanford InfoLab](https://infolab.stanford.edu/trio/) |

---

## 8. Column-Level Lineage

Tracing an individual column back to its source columns through any
number of transformations.

| Predecessor | Year | License | Link |
|---|---|---|---|
| Apache Atlas | 2015 | Apache 2.0 | [atlas.apache.org](https://atlas.apache.org/) · [GitHub](https://github.com/apache/atlas) |
| OpenLineage spec | 2020 | Apache 2.0 | [openlineage.io](https://openlineage.io/) · [GitHub](https://github.com/OpenLineage/OpenLineage) |
| Marquez (LF AI & Data) | 2018 | Apache 2.0 | [GitHub](https://github.com/MarquezProject/marquez) |
| LinkedIn DataHub | 2019 | Apache 2.0 | [datahubproject.io](https://datahubproject.io/) · [GitHub](https://github.com/datahub-project/datahub) |
| dbt column-level lineage | 2022 | Apache 2.0 (manifest), proprietary (dbt Cloud UI) | [docs.getdbt.com](https://docs.getdbt.com/) |
| Provenance polynomials (Green & Karvounarakis) | 2007 | academic | [ACM PODS '07](https://dl.acm.org/doi/10.1145/1265530.1265535) |
| ProvDB (Database Group, Buneman et al.) | 2016 | academic | [University of Edinburgh page](https://homepages.inf.ed.ac.uk/jcheney/) |

### 8.1 Per-Row Lineage (DIG-distinctive — flag for FTO)

DIG's per-row lineage (every output row maps back to source rows) is
*less common in OSS* than column-level lineage. Prior art:

| Predecessor | Year | License | Link |
|---|---|---|---|
| Trio system — uncertainty + lineage at row level | 2002 | academic | [Stanford InfoLab](https://infolab.stanford.edu/trio/) |
| ORCHESTRA (Pennsylvania) | 2007 | academic | [Penn DB](https://db.cis.upenn.edu/Research/orchestra.html) |
| Cheney "Provenance in Databases" — covers row-level "where" / "why" | 2009 | academic | [now publishers](https://www.nowpublishers.com/article/Details/DBS-007) |
| Apache Spark lineage RDD (DAG of partitions) | 2014 | Apache 2.0 | [spark.apache.org](https://spark.apache.org/) |
| Polars `with_row_count()` for row tracking | 2020 | MIT | [GitHub](https://github.com/pola-rs/polars) |

> **FTO note:** This is one of three areas the prior-art-map flags as
> warranting a specific patent search before commercial deployment.

---

## 9. Cross-Pipeline Catalog (Workspace-Wide Lineage)

Meta-graph of pipelines connected by dataset references.

| Predecessor | Year | License | Link |
|---|---|---|---|
| Apache Atlas | 2015 | Apache 2.0 | [atlas.apache.org](https://atlas.apache.org/) |
| LinkedIn DataHub | 2019 | Apache 2.0 | [datahubproject.io](https://datahubproject.io/) |
| Marquez / OpenLineage | 2018 | Apache 2.0 | [marquez](https://github.com/MarquezProject/marquez) |
| Egeria (LF AI & Data) | 2018 | Apache 2.0 | [egeria-project.org](https://egeria-project.org/) |
| Amundsen (Lyft) | 2019 | Apache 2.0 | [GitHub](https://github.com/amundsen-io/amundsen) |
| Spline (ABSA, Spark lineage tracker) | 2018 | Apache 2.0 | [GitHub](https://github.com/AbsaOSS/spline) |

### 9.1 Column-Level Edges in a Catalog

| Predecessor | Year | License | Link |
|---|---|---|---|
| Apache Atlas column-level lineage | 2017 | Apache 2.0 | [atlas docs](https://atlas.apache.org/2.4.0/index.html) |
| OpenLineage column-level facets | 2022 | Apache 2.0 | [OpenLineage spec](https://openlineage.io/docs/spec/facets/) |
| dbt manifest `compiled_code` + ref graph | 2017 | Apache 2.0 | [dbt manifest schema](https://schemas.getdbt.com/) |

---

## 10. Run-State Visualization on Canvas

Colour-coding nodes by execution status (running / succeeded / failed).

| Predecessor | Year | License | Link |
|---|---|---|---|
| Apache Airflow Graph view | 2014 | Apache 2.0 | [airflow docs UI](https://airflow.apache.org/docs/apache-airflow/stable/ui.html) |
| Luigi central scheduler | 2012 | Apache 2.0 | [GitHub](https://github.com/spotify/luigi) |
| Dagster asset graph | 2018 | Apache 2.0 | [dagster docs](https://docs.dagster.io/) |
| Prefect Cloud flow run UI | 2020 | Apache 2.0 (core) | [docs.prefect.io](https://docs.prefect.io/) |
| Argo Workflows UI | 2017 | Apache 2.0 | [argo-workflows.readthedocs.io](https://argo-workflows.readthedocs.io/) |

---

## 11. Freshness / SLA Tracking

Tracking when each pipeline node / dataset was last updated, alerting
when overdue.

| Predecessor | Year | License | Link |
|---|---|---|---|
| dbt source freshness | 2018 | Apache 2.0 | [docs.getdbt.com sources](https://docs.getdbt.com/docs/build/sources#snapshotting-source-data-freshness) |
| Apache Atlas SLA support | 2017 | Apache 2.0 | [atlas.apache.org](https://atlas.apache.org/) |
| OpenLineage `dataset.versionFacet` | 2022 | Apache 2.0 | [OpenLineage spec](https://openlineage.io/docs/spec/facets/) |
| Cron expression + schedule monitors | 1987 | various | [Wikipedia: Cron](https://en.wikipedia.org/wiki/Cron) |

### 11.1 Halo / Outline Indicators on Graph Nodes

| Predecessor | Year | License | Link |
|---|---|---|---|
| Cytoscape.js node decorators | 2014 | MIT | [GitHub](https://github.com/cytoscape/cytoscape.js) |
| Dagster freshness-aware asset graph | 2022 | Apache 2.0 | [docs.dagster.io](https://docs.dagster.io/concepts/assets/asset-checks) |

> **FTO note:** Data-observability vendors (Monte Carlo, Datadog,
> Bigeye, Anomalo) have active patent filings around freshness +
> anomaly detection. The dbt-source-freshness Apache prior art covers
> the *concept*; jurisdiction-specific search recommended for the
> specific *halo + scanner-loop* combination before commercial deploy.

---

## 12. Data Quality Testing as Pipeline Steps

Inline assertions (`not_null`, `unique`, `between`, etc.) declared as
nodes in a pipeline.

| Predecessor | Year | License | Link |
|---|---|---|---|
| dbt tests | 2017 | Apache 2.0 | [docs.getdbt.com data tests](https://docs.getdbt.com/docs/build/data-tests) |
| Great Expectations | 2018 | Apache 2.0 | [GitHub](https://github.com/great-expectations/great_expectations) |
| Apache Griffin | 2016 | Apache 2.0 | [GitHub](https://github.com/apache/griffin) |
| Soda Core | 2021 | Apache 2.0 | [GitHub](https://github.com/sodadata/soda-core) |
| Deequ (Amazon, Spark-based) | 2018 | Apache 2.0 | [GitHub](https://github.com/awslabs/deequ) |
| TensorFlow Data Validation (TFDV) | 2018 | Apache 2.0 | [GitHub](https://github.com/tensorflow/data-validation) |
| Pandera | 2018 | MIT | [GitHub](https://github.com/unionai-oss/pandera) |
| Cerberus | 2014 | ISC | [GitHub](https://github.com/pyeve/cerberus) |

### 12.1 Specific check kinds DIG implements

| Check | Prior art |
|---|---|
| `not_null` | dbt `not_null` test, every SQL DBMS NOT NULL constraint |
| `unique` | dbt `unique` test, SQL UNIQUE constraint |
| `between` | dbt `accepted_range`, Pandera `Check.between`, GE `expect_column_values_to_be_between` |
| `in_set` | dbt `accepted_values`, Pandera `Check.isin`, GE `expect_column_values_to_be_in_set` |
| `regex` | GE `expect_column_values_to_match_regex`, Pandera `Check.str_matches` |
| `expression` | dbt singular tests, Pandera custom checks |

---

## 13. Notification System + Rule Engine

Event-driven notification with wildcards, filters, cooldowns, and
templates.

| Predecessor | Year | License | Link |
|---|---|---|---|
| Esper (Complex Event Processing) | 2006 | GPLv2 | [espertech.com](http://www.espertech.com/esper/) |
| Drools | 2001 | Apache 2.0 | [drools.org](https://www.drools.org/) · [GitHub](https://github.com/apache/incubator-kie-drools) |
| Apache Flink CEP | 2016 | Apache 2.0 | [flink.apache.org](https://flink.apache.org/) |
| PagerDuty event rules | 2009 | proprietary, freely documented | [pagerduty.com](https://www.pagerduty.com/docs/) |
| Sentry alerting rules | 2012 | BSL (Sentry self-hosted), freely documented | [sentry.io docs](https://docs.sentry.io/) |
| Prometheus AlertManager | 2015 | Apache 2.0 | [prometheus.io](https://prometheus.io/docs/alerting/latest/alertmanager/) |

---

## 14. In-Browser SQL / DataFrame Execution

Running SQL queries in the user's browser via WASM.

| Predecessor | Year | License | Link |
|---|---|---|---|
| sql.js (SQLite in browser) | 2014 | MIT | [GitHub](https://github.com/sql-js/sql.js) |
| DuckDB-WASM | 2021 | MIT | [duckdb.org/docs/api/wasm](https://duckdb.org/docs/api/wasm/overview) · [GitHub](https://github.com/duckdb/duckdb-wasm) |
| Pyodide (Python in browser) | 2018 | MPL 2.0 | [pyodide.org](https://pyodide.org/) · [GitHub](https://github.com/pyodide/pyodide) |
| Apache Arrow JavaScript | 2017 | Apache 2.0 | [arrow.apache.org/docs/js](https://arrow.apache.org/docs/js/) |

**DIG underlying library:** [duckdb/duckdb-wasm](https://github.com/duckdb/duckdb-wasm) (MIT)

---

## 15. Backend Data Engine

Server-side dataframe processing for larger-than-browser datasets.

| Predecessor | Year | License | Link |
|---|---|---|---|
| pandas | 2008 | BSD-3 | [pandas.pydata.org](https://pandas.pydata.org/) |
| Apache Spark | 2009 | Apache 2.0 | [spark.apache.org](https://spark.apache.org/) |
| Polars | 2020 | MIT | [pola.rs](https://pola.rs/) · [GitHub](https://github.com/pola-rs/polars) |
| DuckDB | 2018 | MIT | [duckdb.org](https://duckdb.org/) · [GitHub](https://github.com/duckdb/duckdb) |
| Dask | 2014 | BSD-3 | [dask.org](https://www.dask.org/) |

**DIG underlying libraries:** [Polars](https://github.com/pola-rs/polars) + [DuckDB](https://github.com/duckdb/duckdb)

---

## 16. Group / Subgraph / Compound Node Patterns

Treating a cluster of nodes as a single visual unit that can be expanded
or collapsed.

| Predecessor | Year | License | Link |
|---|---|---|---|
| KNIME metanodes | 2007 | GPLv3 | [KNIME docs](https://docs.knime.com/2017-12/analytics_platform_metanodes_guide/index.html) |
| Apache NiFi process groups | 2014 | Apache 2.0 | [nifi.apache.org docs](https://nifi.apache.org/docs.html) |
| Cytoscape.js compound nodes | 2014 | MIT | [js.cytoscape.org/#notation](https://js.cytoscape.org/#notation/elements-json) |
| Graphviz subgraphs (`cluster_*`) | 1991 | EPL 1.0 | [graphviz.org](https://graphviz.org/Gallery/directed/cluster.html) |
| Dagster asset groups | 2022 | Apache 2.0 | [docs.dagster.io](https://docs.dagster.io/concepts/assets/software-defined-assets#assigning-asset-keys-and-groups) |
| xyflow group node example | 2022 | MIT | [reactflow.dev examples](https://reactflow.dev/examples/layout/sub-flows) |

---

## 17. Mini-map / Overview Pane

Small overview rectangle showing the whole graph + current viewport.

| Predecessor | Year | License | Link |
|---|---|---|---|
| Adobe Photoshop Navigator panel | 1990 | proprietary | [Wikipedia: Adobe Photoshop history](https://en.wikipedia.org/wiki/Adobe_Photoshop) |
| AutoCAD aerial view | 1982 | proprietary | [Wikipedia: AutoCAD](https://en.wikipedia.org/wiki/AutoCAD) |
| Cytoscape.js navigator extension | 2014 | MIT | [GitHub](https://github.com/cytoscape/cytoscape.js-navigator) |
| xyflow `<MiniMap>` component | 2022 | MIT | [reactflow.dev/api/components/minimap](https://reactflow.dev/api-reference/components/minimap) |

**DIG underlying component:** xyflow's `<MiniMap>` (MIT)

---

## 18. Zoom + Pan on SVG / Canvas

Wheel-zoom and drag-pan over a viewport.

| Predecessor | Year | License | Link |
|---|---|---|---|
| d3-zoom | 2011 | BSD-3 / ISC | [GitHub](https://github.com/d3/d3-zoom) |
| svg-pan-zoom | 2009 | BSD-2 | [GitHub](https://github.com/bumbu/svg-pan-zoom) |
| Apple Safari pinch-zoom (Web standard) | 2007 | open standard | [W3C: Pointer Events](https://www.w3.org/TR/pointerevents/) |

**DIG underlying library:** [d3/d3-zoom](https://github.com/d3/d3-zoom) (BSD-3)

---

## 19. Annotation Pins on Visualisations

Drop a note on a chart element; persist locally or to the document.

| Predecessor | Year | License | Link |
|---|---|---|---|
| Tableau annotations | 2003 | proprietary, freely documented | [tableau.com docs](https://help.tableau.com/) |
| Power BI insights | 2014 | proprietary | [Microsoft docs](https://learn.microsoft.com/en-us/power-bi/) |
| Plotly annotations | 2015 | MIT | [plotly.com docs](https://plotly.com/python/text-and-annotations/) |
| Vega-Lite annotation marks | 2017 | BSD-3 | [vega.github.io/vega-lite](https://vega.github.io/vega-lite/) |
| Hypothes.is web annotation | 2011 | BSD-2 | [hypothes.is](https://hypothes.is/) |

---

## 20. Schema Diff / Cell-Level Highlights

Highlighting added / removed / renamed columns between consecutive
preview runs.

| Predecessor | Year | License | Link |
|---|---|---|---|
| GNU `diff` | 1974 | GPL | [Wikipedia: diff](https://en.wikipedia.org/wiki/Diff) |
| GitHub diff view | 2008 | proprietary, freely documented | [github.com](https://github.com/) |
| `daff` (data diff) | 2014 | MIT | [GitHub](https://github.com/paulfitz/daff) |
| OpenRefine reconciliation views | 2010 | BSD-3 | [openrefine.org](https://openrefine.org/) |
| dbt `state:modified` | 2019 | Apache 2.0 | [dbt state docs](https://docs.getdbt.com/reference/node-selection/state-comparison) |

---

## 21. AI / NL-to-Pipeline Translation

Natural-language requests turned into pipeline steps.

| Predecessor | Year | License | Link |
|---|---|---|---|
| OpenAI function calling | 2023 | proprietary, openly documented | [platform.openai.com](https://platform.openai.com/docs/guides/function-calling) |
| LangChain | 2022 | MIT | [GitHub](https://github.com/langchain-ai/langchain) |
| LlamaIndex | 2022 | MIT | [GitHub](https://github.com/run-llama/llama_index) |
| Anthropic tool use | 2024 | proprietary, openly documented | [docs.anthropic.com tool use](https://docs.anthropic.com/en/docs/build-with-claude/tool-use) |

> **FTO note:** AI-assisted data preparation has active patents at
> several incumbents. DIG's AI assistant deliberately avoids any
> "predictive transformation suggestion" UX whose mechanisms have
> been patented; the assistant sketches structural pipeline edits on
> request and surfaces them through the normal review/diff/install
> flow that every other DIG action uses.

---

## 22. Run History / Replay

Timeline of pipeline executions with metrics + drill-down.

| Predecessor | Year | License | Link |
|---|---|---|---|
| Apache Airflow DAG runs UI | 2014 | Apache 2.0 | [Airflow UI docs](https://airflow.apache.org/docs/apache-airflow/stable/ui.html) |
| Dagster run timeline | 2018 | Apache 2.0 | [docs.dagster.io](https://docs.dagster.io/) |
| Jupyter notebook execution history | 2014 | BSD-3 | [jupyter.org](https://jupyter.org/) |

---

## 23. Webhook / External-Channel Notifications

Forwarding events to Slack, email, generic HTTP endpoints.

| Predecessor | Year | License | Link |
|---|---|---|---|
| Slack incoming webhooks | 2013 | proprietary | [api.slack.com webhooks](https://api.slack.com/messaging/webhooks) |
| GitHub webhooks | 2008 | proprietary, freely documented | [docs.github.com webhooks](https://docs.github.com/en/webhooks) |
| Sentry integrations | 2012 | BSL | [sentry.io integrations](https://docs.sentry.io/product/integrations/) |
| AWS EventBridge | 2019 | proprietary | [aws.amazon.com/eventbridge](https://aws.amazon.com/eventbridge/) |

---

## 24. Per-Step Validation Queries

Step-level metric collection that runs alongside the data and produces
audit rows.

| Predecessor | Year | License | Link |
|---|---|---|---|
| Apache Spark `df.summary()` / `.describe()` | 2014 | Apache 2.0 | [Spark docs](https://spark.apache.org/) |
| dbt audit_helper | 2018 | Apache 2.0 | [hub.getdbt.com audit_helper](https://hub.getdbt.com/dbt-labs/audit_helper/latest/) |
| Great Expectations checkpoint actions | 2019 | Apache 2.0 | [GE checkpoints](https://docs.greatexpectations.io/) |

---

## 25. Pipeline-as-Code (YAML / JSON Document)

Persisting the pipeline structure as a serialisable document with steps,
inputs, outputs, datasets.

| Predecessor | Year | License | Link |
|---|---|---|---|
| dbt `dbt_project.yml` + model files | 2016 | Apache 2.0 | [docs.getdbt.com projects](https://docs.getdbt.com/docs/build/projects) |
| Apache Airflow DAG-as-Python | 2014 | Apache 2.0 | [airflow docs](https://airflow.apache.org/docs/apache-airflow/stable/concepts.html#dags) |
| Argo Workflows YAML | 2017 | Apache 2.0 | [argo-workflows examples](https://github.com/argoproj/argo-workflows/tree/main/examples) |
| GitLab CI YAML | 2014 | MIT | [docs.gitlab.com](https://docs.gitlab.com/ee/ci/) |
| GitHub Actions YAML | 2018 | proprietary, freely documented | [docs.github.com actions](https://docs.github.com/en/actions) |
| Prefect flow definitions | 2018 | Apache 2.0 | [docs.prefect.io](https://docs.prefect.io/) |

---

## 26. Pipeline Diff / Comparison

Showing two pipeline documents side-by-side with structural changes.

| Predecessor | Year | License | Link |
|---|---|---|---|
| GNU `diff` | 1974 | GPL | [Wikipedia](https://en.wikipedia.org/wiki/Diff) |
| jsondiffpatch | 2012 | MIT | [GitHub](https://github.com/benjamine/jsondiffpatch) |
| dbt `dbt run --select state:modified+` | 2019 | Apache 2.0 | [dbt state](https://docs.getdbt.com/reference/node-selection/state-comparison) |

---

## 27. Notebook Export (Python / .ipynb)

Generating a runnable Jupyter notebook from a visual pipeline.

| Predecessor | Year | License | Link |
|---|---|---|---|
| KNIME → Python script export | 2017 | GPLv3 | [KNIME docs](https://docs.knime.com/) |
| Alteryx → Python script via Code Tool | various | proprietary | (general industry pattern) |
| nbconvert | 2014 | BSD-3 | [GitHub](https://github.com/jupyter/nbconvert) |
| Papermill | 2018 | BSD-3 | [GitHub](https://github.com/nteract/papermill) |
| Jupytext (paired notebook ↔ script) | 2018 | MIT | [GitHub](https://github.com/mwouts/jupytext) |

---

## 28. Edit-Time Impact / "What Will This Break"

Showing downstream consumer count when editing a step / column.

| Predecessor | Year | License | Link |
|---|---|---|---|
| dbt `dbt run --select +my_model+` (impact analysis) | 2019 | Apache 2.0 | [dbt model selection](https://docs.getdbt.com/reference/node-selection/syntax) |
| IDE "find references" / "find usages" | 1990s | various | [Wikipedia: IDE](https://en.wikipedia.org/wiki/Integrated_development_environment) |
| Datafold data diff | 2020 | Apache 2.0 | [GitHub](https://github.com/datafold/data-diff) |

---

## 29. Step Categorisation + Search (cmdk Palette)

Searchable command palette for adding steps.

| Predecessor | Year | License | Link |
|---|---|---|---|
| Sublime Text command palette | 2008 | proprietary, copy-prompted GitHub Atom (open) | [sublimetext.com](https://www.sublimetext.com/) |
| GitHub Atom command palette | 2014 | MIT | [atom.io archive](https://atom-archive.github.io/) |
| VS Code command palette | 2015 | MIT | [github.com/microsoft/vscode](https://github.com/microsoft/vscode) |
| `cmdk` library | 2022 | MIT | [GitHub](https://github.com/pacocoursey/cmdk) |

**DIG underlying library:** [cmdk](https://github.com/pacocoursey/cmdk) (MIT)

---

## 30. Toast / Sonner Notifications

Transient bottom-corner notifications.

| Predecessor | Year | License | Link |
|---|---|---|---|
| iOS toast notifications (UIAlertView) | 2007 | proprietary | (Apple Human Interface Guidelines) |
| Android Toast | 2008 | Apache 2.0 (AOSP) | [developer.android.com](https://developer.android.com/) |
| react-toastify | 2017 | MIT | [GitHub](https://github.com/fkhadra/react-toastify) |
| sonner | 2023 | MIT | [GitHub](https://github.com/emilkowalski/sonner) |

**DIG underlying library:** [sonner](https://github.com/emilkowalski/sonner) (MIT)

---

## 31. Web UI Stack

| Layer | Library | License | Link |
|---|---|---|---|
| App framework | Next.js | MIT | [GitHub](https://github.com/vercel/next.js) |
| UI library | React | MIT | [GitHub](https://github.com/facebook/react) |
| Styling | Tailwind CSS | MIT | [GitHub](https://github.com/tailwindlabs/tailwindcss) |
| Animation | Motion (formerly Framer Motion) | MIT | [GitHub](https://github.com/motiondivision/motion) |
| Data flow canvas | xyflow | MIT | [GitHub](https://github.com/xyflow/xyflow) |
| Charting | d3 (sankey, zoom, selection) | BSD-3 / ISC | [d3js.org](https://d3js.org/) |
| Forms / state | TanStack Query | MIT | [GitHub](https://github.com/TanStack/query) |

---

## 32. Backend Stack

| Layer | Library | License | Link |
|---|---|---|---|
| API framework | FastAPI | MIT | [GitHub](https://github.com/fastapi/fastapi) |
| ORM | SQLAlchemy | MIT | [GitHub](https://github.com/sqlalchemy/sqlalchemy) |
| Validation | Pydantic | MIT | [GitHub](https://github.com/pydantic/pydantic) |
| Server | Uvicorn | BSD-3 | [GitHub](https://github.com/encode/uvicorn) |
| DataFrame engine | Polars | MIT | [GitHub](https://github.com/pola-rs/polars) |
| SQL engine | DuckDB | MIT | [GitHub](https://github.com/duckdb/duckdb) |

---

## 33. Run history / job listing

A list-of-runs UI with status / time / pipeline filtering, click-to-detail.

| Predecessor | Year | License | Link |
|---|---|---|---|
| Apache Airflow DagRun list | 2014 | Apache 2.0 | [Airflow UI docs](https://airflow.apache.org/docs/apache-airflow/stable/ui.html) |
| Dagster runs page | 2018 | Apache 2.0 | [Dagster docs](https://docs.dagster.io/concepts/runs/runs) |
| Prefect Cloud flow runs | 2020 | Apache 2.0 (core) | [Prefect docs](https://docs.prefect.io/latest/concepts/flows/) |
| Argo Workflows UI | 2017 | Apache 2.0 | [argo-workflows.readthedocs.io](https://argo-workflows.readthedocs.io/) |
| GitHub Actions workflow runs | 2018 | proprietary, freely documented | [docs.github.com actions](https://docs.github.com/en/actions) |
| GitLab CI/CD pipelines | 2014 | MIT | [docs.gitlab.com](https://docs.gitlab.com/ee/ci/) |
| Jenkins build history | 2004 | MIT | [jenkins.io](https://www.jenkins.io/) |
| Snowflake `QUERY_HISTORY` view | 2014 | proprietary, schema documented | [docs.snowflake.com QUERY_HISTORY](https://docs.snowflake.com/en/sql-reference/account-usage/query_history) |

### 33.1 Run-detail drill-down with timeline

| Predecessor | Year | License | Link |
|---|---|---|---|
| Dagster timeline view | 2018 | Apache 2.0 | [Dagster docs](https://docs.dagster.io/) |
| Jupyter notebook execution view | 2014 | BSD-3 | [jupyter.org](https://jupyter.org/) |
| GitHub Actions workflow visualisation | 2022 | proprietary | [GitHub blog](https://github.blog/changelog/) |

### 33.2 Cursor pagination on run lists

| Predecessor | Year | License | Link |
|---|---|---|---|
| GraphQL Cursor Connections spec | 2015 | OWFa 1.0 | [Relay docs](https://relay.dev/graphql/connections.htm) |
| Stripe API pagination | 2011 | proprietary, openly documented | [stripe.com docs](https://stripe.com/docs/api/pagination) |

---

## 34. OpenLineage emission

Standardised event model for run lifecycle + dataset shape.

| Predecessor | Year | License | Link |
|---|---|---|---|
| OpenLineage spec | 2020 | Apache 2.0 | [openlineage.io](https://openlineage.io/) · [GitHub](https://github.com/OpenLineage/OpenLineage) |
| Marquez (LF AI & Data, reference impl) | 2018 | Apache 2.0 | [GitHub](https://github.com/MarquezProject/marquez) |
| Apache Atlas notification model | 2015 | Apache 2.0 | [atlas.apache.org](https://atlas.apache.org/) |
| Egeria event protocol | 2018 | Apache 2.0 | [egeria-project.org](https://egeria-project.org/) |
| Spline (ABSA Spark lineage tracker) | 2018 | Apache 2.0 | [GitHub](https://github.com/AbsaOSS/spline) |
| OpenLineage Airflow integration | 2021 | Apache 2.0 | [GitHub](https://github.com/OpenLineage/OpenLineage/tree/main/integration/airflow) |
| OpenLineage dbt integration | 2021 | Apache 2.0 | [GitHub](https://github.com/OpenLineage/OpenLineage/tree/main/integration/dbt) |

OpenLineage facets DIG emits:

| Facet | Source | Link |
|---|---|---|
| `SchemaDatasetFacet` | OpenLineage spec | [spec link](https://openlineage.io/docs/spec/facets/dataset-facets/schema) |
| `DataQualityMetricsInputDatasetFacet` | OpenLineage spec | [spec link](https://openlineage.io/docs/spec/facets/dataset-facets/data-quality-metrics) |
| `ColumnLineageDatasetFacet` | OpenLineage spec | [spec link](https://openlineage.io/docs/spec/facets/dataset-facets/column-lineage-facet) |
| `OutputStatisticsOutputDatasetFacet` | OpenLineage spec | [spec link](https://openlineage.io/docs/spec/facets/dataset-facets/output-statistics) |

DIG-specific facets (custom keys under `facets`) — non-standard, free
to define per the spec's extensibility rules.

---

## 35. Pluggable storage backends

Abstraction over local filesystem, S3, GCS, Azure Blob, MinIO, NFS.

| Predecessor | Year | License | Link |
|---|---|---|---|
| fsspec (Filesystem Spec) | 2018 | BSD-3 | [GitHub](https://github.com/fsspec/filesystem_spec) |
| s3fs (fsspec adapter) | 2016 | BSD-3 | [GitHub](https://github.com/fsspec/s3fs) |
| gcsfs | 2017 | BSD-3 | [GitHub](https://github.com/fsspec/gcsfs) |
| Apache Arrow filesystems | 2019 | Apache 2.0 | [arrow.apache.org docs](https://arrow.apache.org/docs/python/filesystems.html) |
| Hadoop FileSystem interface (`org.apache.hadoop.fs.FileSystem`) | 2006 | Apache 2.0 | [hadoop.apache.org](https://hadoop.apache.org/) |
| Java NIO `FileSystem` | 2011 | OpenJDK GPL+CE | [openjdk.org](https://openjdk.org/) |
| URI scheme (RFC 3986) | 2005 | open standard | [datatracker.ietf.org](https://datatracker.ietf.org/doc/html/rfc3986) |

URI-as-reference (`file://`, `s3://`, `gs://`, `azure://`) has decades
of prior art; the storage abstraction in DIG composes existing
fsspec / Arrow primitives.

---

## 36. Reference data tracking (input + output schemas)

Capturing the schema of data DIG **reads** at ingest AND **writes** at
output, so each run records both shapes regardless of source-database
schema variance.

| Predecessor | Year | License | Link |
|---|---|---|---|
| Apache Atlas dataset facets | 2015 | Apache 2.0 | [atlas.apache.org](https://atlas.apache.org/) |
| OpenLineage `SchemaDatasetFacet` | 2020 | Apache 2.0 | [spec link](https://openlineage.io/docs/spec/facets/dataset-facets/schema) |
| Apache Iceberg schema evolution | 2018 | Apache 2.0 | [iceberg.apache.org](https://iceberg.apache.org/) |
| Apache Avro schema | 2009 | Apache 2.0 | [avro.apache.org](https://avro.apache.org/) |
| Apache Parquet schema | 2013 | Apache 2.0 | [parquet.apache.org](https://parquet.apache.org/) |
| Schema-on-read (Hadoop pattern) | 2008 | Apache 2.0 ecosystem | [Wikipedia: Schema on read](https://en.wikipedia.org/wiki/Schema-on-read) |
| dbt manifest column-level schema | 2017 | Apache 2.0 | [dbt manifest schema](https://schemas.getdbt.com/) |
| Marquez dataset versioning | 2018 | Apache 2.0 | [GitHub](https://github.com/MarquezProject/marquez) |
| Provenance polynomials (Green/Karvounarakis) | 2007 | academic | [ACM PODS '07](https://dl.acm.org/doi/10.1145/1265530.1265535) |

The pattern of "record the schema at read time even when the source is
variable" is the schema-on-read principle, foundational to the entire
Hadoop / data-lake era. DIG's `InputRef.schema` records what was
ACTUALLY observed; `OutputRef.schema` records what was ACTUALLY
written. Both belong to the run record.

---

## 37. Run retention policies

Time-based or count-based deletion of run history.

| Predecessor | Year | License | Link |
|---|---|---|---|
| `logrotate` | 1992 | GPLv2 | [linux.die.net/man/8/logrotate](https://linux.die.net/man/8/logrotate) |
| AWS S3 Lifecycle policies | 2011 | proprietary, openly documented | [docs.aws.amazon.com S3 lifecycle](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lifecycle-mgmt.html) |
| Apache Airflow `log_retention_days` | 2014 | Apache 2.0 | [airflow.apache.org](https://airflow.apache.org/) |
| Dagster run retention | 2020 | Apache 2.0 | [docs.dagster.io](https://docs.dagster.io/concepts/dagster-instance) |
| Prometheus `--storage.tsdb.retention.time` | 2015 | Apache 2.0 | [prometheus.io](https://prometheus.io/docs/prometheus/latest/storage/) |
| `find -mtime -delete` (Unix) | 1971 | various | [GNU find docs](https://www.gnu.org/software/findutils/) |

Retention as "delete records older than N" is foundational sysadmin
hygiene with Unix `find`-era prior art.

---

## 38. Tier separation (free / enterprise)

Single-codebase delivery of a free tier (open-source) and an enterprise
tier (commercial license) via configuration switches + license tokens.

| Predecessor | Year | License | Link |
|---|---|---|---|
| GitLab Community vs Enterprise Edition | 2013 | MIT (CE) + commercial (EE) | [about.gitlab.com](https://about.gitlab.com/install/ce-or-ee/) |
| Sentry self-hosted (FOSS → BSL transition) | 2008 → 2019 | BSD → BSL | [blog.sentry.io](https://blog.sentry.io/2019/11/06/relicensing-sentry/) |
| Confluent Platform (Kafka + tiers) | 2014 | Apache 2.0 + Confluent Community Licence | [confluent.io](https://www.confluent.io/) |
| HashiCorp products (Terraform / Vault / Consul) | 2014 → 2023 | MPL 2.0 → BSL | [hashicorp.com](https://www.hashicorp.com/) |
| Elasticsearch (Apache 2.0 → SSPL/Elastic License) | 2010 → 2021 | Apache 2.0 → SSPL+ELv2 | [elastic.co/blog](https://www.elastic.co/blog/why-license-change-aws) |
| MongoDB Community vs Enterprise | 2009 | SSPL (community) + commercial | [mongodb.com](https://www.mongodb.com/) |
| dbt-core (Apache 2.0) vs dbt Cloud | 2018 | Apache 2.0 + commercial | [getdbt.com](https://www.getdbt.com/) |
| Cal.com (open core) | 2021 | AGPL-3.0 | [GitHub](https://github.com/calcom/cal.com) |
| PostHog (open core) | 2020 | MIT (free) + commercial (paid) | [posthog.com](https://posthog.com/) |
| Strapi (open core) | 2015 | MIT + Enterprise Edition | [strapi.io](https://strapi.io/) |
| Astronomer (Airflow + commercial wrapper) | 2018 | Apache 2.0 + commercial | [astronomer.io](https://www.astronomer.io/) |

The "single codebase, tier flag, license token" architecture is the
de-facto standard for commercial open-source. DIG follows the
GitLab + Sentry model: protocol-based abstractions, single DB schema
with nullable enterprise columns, lazy import of enterprise modules.

---

## 39. Cost / usage tracking columns

Nullable columns on a run record for bytes scanned, compute seconds, cost.

| Predecessor | Year | License | Link |
|---|---|---|---|
| Snowflake `QUERY_HISTORY.bytes_scanned` etc. | 2014 | proprietary, schema documented | [docs.snowflake.com](https://docs.snowflake.com/en/sql-reference/account-usage/query_history) |
| BigQuery `INFORMATION_SCHEMA.JOBS_BY_PROJECT.total_bytes_billed` | 2017 | proprietary, schema documented | [cloud.google.com docs](https://cloud.google.com/bigquery/docs/information-schema-jobs) |
| AWS Cost Explorer | 2017 | proprietary | [aws.amazon.com](https://aws.amazon.com/aws-cost-management/aws-cost-explorer/) |
| Apache Airflow task duration metrics | 2014 | Apache 2.0 | [airflow.apache.org](https://airflow.apache.org/) |
| `time(1)` Unix command | 1973 | various | [POSIX time(1)](https://pubs.opengroup.org/onlinepubs/9699919799/utilities/time.html) |

DIG records nullable cost columns on each run row. Surfacing these
numbers to the operator follows decades of prior art (Unix `time`
1973). Pattern-based optimisation recommendations *generated from*
those numbers (Snowflake / Datadog patents) are deliberately not
part of DIG.

---

## Summary

DIG composes well-established open-source primitives into a particular
visual + workflow opinion. The high-confidence "this is well-trodden
ground" categories are §§ 1, 2, 3, 4, 5, 6, 12, 13, 14, 15, 16, 17, 18,
19, 20, 22, 23, 24, 25, 26, 27, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38,
39 — which is most of the product surface.

The three categories where the prior-art chain is comparatively thin
and a real FTO search is recommended before commercial deployment are
called out inline:

1. **§ 8.1 Per-row lineage** — academic prior art is solid; commercial
   patents (Manta, Talend, Informatica) warrant specific search.
2. **§ 11 Freshness halos + scanner loop** — dbt-source-freshness is
   the closest open-source predecessor; data-observability vendors
   (Monte Carlo, Datadog) have active filings.
3. **§ 21 AI-assisted transforms** — Trifacta / Alteryx hold patents
   here; DIG's AI assistant must avoid replicating patented
   "predictive transformation suggestion" mechanisms.

DIG combines a few elements not commonly seen together in prior art:
compare-runs delta rendered on a Sankey; bipartite Column DNA with
toggleable upstream/downstream walk; an edit-time column-impact chip
linked to interactive lineage drill-through. The maintainers
publish these combinations defensively to keep the design space open.

---

*Document maintained by the DataInsightGrove maintainers. Add new rows
when shipping a feature whose technique is not already covered.*

## Maintenance protocol

When adding a new system / feature to DIG:

1. Decide which existing § the technique fits under, OR open a new §
   if it's a category not represented yet.
2. List ≥ 2 unrelated prior-art predecessors (academic + open-source
   is ideal). Prefer permanent citable URLs (project repos, archived
   papers, Wikipedia revisions); avoid blog posts that rotate.
3. If the new system has a free-tier ↔ enterprise split, note in the
   entry which tier it lands in. Patent-adjacent
   techniques typically gate to enterprise; classical statistics +
   foundational primitives stay free.
4. Cross-link from the implementation's docstring back to the § here.
5. Update the [`Summary`](#summary) section's "well-trodden ground"
   list to include the new §.

This document is **continuously maintained** alongside the code. A PR
that adds a new technique without a matching prior-art row should be
flagged in review.
