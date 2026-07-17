# 📞 Formats Pack

Validate + normalise common identifier formats.

## Steps

| Step | Purpose |
| --- | --- |
| `normalize_phone` | Parse a free-form phone number to E.164 (`+15551234567`); flag invalid rows |
| `validate_email`  | Syntactic email validation per RFC 5322 + DNS check (optional) |
| `validate_iban`   | Validate International Bank Account Numbers; extract country, bank code |

## Requirements

```bash
pip install "phonenumbers>=8.13" "email-validator>=2.1" "schwifty>=2024.4"
```

## Changelog

### 0.1.0 — 2026-05-05

- Initial release.
