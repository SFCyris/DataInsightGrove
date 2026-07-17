# 🔧 Units Pro

Pint-powered unit conversion + physical constants lookup.

## Steps

| Step | Purpose |
| --- | --- |
| `convert_units_pro`  | Convert a column from any source unit to any compatible target unit |
| `physical_constant`  | Look up the value of a named physical constant (gravitational, Avogadro, Planck, etc.) |

## Requirements

```bash
pip install "Pint>=0.24"
```

## Examples

`convert_units_pro` accepts any unit Pint recognises:

- length: meter / mile / nautical_mile / parsec / inch / foot
- mass: kg / pound / stone / ounce / atomic_mass_unit
- time: second / minute / hour / day / year
- energy: joule / calorie / electron_volt / kWh / btu
- pressure: pascal / bar / psi / mmHg
- temperature: kelvin / celsius / fahrenheit / rankine

## Changelog

### 0.1.0 — 2026-05-05

- Initial release.
