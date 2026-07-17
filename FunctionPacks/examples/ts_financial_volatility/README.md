# 💹 Financial · 20-day rolling volatility

**Scenario:** ~2 years of daily price + return data. There's a 60-day
cluster of high-volatility days mid-series (think earnings season or
a crisis window).

## What the flow shows

```
ds ─→ rolling(window=20)             → adds return_pct_std_20 + return_pct_mean_20
   ─→ export_to_image                  → line chart of the rolling std
```

The flat-then-spike-then-flat pattern in the rolling std is exactly
how volatility regimes manifest — the kind of signal a quant or risk
analyst would build a vol-targeting strategy around.

## Run

```bash
python3 FunctionPacks/scripts/import_example.py ts_financial_volatility
```
