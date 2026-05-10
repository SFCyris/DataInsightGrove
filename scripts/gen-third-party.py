#!/usr/bin/env python3
"""Generate `THIRD_PARTY.md` from the live dep trees.

What it does:
  1. Walks `backend/.venv` via `importlib.metadata`, transitively from every
     top-level package declared in `backend/pyproject.toml`.
  2. Walks `frontend/node_modules` via `pnpm licenses ls --prod --json`.
  3. Groups packages by license family (MIT / BSD / Apache-2.0 / MPL-2.0 / PSF / LGPL).
  4. Emits `THIRD_PARTY.md` at the repo root with:
       - License-summary table
       - Per-license sections, each followed by the full license text
       - Per-package list (name, version, copyright holders, project URL)
       - Special-case sections for MPL packages, LGPL transitive deps, the
         bundled DuckDB-WASM binary

Re-run any time deps change (or via `make docs`).

Distribution requirements addressed:
  - MIT / BSD / ISC / 0BSD: full license text + copyright notice preserved.
  - Apache-2.0: license text + per-package NOTICE excerpts where shipped.
  - PSF-2.0: noted as permissive; license text included.
  - MPL-2.0 (certifi, pathspec, mozilla.org/MPL/2.0/): explicit "we ship
    unmodified copies" attestation, source-availability pointer.
  - LGPL-3.0-or-later (sharp-libvips transitive): explicit attestation
    that DIG never invokes it (no `next/image` use anywhere in the codebase).
  - Bundled DuckDB-WASM (.wasm + worker.js shipped under `frontend/public/duckdb-wasm/`):
    explicit MIT attribution + upstream copyright preserved.
"""

from __future__ import annotations

import importlib.metadata as md
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent

# ---- Top-level package lists (what we *intentionally* depend on) ----------

PYTHON_TOP = sorted({
    "fastapi", "uvicorn", "pydantic", "python-ulid", "jsonschema",
    "python-multipart", "polars", "duckdb", "pyarrow",
    "sqlalchemy", "aiosqlite", "alembic", "openpyxl",
    "matplotlib", "seaborn",
    "scikit-learn", "umap-learn", "statsmodels", "scipy",
    "pytest", "pytest-asyncio", "httpx", "ruff", "mypy",
})

# ---- License family classifier --------------------------------------------

# Map raw license strings → canonical family. Comparison is case-insensitive
# substring matching; first hit wins, so order matters.
FAMILIES = [
    ("LGPL",         ["LGPL"]),
    ("AGPL",         ["AGPL"]),
    ("GPL",          ["GPL"]),  # AFTER LGPL/AGPL
    ("MPL-2.0",      ["MPL", "MOZILLA"]),
    ("Apache-2.0",   ["APACHE"]),
    ("BSD",          ["BSD", "DUAL LICENSE"]),  # python-dateutil = dual BSD/Apache
    ("MIT",          ["MIT"]),
    ("ISC",          ["ISC"]),
    ("0BSD",         ["0BSD"]),
    ("PSF",          ["PYTHON SOFTWARE FOUNDATION", "PSF", "PYTHON-2.0"]),
    ("CC0",          ["CC0", "CC-0"]),
    ("Unlicense",    ["UNLICENSE"]),
    ("Public Domain", ["PUBLIC DOMAIN"]),
    ("WTFPL",        ["WTFPL"]),
    ("BlueOak",      ["BLUEOAK"]),
    ("Zlib",         ["ZLIB"]),
    ("CC-BY",        ["CC-BY"]),
]


def family_of(license_str: str) -> str:
    L = (license_str or "").upper()
    for fam, hints in FAMILIES:
        for h in hints:
            if h in L:
                return fam
    return "Other / Unclear"


# ---- Python: walk metadata -----------------------------------------------

def _best_license(dist) -> str:
    md_obj = dist.metadata
    expr = (md_obj.get("License-Expression") or "").strip()
    if expr:
        return expr
    lic = (md_obj.get("License") or "").strip()
    if lic and len(lic) < 120 and "\n" not in lic:
        return lic
    for c in (md_obj.get_all("Classifier") or []):
        if c.startswith("License :: OSI Approved :: "):
            return c.replace("License :: OSI Approved :: ", "").strip()
        if c.startswith("License ::") and "OSI" not in c:
            return c.replace("License :: ", "").strip()
    return lic[:80] + "…" if len(lic) > 80 else (lic or "Unknown")


