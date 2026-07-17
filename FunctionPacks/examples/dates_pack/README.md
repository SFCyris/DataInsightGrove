# 📅 `dates_pack` · order-processing flow

**Scenario:** an order ledger with `order_date` and `ship_date`. We
need to:
1. Tag each order with its US-federal fiscal year (starts October).
2. Compute business-day shipping latency, skipping US holidays.
3. Snap orders to start-of-week for weekly cohort reports.

**Data** (`data.csv`, 15 rows): `order_id, order_date, ship_date, amount_usd`.
Includes orders that span the holidays (A-002 ships across Christmas;
A-012 ships across Christmas + New Year — the business-day count
should reflect the holiday skip).

## What the flow shows

```
ds → cast(order_date) → cast(ship_date)
        → fiscal_year_parts(order_date, fy_start=10)
        → business_days_between(order, ship, country=US)
        → date_snap(order_date, period=week)
```

Result: each row gains `fy_year` / `fy_quarter` / `fy_month`,
`ship_bdays` (1-3 typical, more across holiday weeks), and
`order_week` (Monday-anchored).

| Order | Spans | Calendar days | Business days |
|-------|-------|---------------|--------------|
| A-002 | Dec 23 → Dec 29 | 6 | 2 (Christmas + weekend skipped) |
| A-012 | Dec 22 → Dec 29 | 7 | 3 |
| A-013 | Dec 31 → Jan 5  | 5 | 2 (New Year's Day) |

## How to load

The fastest path — uploads the CSV, substitutes the placeholders in
`flow.dig.json`, and creates the pipeline:

```bash
python3 FunctionPacks/scripts/import_example.py dates_pack
```

It prints a `http://localhost:3100/pipelines/<id>` URL — open it.

If you'd rather build the flow by hand, see the index in
`examples/README.md` → "Manual recreation".
