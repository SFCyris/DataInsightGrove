# 📚 `reference_data` · canonical locale lookups

**Scenario:** a user table where country, currency, and timezone are
recorded in arbitrary forms — alpha-2, alpha-3, numeric, or name.
Downstream joins / dashboards need canonical ISO codes.

**Data** (`data.csv`, 15 rows): `user_id, country_input, currency_input, timezone_input`.
- Country: `US`, `GB`, `DEU`, `392` (numeric Japan), `Brazil`, `France`, …
- Currency: `USD`, `GBP`, `EUR`, `978` (numeric EUR), …
- Timezone: IANA names, plus one deliberately broken (`America/Notarealzone`)

## What the flow shows

```
ds → country_lookup    → adds country_alpha2 / alpha3 / name / numeric / official
   → currency_lookup   → adds currency_code / name / numeric
   → timezone_resolve  → adds timezone_valid / canonical / offset_minutes
```

After the flow:
- Every row has a normalised set of locale fields.
- The `XX` / `XXX` / bad-timezone row (user 11) gets nulls + `_valid=false`
  on each lookup — easy to filter out.
- Numeric inputs (`392`, `978`) resolve cleanly.

## How to load

The fastest path — uploads the CSV, substitutes the placeholders in
`flow.dig.json`, and creates the pipeline:

```bash
python3 FunctionPacks/scripts/import_example.py reference_data
```

It prints a `http://localhost:3100/pipelines/<id>` URL — open it.

If you'd rather build the flow by hand, see the index in
`examples/README.md` → "Manual recreation".
