# 📞 `formats_pack` · CRM contact hygiene

**Scenario:** an exported CRM contact list with messy formats. Phones
in (555) 123-4567, dotted, or international form. Emails with typos.
IBANs with stray spaces or invalid checksums.

**Data** (`data.csv`, 10 rows): `customer_id, name, email, phone, iban`.
Some rows are deliberately broken so you can see the flag columns light
up.

## What the flow shows

```
ds → normalize_phone(US default) → validate_email → validate_iban
                                                       ├─→ all rows + flag columns
                                                       └─→ filter to invalid rows
```

| Customer | Issue |
|----------|-------|
| C-003 | Email is `carlos@` (truncated) |
| C-005 | Email is plain text, not RFC |
| C-007 | Phone has letters, IBAN is `DE-INVALID` |
| C-008 | IBAN missing |
| C-010 | Korean IBAN format isn't real (KR isn't an IBAN country) |

After the flow:
- `phone_e164` — `+15551234567` style on success, NULL on failure
- `phone_e164_valid` — boolean
- `email_valid` + `email_normalized`
- `iban_valid` + `iban_country` + `iban_bank_code` + `iban_account`

## How to load

The fastest path — uploads the CSV, substitutes the placeholders in
`flow.dig.json`, and creates the pipeline:

```bash
python3 FunctionPacks/scripts/import_example.py formats_pack
```

It prints a `http://localhost:3100/pipelines/<id>` URL — open it.

If you'd rather build the flow by hand, see the index in
`examples/README.md` → "Manual recreation".