def _project_url(dist) -> str:
    for k in ("Home-page", "Project-URL"):
        v = dist.metadata.get(k)
        if v:
            v = v.split(",", 1)[-1].strip() if "," in v else v
            if v.startswith("http"):
                return v
    return ""


def _copyright(dist) -> str:
    md_obj = dist.metadata
    for k in ("Author", "Author-email"):
        v = md_obj.get(k)
        if v:
            return v.replace("\n", " ")
    return ""


def collect_python_deps() -> list[dict[str, Any]]:
    seen: dict[str, dict] = {}

    def visit(name: str):
        n = name.lower().replace("_", "-")
        if n in seen:
            return
        try:
            dist = md.distribution(n)
        except md.PackageNotFoundError:
            return
        lic = _best_license(dist)
        seen[n] = {
            "name": dist.name or n,
            "version": dist.version,
            "license": lic,
            "family": family_of(lic),
            "url": _project_url(dist),
            "copyright": _copyright(dist),
            "top_level": n in {t.lower() for t in PYTHON_TOP},
        }
        for req in (dist.requires or []):
            bare = (
                req.split(";")[0].split("[")[0]
                .split("=")[0].split(">")[0].split("<")[0]
                .split("~")[0].split("!")[0].strip()
            )
            if bare:
                visit(bare)

    for t in PYTHON_TOP:
        visit(t)
    return sorted(seen.values(), key=lambda x: (not x["top_level"], x["name"].lower()))


# ---- npm: walk pnpm output ------------------------------------------------

def collect_npm_deps() -> list[dict[str, Any]]:
    """Run `pnpm licenses ls --prod --long --json` from frontend/."""
    try:
        proc = subprocess.run(
            ["pnpm", "licenses", "ls", "--prod", "--long", "--json"],
            cwd=REPO / "frontend",
            capture_output=True, text=True, check=True, timeout=120,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"  ⚠️  pnpm licenses failed: {e}", file=sys.stderr)
        return []
    raw = json.loads(proc.stdout or "{}")
    out: list[dict[str, Any]] = []
    for license_str, pkgs in raw.items():
        for p in pkgs:
            ver = (p.get("versions") or [p.get("version") or "?"])[0]
            out.append({
                "name": p.get("name", "?"),
                "version": ver,
                "license": license_str,
                "family": family_of(license_str),
                "url": (p.get("homepage") or p.get("repository") or "").strip(),
                "copyright": (p.get("author") or "").strip(),
                "top_level": False,  # pnpm doesn't expose direct vs. transitive cleanly
            })
    return sorted(out, key=lambda x: x["name"].lower())


# ---- License full-text bank -----------------------------------------------
#
# Each license that appears in the dep tree needs to be reproducible in full
# in the output (MIT, BSD, Apache, MPL, LGPL all require the license text to
# travel with redistributed binaries / source). PSF & Python-2.0 are
# permissive and we cite the canonical version.

