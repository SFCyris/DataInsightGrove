# Data types in DIG

DIG knows about **29 data types**, organized in two layers:

- **6 base physical types** — `string`, `integer`, `double`, `boolean`, `date`, `datetime` — describe how a value is stored on disk.
- **23 meta-types** — describe what a value *means*. A meta-type maps onto a precise physical SQL type (`DECIMAL(18,4)` for `currency`, `UUID` for `uuid`, `DOUBLE[n]` for `vector`, …). The mapping isn't just relabeling — it actually changes how DuckDB stores and operates on the values, so casts are lossless and arithmetic is exact.

The full registry lives in [`backend/dig/engine/meta_types.py`](../backend/dig/engine/meta_types.py); this document explains it in prose.

---

## The two-layer model

Every column has a **logical type** (what it means) and a **physical storage type** (how it's stored). A `currency` column means "a monetary value" and is stored in `DECIMAL(18,4)` so `$0.10 + $0.20` is exactly `$0.30` rather than IEEE 754's `0.30000000000000004`. The grid surfaces both — the logical type drives validation and formatting; the physical type appears in the column-header tooltip and the profile drawer ("Stored as DECIMAL(18,4)").

Some meta-types pick their physical storage **dynamically** based on the data. A `scientific` column whose values fit in IEEE 754's range is stored as `DOUBLE`; one whose values exceed `±1.8 × 10³⁰⁸` is stored as `VARCHAR` so the value isn't silently mauled to ±Inf. The Cast UI shows this trade-off — when the detector picks a non-default storage, an amber `→ VARCHAR` chip appears on the smart-pick.

---

## How a type is chosen

When you ingest a dataset, DIG profiles every column and asks each detector *"how confident are you that this column is your type?"* Detectors return a score between `0` and `1` and (optionally) a storage override. The top-scoring detector wins; alternates with score ≥ `0.5` are surfaced in the column header as a **✨ +N** badge so you can re-cast in one click.

You can always override the auto-detection from the column menu (`⋯ → 🔄 Cast to…`). The Cast UI shows **smart picks** (the detector's alternates) first, then a *Show all types* expansion that reveals the full catalog grouped by base physical type.

---

## Base physical types

These six are the storage primitives. Every meta-type ultimately maps onto one of them.

### 🅰️ string

Free-form text.

| Aspect | Value |
|---|---|
| **Storage** | UTF-8 string (`VARCHAR` in DuckDB / `Utf8` in Polars) |
| **Constraints** | Any sequence of Unicode characters; `NULL` is a separate state |
| **Range** | Length ≤ 2 GB per cell (DuckDB hard limit) |
| **Granularity** | Single Unicode character |
| **Min / max** | n/a — strings sort lexicographically |

**Where you find it:** product names, free-text comments, addresses, anything not pinned down by a more specific type.

### 🔢 integer

Whole number, no fractional part.

| Aspect | Value |
|---|---|
| **Storage** | 64-bit signed integer (`BIGINT` / `Int64`) |
| **Constraints** | No fractional component |
| **Range** | −9,223,372,036,854,775,808 to 9,223,372,036,854,775,807 |
| **Granularity** | 1 |
| **Min / max** | −2⁶³ / 2⁶³ − 1 |

**Where you find it:** row counts, ages, quantities, ranks, IDs, click counts. For values exceeding 2⁶³, see `bignum`.

### 🔢 double

Floating-point number with a fractional part.

| Aspect | Value |
|---|---|
| **Storage** | IEEE 754 64-bit float (`DOUBLE` / `Float64`) |
| **Constraints** | `NaN` and `±Inf` are valid IEEE values; DIG renders them as `—` |
| **Range** | ±5 × 10⁻³²⁴ (subnormal) to ±1.8 × 10³⁰⁸ |
| **Granularity** | ~15–17 significant decimal digits |
| **Min / max** | ±2.225 × 10⁻³⁰⁸ (normal min) / ±1.797 × 10³⁰⁸ |

**Where you find it:** measurements, ratios, sensor readings. For exact decimal arithmetic see `currency` / `percentage`.

### ☑️ boolean

Two-state truth value.

| Aspect | Value |
|---|---|
| **Storage** | 1-byte boolean (`BOOLEAN` / `Boolean`) |
| **Constraints** | Exactly one of `true`, `false`, or `NULL` |
| **Range** | {`true`, `false`} |
| **Granularity** | n/a |
| **Min / max** | `false` < `true` |

**Where you find it:** flags, feature toggles, yes/no survey answers.

### 📅 date

Calendar date with no time component.

| Aspect | Value |
|---|---|
| **Storage** | `DATE` / `Date32` (days since 1970-01-01) |
| **Constraints** | Year/month/day with calendar validity |
| **Range** | 5877642-06-23 BC to 5881580-07-11 AD (DuckDB) |
| **Granularity** | 1 day |
| **Min / max** | Display formatted as ISO-8601 (`2026-05-02`) |

**Where you find it:** birthdays, calendar events, due dates, billing periods.

### 📅 datetime

Timestamp — date plus time of day.

| Aspect | Value |
|---|---|
| **Storage** | `TIMESTAMP` / `Datetime[μs]` (microseconds since epoch) |
| **Constraints** | Naive (timezone-less) by default |
| **Range** | 290,000 BC to 290,000 AD |
| **Granularity** | 1 microsecond |
| **Min / max** | Display formatted as ISO-8601 (`2026-05-02T15:30:00`) |

**Where you find it:** event logs, transaction timestamps, audit trails.

---

## Numeric meta-types

These layer extra meaning on top of `integer` or `double`, and each maps to a **precise** physical storage so arithmetic is exact and overflow is caught.

### 🔑 index

Integer column where every value is unique.

| Aspect | Value |
|---|---|
| **Logical** | `index` |
| **Physical** | `BIGINT` |
| **Detection** | ≥ 99.9% non-null AND ≥ 99.9% distinct values |
| **Constraints** | All non-null values must be unique. Duplicates render rose-tinted with a **⚠ N** column-header badge |
| **Range** | Same as `integer` |
| **Granularity** | 1 |

**Where you find it:** primary keys, surrogate IDs, row numbers.

### 📊 percentage

Decimal value in `[0, 1]`, displayed as a percent.

| Aspect | Value |
|---|---|
| **Logical** | `percentage` |
| **Physical** | `DECIMAL(9,6)` — exact decimal arithmetic, 6 fraction digits |
| **Detection** | All values in `[-0.001, 1.001]`. Score `0.92` if name contains `pct/percent/rate/ratio/_pc/fraction`, else `0.65` |
| **Constraints** | 0–1 range |
| **Range** | `-999.999999` to `999.999999` (3 integer digits + 6 fractional, by precision); usable values [0, 1] |
| **Granularity** | 10⁻⁶ (one part per million) |
| **Display** | `12.34%` (en-US) |

**Where you find it:** conversion rates, churn fractions, completion rates. DIG's canonical storage is **0..1**, not **0..100** — multiply at the source if needed.

### 💵 currency

Monetary value with exact decimal arithmetic.

| Aspect | Value |
|---|---|
| **Logical** | `currency` |
| **Physical** | `DECIMAL(18,4)` — 14 integer digits + 4 fractional |
| **Detection** | Column name contains `price/amount/cost/revenue/balance/fee/salary/income/expense/total/value/_usd/_eur/_gbp`. Score `0.75` |
| **Constraints** | None enforced — DIG can't tell `19.99 USD` from `19.99 EUR` |
| **Range** | ±99,999,999,999,999.9999 (covers any realistic monetary value) |
| **Granularity** | $0.0001 (one ten-thousandth of a unit; sufficient for HFT / sub-cent micropayments) |
| **Display** | `$1,234.56` (en-US, USD) |

**Why DECIMAL not DOUBLE:** floating-point arithmetic on currency loses cents (`0.1 + 0.2 ≠ 0.3`). `DECIMAL(18,4)` is exact: `$19.99 + $0.01 = $20.0000` reliably.

**Where you find it:** prices, salaries, transaction amounts, account balances, invoice totals.

### 🔬 scientific (IEEE 754)

`double` formatted in scientific notation.

| Aspect | Value |
|---|---|
| **Logical** | `scientific` |
| **Physical** | `DOUBLE` for in-range values; `VARCHAR` if `\|x\|` exceeds IEEE 754 (range-aware) |
| **Detection** | `max(\|value\|) ≥ 10⁶` OR `min(\|value\|) < 10⁻³` (and non-zero). Score `0.85` |
| **Constraints** | None for DOUBLE storage; values stored as VARCHAR can be arbitrary-precision lexical decimals |
| **Range (DOUBLE)** | ±2.225 × 10⁻³⁰⁸ to ±1.798 × 10³⁰⁸ |
| **Range (VARCHAR)** | unbounded |
| **Granularity** | 4 significant digits in display (`1.2345e+10`) |

**Multi-storage trade-off:** when the detector picks `VARCHAR` storage, you preserve precision but lose SQL pushdown for `SUM`/`AVG` etc. — operations have to route through the parsing layer. The Cast UI shows this with a `→ VARCHAR` chip.

**Where you find it:** physics constants, astronomy distances, molecular concentrations, very small p-values, very large counts.

### 🧮 bignum

128-bit signed integer for values that overflow `BIGINT`.

| Aspect | Value |
|---|---|
| **Logical** | `bignum` |
| **Physical** | `HUGEINT` (128-bit) for `\|x\|` ≤ 2¹²⁷; `VARCHAR` beyond (range-aware) |
| **Detection** | Numeric values approaching 2⁶³, OR hex strings with > 16 nibbles (decoded value > 64 bits) |
| **Constraints** | Whole-number only |
| **Range (HUGEINT)** | ±170,141,183,460,469,231,731,687,303,715,884,105,727 (≈ 1.7 × 10³⁸) |
| **Range (VARCHAR)** | unbounded |
| **Granularity** | 1 |

**Where you find it:** SHA-256 fragments, genomic position counts, large hex IDs, financial micro-units. DuckDB's `HUGEINT` is the canonical storage.

### #️⃣ hex

Number written in hexadecimal notation (`0xCAFE`).

| Aspect | Value |
|---|---|
| **Logical** | `hex` |
| **Physical** | `VARCHAR` — text notation preserved |
| **Detection** | ≥ 85% of top values match `^0x[0-9a-f]+$`. Score capped at `0.95` |
| **Constraints** | Must start with `0x` followed by hex digits |
| **Range** | Limited only by string length |

**Where you find it:** memory addresses, error codes, hash digests. The numeric-decoded form lives in `bignum`.

### ♾️ decimal_string

Arbitrary-precision decimal stored as a lexical string.

| Aspect | Value |
|---|---|
| **Logical** | `decimal_string` |
| **Physical** | `VARCHAR` |
| **Detection** | ≥ 85% numeric-shaped strings AND at least one value has > 30 significant digits (DECIMAL(38,n) overflow) |
| **Constraints** | Must match `^[+-]?(\d+\.?\d*\|\.\d+)([eE][+-]?\d+)?$` |
| **Range** | Unbounded |
| **Granularity** | Per-value, limited only by string length |

**Trade-off:** SQL `SUM`/`AVG` etc. don't apply natively — operations route through Python `decimal.Decimal` when needed. Use only when `DECIMAL(38,n)` or `HUGEINT` would overflow.

**Where you find it:** high-precision physical constants (Avogadro to 100 digits), scientific calculations, custom financial micro-units.

---

## String meta-types

All eight are stored as `VARCHAR` (or DuckDB-native `UUID` for the UUID type) and add per-cell shape validation. Invalid cells render rose-tinted with a tooltip explaining what was expected.

### 🆔 uuid

RFC 4122 universally-unique identifier.

| Aspect | Value |
|---|---|
| **Logical** | `uuid` |
| **Physical** | DuckDB native `UUID` (128-bit binary) — faster compare/sort than VARCHAR |
| **Detection** | ≥ 85% of top values match the 8-4-4-4-12 hex pattern. Score capped at `0.95` |
| **Constraints** | 8-4-4-4-12 hex separated by `-` |
| **Range** | 2¹²⁸ unique values |

**Where you find it:** session tokens, distributed trace IDs, anything from `uuid.uuid4()`. Covers UUID v1 through v8.

### 📧 email

Email address.

| Aspect | Value |
|---|---|
| **Logical** | `email` |
| **Physical** | `VARCHAR` |
| **Detection** | ≥ 85% match `^[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}$`. Score capped at `0.95` |
| **Constraints** | local@domain.tld shape; pragmatic, not full RFC 5322 |

**Where you find it:** user records, mailing lists, contact forms.

### 🔗 url

HTTP/HTTPS URL.

| Aspect | Value |
|---|---|
| **Logical** | `url` |
| **Physical** | `VARCHAR` |
| **Detection** | ≥ 85% match `^https?://[^\s<>'"]+$` |
| **Constraints** | Must start with `http://` or `https://` |

**Where you find it:** referrer URLs, content links, API endpoints.

### 🌐 ip

IPv4 or IPv6 address.

| Aspect | Value |
|---|---|
| **Logical** | `ip` |
| **Physical** | `VARCHAR` |
| **Detection** | ≥ 85% match either IPv4 (4 octets 0–255) or loose IPv6 (`:` plus hex digits, 2–7 colons) |
| **Constraints** | IPv4: octets 0–255. IPv6: lenient |

**Where you find it:** access logs, audit trails, geolocation joins.

### 📞 phone (E.164)

Phone number in E.164 format.

| Aspect | Value |
|---|---|
| **Logical** | `phone` |
| **Physical** | `VARCHAR` |
| **Detection** | ≥ 85% match `^\+?[1-9]\d{6,14}$` (optional `+`, 7–15 digits) |
| **Constraints** | Strict E.164 — no spaces, dashes, or parentheses |

**Where you find it:** customer records, MFA contacts. Normalize formatted numbers before casting.

### 🌍 country

ISO 3166-1 alpha-2 country code.

| Aspect | Value |
|---|---|
| **Logical** | `country` |
| **Physical** | `VARCHAR` |
| **Detection** | ≥ 85% appear in DIG's hardcoded ~250-code list |
| **Constraints** | Exactly two ASCII letters |

**Where you find it:** address data, billing locales, geo-IP joins. Alpha-3 (`USA`) and full names need a separate mapping step.

### 🎨 color

CSS color: hex, `rgb()`, or named.

| Aspect | Value |
|---|---|
| **Logical** | `color` |
| **Physical** | `VARCHAR` |
| **Detection** | ≥ 85% match hex, `rgb(...)`, or one of ~25 named colors |
| **Constraints** | Valid CSS color literal |

**Where you find it:** theme definitions, palette tables, design tokens.

### 🌍 timezone

IANA timezone name.

| Aspect | Value |
|---|---|
| **Logical** | `timezone` |
| **Physical** | `VARCHAR` |
| **Detection** | ≥ 80% appear in the IANA zone database |
| **Constraints** | Exact match to IANA list. `EST`/`PST`/`CET` are NOT valid (abbreviations, not zone IDs) |

**Where you find it:** user-preference tables, calendar/scheduling data, log shipping headers.

---

## Composite types

Structured/nested types — DIG promotes them to DuckDB native composite storage so operations are fast and lossless.

### 📦 json

Semi-structured JSON object or array.

| Aspect | Value |
|---|---|
| **Logical** | `json` |
| **Physical** | `JSON` (DuckDB native) |
| **Detection** | ≥ 85% of top values start with `{`/`[` and parse via `json.loads`. Score capped at `0.95` |
| **Constraints** | Valid JSON per RFC 8259 |
| **Operators** | Path extraction (`->`, `->>`), `json_extract`, `json_array_length`, `json_type` (DuckDB built-ins) |

**Where you find it:** event payloads, API responses, document stores, config blobs.

### 📚 array

Variable-length list of values.

| Aspect | Value |
|---|---|
| **Logical** | `array` |
| **Physical** | `JSON` (variable-length list) |
| **Detection** | ≥ 85% are JSON arrays AND not all-numeric (else promoted to `vector`) |
| **Constraints** | Top-level must be a JSON array |
| **Operators** | `json_array_length`, `json_extract` (by index), `unnest` to explode rows |

**Where you find it:** tag lists, tracked-events arrays, multi-select form fields.

### 🧭 vector

Fixed-length numeric array — typically ML embeddings.

| Aspect | Value |
|---|---|
| **Logical** | `vector` |
| **Physical** | `DOUBLE[n]` — DuckDB-native fixed-size array |
| **Detection** | Numeric-only arrays of consistent length `n` |
| **Constraints** | All entries must be numeric; length must be uniform across rows |
| **Operators** | `array_cosine_similarity`, `array_inner_product`, `array_distance` (DuckDB), `<->` operator for kNN |

**Where you find it:** ML embeddings (sentence-transformers, OpenAI, Cohere, …), feature vectors, kNN indices, RAG pipelines.

---

## Spatial coordinate types

DIG carries three coordinate systems plus a lossless conversion step. Detection of these is **not automatic** from raw column data — they come from explicit casts or upstream `pack_struct` operations. The `convert_coordinates` step handles transitions between systems.

### 📐 cartesian2d

2D point (x, y).

| Aspect | Value |
|---|---|
| **Logical** | `cartesian2d` |
| **Physical** | `STRUCT(x DOUBLE, y DOUBLE)` |
| **Convertible to** | `polar2d` (pure trig, lossless), `cartesian3d` (z=0), `polar3d`, `geographic` (via ECEF) |

**Where you find it:** screen coordinates, manufacturing tolerances, abstract 2D vectors.

### 📐 cartesian3d

3D point (x, y, z).

| Aspect | Value |
|---|---|
| **Logical** | `cartesian3d` |
| **Physical** | `STRUCT(x DOUBLE, y DOUBLE, z DOUBLE)` |
| **Convertible to** | `polar3d` (spherical), `cartesian2d` (drops z), `geographic` (assumes ECEF) |

**Where you find it:** 3D modeling, physics simulations, ECEF satellite positions.

### 🧭 polar2d

Polar coordinate (r, θ) — radius + angle in radians.

| Aspect | Value |
|---|---|
| **Logical** | `polar2d` |
| **Physical** | `STRUCT(r DOUBLE, theta DOUBLE)` |
| **Convertible to** | `cartesian2d` (lossless: x = r·cosθ, y = r·sinθ), and via cartesian to other systems |

**Where you find it:** waveform analysis (magnitude/phase), radar plots, anything with a natural origin.

### 🧭 polar3d

Spherical polar (r, θ inclination, φ azimuth) — ISO physics convention.

| Aspect | Value |
|---|---|
| **Logical** | `polar3d` |
| **Physical** | `STRUCT(r DOUBLE, theta DOUBLE, phi DOUBLE)` |
| **Convertible to** | `cartesian3d` (lossless), and via cartesian to other systems |

**Where you find it:** astronomical positions (right ascension/declination after conversion), 3D directional sensors, sound localization.

### 🌍 geographic

Point on Earth — lat/lon stored as DuckDB-spatial geometry.

| Aspect | Value |
|---|---|
| **Logical** | `geographic` |
| **Physical** | `GEOMETRY` (DuckDB spatial extension; Well-Known Binary format) |
| **Constraints** | lat ∈ `[-90, 90]`, lon ∈ `[-180, 180]` |
| **Operators** | `ST_Distance` (great-circle Haversine), `ST_DWithin`, `ST_Contains`, `ST_Buffer`, et al. |
| **Convertible to** | `cartesian3d` via WGS84 ECEF (Earth-Centered Earth-Fixed) |

**Where you find it:** lat/lon pairs, GeoJSON points, anything geospatial. The DuckDB spatial extension must be loaded (`INSTALL spatial; LOAD spatial;`) at backend startup.

---

## Coordinate conversion

The `convert_coordinates` step (in [`backend/steps/convert_coordinates/`](../backend/steps/convert_coordinates/)) handles lossless conversion between any pair of coordinate systems. The conversion catalog:

| From | To | Method | Loss |
|---|---|---|---|
| `cartesian2d` | `polar2d` | `r = √(x²+y²)`, `θ = atan2(y, x)` | bit-exact (machine ε) |
| `polar2d` | `cartesian2d` | `x = r·cosθ`, `y = r·sinθ` | bit-exact |
| `cartesian3d` | `polar3d` | spherical (r, θ, φ) — ISO physics convention | bit-exact |
| `polar3d` | `cartesian3d` | inverse spherical | bit-exact |
| `cartesian2d` ↔ `cartesian3d` | dimension lift / drop (z=0) | trivial | up: lossless; down: drops z |
| `geographic` | `cartesian3d` | WGS84 ECEF — semi-major a=6,378,137 m, flattening f=1/298.257223563 | bit-exact |
| `cartesian3d` | `geographic` | WGS84 ECEF inverse via Bowring's closed-form | drift ≈ 1.4×10⁻¹⁴° (≈ 16 nm on Earth) |
| `polar` ↔ `geographic` | routed through cartesian | composite drift |

The step takes:
- `fromType` and `toType` — any of the five coordinate systems
- `sourceColumns` — the input columns in canonical order (cartesian: `[x, y, z?]`; polar: `[r, theta, phi?]`; geographic: `[lat, lon]`)
- `outputPrefix` — prepended to each generated output column (`coord_x`, `coord_y`, `coord_lat`, `coord_lon`, …)

Output columns follow the canonical order of the target system. The step is Polars-engine (not SQL) because the math involves trig and conditional ellipsoid logic that's cleaner in Python; preview routes through the backend rather than DuckDB-WASM.

---

## Adding a new type

The recipe lives in [`backend/dig/engine/meta_types.py`](../backend/dig/engine/meta_types.py) at the top of the file. In short:

1. Append a `TypeDescriptor` to the `TYPES` registry (id, label, base, sql_type, description, detector). Pick the precise SQL physical type — if DuckDB has one for your domain (`UUID`, `JSON`, `DECIMAL`, `HUGEINT`, `GEOMETRY`), use it.
2. Write the detector function — input is the column profile dict, output is a `TypeCandidate` with score 0–1, optional `storage` override, or `None`.
3. Add the new id to:
   - [`backend/steps/cast_type/manifest.json`](../backend/steps/cast_type/manifest.json) `targetType` enum
   - [`backend/steps/cast_type/step.py`](../backend/steps/cast_type/step.py) `_TYPE_TO_SQL` map
4. Add the emoji to `TYPE_EMOJI` in [`frontend/components/grid/live-grid.tsx`](../frontend/components/grid/live-grid.tsx).
5. Add the type id to `META_TYPE_IDS` (same file) and to `_META_TYPES` in [`frontend/lib/meta-types.ts`](../frontend/lib/meta-types.ts).
6. (Optional) Add a per-cell validator in `meta-types.ts` and reference it from `isValidForType()`.
7. (Optional) Add a frontend formatter in the `fmt()` function in `live-grid.tsx`.

Auto-detection, the cast dropdown, the smart-picks UI, the profile drawer, and the column-header tooltip all read from the registry — adding it in one place surfaces it everywhere.
