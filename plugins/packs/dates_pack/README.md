# 📅 Dates Pack

Calendar primitives the built-in `extract_date_parts` doesn't cover.

## Steps

| Step | Purpose |
| --- | --- |
| `fiscal_year_parts`     | Add `fy_year` / `fy_quarter` / `fy_month` columns for any fiscal-year start month (e.g. April for UK gov, October for US federal) |
| `business_days_between` | Number of business days between two dates per row, honouring country holiday calendars |
| `date_snap`             | Snap a date to the start of week / month / quarter / year |

## Requirements

```bash
pip install "holidays>=0.40"
```

## Changelog

### 0.1.0 — 2026-05-05

- Initial release.
