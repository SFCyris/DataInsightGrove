# ⏳ Time-series Pro

Diagnostic tests + ACF/PACF analysis + changepoint detection. The
"is this series even forecastable?" toolkit.

## Steps

| Step | Purpose |
| --- | --- |
| `adf_test`              | Augmented Dickey-Fuller — tests for unit root (H0: non-stationary) |
| `kpss_test`             | Kwiatkowski-Phillips-Schmidt-Shin — tests for stationarity (H0: stationary). Use both ADF + KPSS for a confident verdict |
| `acf_pacf`              | Autocorrelation + partial-autocorrelation values for lags 1..N — feeds ARIMA order selection |
| `changepoint_detection` | Detect sudden shifts in mean or variance using rolling-window CUSUM |

## Requirements

```bash
pip install "statsmodels>=0.14"
```

## Changelog

### 0.1.0 — 2026-05-05

- Initial release.
