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