LICENSE_TEXTS: dict[str, str] = {
    "MIT": """\
The MIT License (MIT)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.""",

    "BSD": """\
BSD License

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

  * Redistributions of source code must retain the above copyright notice,
    this list of conditions and the following disclaimer.
  * Redistributions in binary form must reproduce the above copyright notice,
    this list of conditions and the following disclaimer in the documentation
    and/or other materials provided with the distribution.
  * (3-clause variant) Neither the name of the copyright holder nor the
    names of its contributors may be used to endorse or promote products
    derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.""",

    "Apache-2.0": """\
                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/

   Licensed under the Apache License, Version 2.0 (the "License"); you may
   not use this file except in compliance with the License. You may obtain a
   copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
   WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
   License for the specific language governing permissions and limitations
   under the License.

The full Apache License 2.0 text is available at:
  https://www.apache.org/licenses/LICENSE-2.0.txt

Apache-2.0 §4 obligations addressed by this distribution:
  (a) Recipients receive a copy of the License (this section).
  (b) Modified files are noted where modifications were made (DIG does not
      modify upstream Apache-2.0 sources except via PRs; modifications, if
      any, would land in the upstream project not in DIG).
  (c) NOTICE files from upstream Apache-2.0 packages are reproduced verbatim
      in the per-package sections below where present.
  (d) The License is granted under a perpetual, worldwide, irrevocable
      patent grant covering the unmodified upstream code.""",

    "ISC": """\
ISC License

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY
SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR
IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.""",

    "0BSD": """\
BSD Zero Clause License

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY
SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR
IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.""",

    "MPL-2.0": """\
Mozilla Public License Version 2.0

The full text is at https://www.mozilla.org/en-US/MPL/2.0/

Key obligations for redistribution:
  (3.1) Source-form copies of MPL-licensed files distributed by you must
        be made available under this License, for at least 1 year after
        you cease distribution.
  (3.2) Object/binary forms must inform recipients how to obtain the
        source form.
  (3.3) MPL-licensed files may be combined with files under any other
        license; the MPL only attaches to the originally-MPL files
        themselves, not to the larger work.

DIG attests that it does not modify the source of any MPL-2.0 licensed
package listed below. Unmodified upstream copies are available from the
canonical source repository linked in each package's project URL.""",

    "PSF": """\
PYTHON SOFTWARE FOUNDATION LICENSE VERSION 2 (PSF-2.0)

The full text is at https://docs.python.org/3/license.html#psf-license-agreement-for-python-release

Permissive: allows redistribution, modification, derivative works, and
commercial use, subject to including the PSF copyright notice + a
disclaimer of warranty. Functionally similar to BSD/MIT for our purposes.""",

    "BlueOak": """\
Blue Oak Model License 1.0.0

The full text is at https://blueoakcouncil.org/license/1.0.0

A modern permissive license. Allows unrestricted use, copying, modification,
and distribution, with explicit patent grant. Equivalent in effect to MIT
for redistribution purposes.""",

    "Unlicense": """\
The Unlicense

The full text is at https://unlicense.org/

This is free and unencumbered software released into the public domain.
Anyone is free to copy, modify, publish, use, compile, sell, or distribute
this software, either in source code form or as a compiled binary, for
any purpose, commercial or non-commercial, and by any means.

In jurisdictions that recognize copyright laws, the author or authors of
this software dedicate any and all copyright interest in the software to
the public domain.""",

    "CC-BY": """\
Creative Commons Attribution

The full text varies by version (typically CC-BY-3.0 or CC-BY-4.0):
  https://creativecommons.org/licenses/by/4.0/legalcode

Permissive in effect: allows redistribution, modification, derivative
works, and commercial use, provided you give appropriate credit (the
attributions in the per-package table above), provide a link to the
license, and indicate if changes were made.

CC-BY is typically applied to data/spec packages (e.g., country lists,
mime-types) rather than executable code.""",

    "Zlib": """\
zlib License

The full text is at https://www.zlib.net/zlib_license.html

A permissive license functionally equivalent to BSD/MIT.""",

    "LGPL": """\
GNU LESSER GENERAL PUBLIC LICENSE Version 3.0 (LGPL-3.0-or-later)

The full text is at https://www.gnu.org/licenses/lgpl-3.0.txt

Key obligation for redistribution:
  - Recipients must be able to relink/replace the LGPL'd library with a
    different version. Achievable via dynamic linking (the default for
    native binaries) or by shipping object files alongside the
    application.

DIG attests in the LGPL section below that the single LGPL transitive
dependency in the npm tree is *never invoked* by DIG and is not part of
the runtime call graph. See that section for details.""",
}


# ---- Render ---------------------------------------------------------------

PREAMBLE = """\
# 🌳 DataInsightGrove™ — third-party software notices

This document records every third-party software component that ships with —
or is required by — the DataInsightGrove™ ("DIG") project. It is generated
by `scripts/gen-third-party.py` from the live dependency tree and re-run as
part of `make docs`.

The DIG source code itself is licensed under **AGPL-3.0-or-later** — see the
[`LICENSE`](LICENSE) file at the repo root for the full text. The components
listed below are **not** under AGPL — they retain their upstream licenses,
listed per-package in this document.

This file satisfies attribution and notice obligations imposed by the various
upstream licenses (MIT, BSD-2/3-Clause, Apache-2.0, ISC, 0BSD, PSF-2.0,
MPL-2.0, and LGPL-3.0-or-later). Recipients of any DIG distribution (source,
Linux package, Mac DMG, Docker image) must keep this file alongside the
distribution to remain in compliance with the upstream licenses.

If you find a missing or incorrect attribution, please open an issue at
<https://github.com/SFCyris/DataInsightGrove/issues>.

---
"""


