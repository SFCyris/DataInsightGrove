# 📚 Reference data

Authoritative lookups against ISO standards.

## Steps

| Step | Purpose |
| --- | --- |
| `country_lookup`     | Resolve a country column (alpha-2 / alpha-3 / numeric / name) into its full canonical row |
| `currency_lookup`    | Resolve a currency column (ISO 4217 alpha-3 / numeric / name) |
| `timezone_resolve`   | Validate IANA timezone names; detect ambiguity (e.g. `EST` matches multiple zones) |

## Requirements

```bash
pip install "pycountry>=23.12"
```

## Changelog

### 0.1.0 — 2026-05-05

- Initial release.
