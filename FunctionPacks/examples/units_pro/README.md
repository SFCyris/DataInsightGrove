# 🔧 `units_pro` · sensor unit normalisation

**Scenario:** field sensors report measurements in a mix of imperial
and metric units. We need to normalize everything to SI before
downstream analytics.

**Data** (`data.csv`, 15 rows): `sensor_id, city, temperature_celsius,
distance_miles, energy_kwh, pressure_psi`.

## What the flow shows

```
ds → convert_units_pro(°C → °F)
   → convert_units_pro(miles → km)
   → convert_units_pro(psi → bar)
   → convert_units_pro(kWh → joules)
   → physical_constant(speed_of_light) → c_m_per_s column
```

Each conversion adds a new column without dropping the original — so a
review can compare both forms side by side.

## How to load

The fastest path — uploads the CSV, substitutes the placeholders in
`flow.dig.json`, and creates the pipeline:

```bash
python3 FunctionPacks/scripts/import_example.py units_pro
```

It prints a `http://localhost:3100/pipelines/<id>` URL — open it.

If you'd rather build the flow by hand, see the index in
`examples/README.md` → "Manual recreation".
