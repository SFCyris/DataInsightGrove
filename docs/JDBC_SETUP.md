# JDBC ingress / egress

DIG ships with two artifacts that bridge to any JDBC-accessible database:

- **`jdbc` connector** — read tables / queries as a dataset (ingress)
- **`export_to_jdbc` step** — write rows back to a database (egress)

This covers the long tail of enterprise databases: Oracle, DB2, MS SQL
Server, Snowflake, Teradata, Vertica, SAP HANA, Hyperion, Informix, etc.
For Postgres / MySQL / SQLite, prefer the dedicated native-driver
connectors and the `export_to_db` step — they're lighter (no JVM) and
faster.

## Prerequisites

1. **Java runtime (JRE 8 or newer)** on `PATH`.
   - macOS: `brew install --cask temurin`
   - Linux: `apt install default-jre` / `dnf install java-latest-openjdk`
   - Windows: <https://adoptium.net/>
2. **Python extras**: `pip install -e .[jdbc]` (installs `JPype1` and
   `jaydebeapi`). JPype1 builds a CPython↔JVM bridge from source on first
   install — ensure `cmake` is available. Wheels are published for many
   platforms; if pip can't find one, install CMake (`brew install cmake` /
   `apt install cmake`) before retrying.
3. **JDBC driver JAR** for your database. Download from the vendor:
   - PostgreSQL: <https://jdbc.postgresql.org/download/>
   - MySQL: <https://dev.mysql.com/downloads/connector/j/>
   - Oracle: <https://www.oracle.com/database/technologies/appdev/jdbc-downloads.html>
   - MS SQL Server: <https://learn.microsoft.com/sql/connect/jdbc/microsoft-jdbc-driver-for-sql-server>
   - Snowflake: <https://docs.snowflake.com/en/developer-guide/jdbc/jdbc>
   - DB2: <https://www.ibm.com/support/pages/db2-jdbc-driver-versions-and-downloads>

   Drop them in a folder you control — for example `~/dig-drivers/` —
   and reference it from the connector / step config. `jarPath` accepts
   either a single `.jar` file or a directory containing one or more.

## Ingress — `jdbc` connector

Add a dataset of type `jdbc` to your pipeline. Required fields:

| Field          | Example                                            |
| -------------- | -------------------------------------------------- |
| URI            | `jdbc:oracle:thin:@//host:1521/ORCL`               |
| `driverClass`  | `oracle.jdbc.OracleDriver`                         |
| `jarPath`      | `/Users/me/dig-drivers/ojdbc11.jar`                |
| `username`     | `analytics_ro`                                     |
| `password`     | `${ORA_PASS}` *(env-var interpolation supported)*  |
| `table`  *or*  | `analytics.orders`                                 |
| `query`        | `SELECT * FROM analytics.orders WHERE ts > …`      |

Either `table` or `query` is required — not both.

### Common driver classes

| Database             | URL prefix                       | Driver class                                       |
| -------------------- | -------------------------------- | -------------------------------------------------- |
| Oracle               | `jdbc:oracle:thin:@…`            | `oracle.jdbc.OracleDriver`                         |
| MS SQL Server        | `jdbc:sqlserver://…`             | `com.microsoft.sqlserver.jdbc.SQLServerDriver`     |
| DB2                  | `jdbc:db2://…`                   | `com.ibm.db2.jcc.DB2Driver`                        |
| Snowflake            | `jdbc:snowflake://…`             | `net.snowflake.client.jdbc.SnowflakeDriver`        |
| Teradata             | `jdbc:teradata://…`              | `com.teradata.jdbc.TeraDriver`                     |
| Vertica              | `jdbc:vertica://…`               | `com.vertica.jdbc.Driver`                          |
| Postgres *(via JDBC)*| `jdbc:postgresql://…`            | `org.postgresql.Driver`                            |
| MySQL *(via JDBC)*   | `jdbc:mysql://…`                 | `com.mysql.cj.jdbc.Driver`                         |

## Egress — `export_to_jdbc` step

Add an `export_to_jdbc` step to your pipeline. Same auth / driver fields
as the connector, plus:

- **`table`** — schema-qualify if needed (`analytics.daily_snapshot`).
- **`mode`**:
  - `append` — INSERT only. Table must already exist.
  - `truncate_then_append` — TRUNCATE TABLE, then INSERT. Schema
    unchanged.
  - `drop_and_create` — DROP TABLE IF EXISTS, CREATE TABLE from the
    Polars frame's schema (BIGINT / DOUBLE PRECISION / VARCHAR(4000) /
    BOOLEAN / DATE / TIMESTAMP), then INSERT. **Useful for ad-hoc
    snapshot tables. Don't use against production schemas — vendor type
    nuances aren't represented.** Some databases (Oracle pre-23c) don't
    support `DROP TABLE IF EXISTS`; on those, create the table by hand
    once and use `truncate_then_append` afterwards.
- **`batchSize`** — rows per `executemany()` call. Default 1000. Bigger
  is faster, smaller uses less memory.

## Secrets

`password` accepts `${ENV_VAR}` interpolation. Recommended:

```text
DIG_AUTH_TOKEN=...
ORA_PASS=...
SNOWFLAKE_PASS=...
```

…then put `${ORA_PASS}` in the pipeline's password field. The pipeline
JSON travels safely between machines without the secret.

`X-DIG-Signature: sha256=<hex>` is sent by the **webhook** dispatcher
(separate feature) — JDBC auth happens through the JDBC driver itself
and does not surface that header.

## Troubleshooting

- **`ModuleNotFoundError: jaydebeapi`** — install `[jdbc]` extra.
- **`Failed to start JVM`** — ensure a JRE is on PATH (`java -version`).
- **`No suitable driver`** — `driverClass` doesn't match the URL prefix,
  or the JAR isn't on the classpath. Verify `jarPath` exists and the
  class name matches the vendor docs.
- **`Could not find or load main class`** — JAR is for a Java version
  newer than your JRE. Install a newer JRE or download an older driver.