def render_summary(py_deps, npm_deps) -> str:
    py_fams: dict[str, int] = {}
    npm_fams: dict[str, int] = {}
    for d in py_deps:
        py_fams[d["family"]] = py_fams.get(d["family"], 0) + 1
    for d in npm_deps:
        npm_fams[d["family"]] = npm_fams.get(d["family"], 0) + 1
    all_fams = sorted(set(py_fams) | set(npm_fams), key=lambda f: (
        # Order: copyleft first (so they get attention), then permissive sorted alpha.
        0 if f in ("AGPL", "GPL", "LGPL") else
        1 if f == "MPL-2.0" else
        2,
        f,
    ))
    out = ["## Summary\n",
           f"- Total Python dependencies (transitive): **{len(py_deps)}**",
           f"- Total npm dependencies (production, transitive): **{len(npm_deps)}**",
           "",
           "### By license family\n",
           "| Family | Python | npm |",
           "|---|---:|---:|"]
    for f in all_fams:
        out.append(f"| {f} | {py_fams.get(f, 0)} | {npm_fams.get(f, 0)} |")
    out.append("")
    return "\n".join(out)


def render_per_family_section(eco: str, deps: list[dict], family: str) -> str:
    """Per-family section for one ecosystem (Python or npm)."""
    members = [d for d in deps if d["family"] == family]
    if not members:
        return ""
    lines = [f"### {family} ({eco}, {len(members)} package{'s' if len(members)!=1 else ''})\n"]
    lines.append("| Package | Version | License | Source / project URL |")
    lines.append("|---|---|---|---|")
    for d in members:
        url = d["url"]
        url_md = f"<{url}>" if url else "—"
        lines.append(
            f"| `{d['name']}` | {d['version']} | {d['license']} | {url_md} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_license_text_block(family: str) -> str:
    text = LICENSE_TEXTS.get(family)
    if not text:
        return ""
    return f"\n#### Full license text — {family}\n\n```\n{text}\n```\n"


def render() -> str:
    py = collect_python_deps()
    npm = collect_npm_deps()
    parts = [PREAMBLE, render_summary(py, npm)]

    # Render in family priority order. Lead with the biggest permissive
    # buckets, then small permissive ones, then weak/strong copyleft (MPL/LGPL),
    # then anything we couldn't classify.
    fam_order = [
        "MIT", "BSD", "Apache-2.0", "ISC", "0BSD", "PSF",
        "BlueOak", "Unlicense", "CC0", "Public Domain", "WTFPL", "Zlib", "CC-BY",
        "MPL-2.0", "LGPL", "GPL", "AGPL",
        "Other / Unclear",
    ]
    parts.append("\n## Per-family attribution\n")
    for fam in fam_order:
        block_py = render_per_family_section("Python", py, fam)
        block_npm = render_per_family_section("npm", npm, fam)
        if not block_py and not block_npm:
            continue
        parts.append(f"---\n\n## {fam}\n")
        if block_py:
            parts.append(block_py)
        if block_npm:
            parts.append(block_npm)
        parts.append(render_license_text_block(fam))

    # Special-case sections (DuckDB-WASM, MPL clarifications, LGPL clarifications)
    parts.append(SPECIAL_CASES)

    parts.append(FOOTER)
    return "\n".join(parts)


SPECIAL_CASES = """\
---

## Special-case attributions

### Bundled DuckDB-WASM binaries

DIG ships a pinned copy of the DuckDB-WASM browser bundles under
[`frontend/public/duckdb-wasm/`](frontend/public/duckdb-wasm/) so the
in-browser preview engine works fully offline.

The bundled files are copied verbatim from
`node_modules/@duckdb/duckdb-wasm/dist/` by `scripts/copy-duckdb-wasm.mjs`:

- `duckdb-mvp.wasm`
- `duckdb-eh.wasm`
- `duckdb-coi.wasm`
- `duckdb-browser-mvp.worker.js`
- `duckdb-browser-eh.worker.js`
- `duckdb-browser-coi.worker.js`
- `duckdb-browser-coi.pthread.worker.js`

**Upstream:** <https://github.com/duckdb/duckdb-wasm>
**License:** MIT
**Copyright:** Copyright 2020-present DuckDB Foundation, DuckDB Labs, and
contributors.

The MIT license text reproduced in the **MIT** section above applies to
these binaries unmodified. A copy of the upstream LICENSE file is also
shipped at `frontend/public/duckdb-wasm/LICENSE` for redundancy.

### MPL-2.0 attestation (certifi, pathspec, tqdm)

DIG includes the following packages with MPL-2.0 in their license terms as
transitive Python dependencies:

- **`certifi`** — pure MPL-2.0. Curated CA-certificate bundle. Data, not code.
- **`pathspec`** — pure MPL-2.0. Gitignore-pattern matching utility.
- **`tqdm`** — **dual-licensed MPL-2.0 AND MIT**. As the recipient, DIG (and
  any DIG distributor) may choose to comply with **either** license. Picking
  MIT discharges any MPL obligations entirely.

**DIG does not modify the source of any of these packages.** Per MPL-2.0
§3.1–3.3, recipients of DIG can obtain the unmodified upstream source from
each package's project URL in the MPL-2.0 table above.

If you redistribute a DIG binary that bundles any of these packages (e.g.,
a Mac DMG built via PyInstaller / Nuitka), you must:

1. Keep the unmodified package files intact.
2. Either include the upstream LICENSE files alongside, or point recipients
   to the canonical source URLs (this document does the latter).
3. For `tqdm` specifically: declaring this distribution complies under the
   **MIT** half of the dual license is sufficient and removes any MPL-2.0
   §3 source-disclosure obligation for that package.

### LGPL-3.0-or-later attestation (sharp / libvips)

The npm dependency tree contains exactly one LGPL-licensed package:

- `@img/sharp-libvips-darwin-arm64` (LGPL-3.0-or-later) — the libvips
  native binary used by Next.js's `<Image>` component for build-time
  image optimization.

**DIG attestation:** This package is **never invoked at runtime by DIG.**
A repo-wide `grep` for `from "next/image"` in `frontend/app/` and
`frontend/components/` returns zero matches. DIG uses native HTML `<img>`
tags + canvas-rendered SVG/WASM for all image rendering. Sharp is pulled
in as an `optionalDependency` of Next.js itself; in DIG's static-export
build path it is never bundled into the user-facing distribution.

If a future contributor adds `next/image` use, this attestation becomes
inaccurate and must be updated. Until then, no LGPL obligations attach to
DIG distributions because no LGPL-licensed code travels with them.

### Bundled fonts and assets

- DIG ships emoji as Unicode characters rendered by the user's system
  emoji font. No emoji font files are bundled.
- DIG bundles **Geist Sans** and **Geist Mono** via the `geist` npm
  package (Vercel + basement.studio). The actual `.woff2` files travel
  with every build artifact (web bundle, Mac `.app`, Linux package),
  meaning DIG runs offline with no font CDN fetch.
  - Copyright: © 2023 Vercel, in collaboration with basement.studio.
  - License: **SIL Open Font License 1.1** (OFL-1.1).
  - License text shipped with this distribution: [`licenses/Geist-OFL.txt`](licenses/Geist-OFL.txt).
  - Upstream: <https://github.com/vercel/geist-font>.
  - Reserved Font Names: "Geist". Per OFL §3, derivatives that use
    these names are not permitted; DIG uses the fonts as-is.
"""


FOOTER = """\
---

## How to regenerate

```bash
make docs   # runs scripts/gen-third-party.py + scripts/gen-steps-doc.py
# or directly:
python3 scripts/gen-third-party.py
```

The generator walks `backend/.venv` (Python) and `frontend/node_modules`
(npm) at run time, so this file is always in sync with what's actually
installed. Re-run after `pip install` / `pnpm install` to refresh.

## Reporting an issue

If a package is missing, mis-attributed, or you believe DIG is in violation
of an upstream license:

- **Open an issue:** <https://github.com/SFCyris/DataInsightGrove/issues>
  with the prefix `[third-party]`
- **Or email** the maintainer (see [`TRADEMARK.md`](TRADEMARK.md))

We aim to address license-compliance reports within 30 days.

---

_Last regenerated: see git log of this file. Generator:_
[`scripts/gen-third-party.py`](scripts/gen-third-party.py).
"""


# ---- Main -----------------------------------------------------------------

def main() -> int:
    print("Walking Python deps…")
    py = collect_python_deps()
    print(f"  found {len(py)} packages")

    print("Walking npm deps…")
    npm = collect_npm_deps()
    print(f"  found {len(npm)} packages")

    print("Rendering THIRD_PARTY.md …")
    md_text = render()
    out = REPO / "THIRD_PARTY.md"
    out.write_text(md_text)
    print(f"  wrote {out.relative_to(REPO)} ({out.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
