#!/usr/bin/env node
/**
 * Copy DuckDB-WASM bundles from node_modules into frontend/public/duckdb-wasm/.
 *
 * Run automatically as part of `pnpm postinstall` and `pnpm build`. Idempotent
 * — copies only when source is newer than dest. Skips sourcemaps to keep the
 * bundled size to ~24 MB total (vs ~110 MB with sourcemaps).
 *
 * Why bundled: DIG is a self-hosted tool; depending on jsDelivr at runtime
 * breaks offline use, leaks "user X opened DIG" to a third party, and exposes
 * us to CDN supply-chain risk. See docs/DECISIONS/0001-duckdb-wasm-hosting.md.
 */
import {
  copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, statSync,
  writeFileSync,
} from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(here, "..", "node_modules", "@duckdb", "duckdb-wasm", "dist");
const DST = resolve(here, "..", "public", "duckdb-wasm");

// All 3 wasm variants + matching browser workers. Excludes node-* (server-only)
// and *.map (sourcemaps — not needed in production, ~80 MB).
const WANTED = [
  "duckdb-mvp.wasm",
  "duckdb-eh.wasm",
  "duckdb-coi.wasm",
  "duckdb-browser-mvp.worker.js",
  "duckdb-browser-eh.worker.js",
  "duckdb-browser-coi.worker.js",
  "duckdb-browser-coi.pthread.worker.js",
];

function copyIfChanged(src, dst) {
  if (existsSync(dst)) {
    const ss = statSync(src);
    const ds = statSync(dst);
    if (ds.mtimeMs >= ss.mtimeMs && ds.size === ss.size) return false;
  }
  copyFileSync(src, dst);
  return true;
}

if (!existsSync(SRC)) {
  console.error(`copy-duckdb-wasm: source dir missing: ${SRC}`);
  console.error("  Did you run `pnpm install`?");
  process.exit(1);
}

mkdirSync(DST, { recursive: true });

const present = new Set(readdirSync(SRC));
let copied = 0;
let skipped = 0;
let bytes = 0;

for (const file of WANTED) {
  if (!present.has(file)) {
    console.warn(`copy-duckdb-wasm: ${file} not found in source — skipping`);
    continue;
  }
  const src = join(SRC, file);
  const dst = join(DST, file);
  if (copyIfChanged(src, dst)) {
    copied++;
    bytes += statSync(src).size;
  } else {
    skipped++;
  }
}

// NOTICE.txt — preserves the upstream MIT attribution next to the bundled
// binaries. Required by MIT once we redistribute "substantial portions"
// (the wasm binaries definitely qualify). Regenerated on every run so
// version bumps stay accurate.
const upstreamPkg = JSON.parse(
  readFileSync(join(SRC, "..", "package.json"), "utf8"),
);
const noticeBody = `DuckDB-WASM browser bundles — third-party notice
=================================================

These files are bundled with DataInsightGrove™ ("DIG"), distributed under
the MIT license listed below. They are unmodified copies of the upstream
@duckdb/duckdb-wasm npm package, copied verbatim from node_modules at
build time by frontend/scripts/copy-duckdb-wasm.mjs.

Upstream:    https://github.com/duckdb/duckdb-wasm
Version:     ${upstreamPkg.version}
License:     ${upstreamPkg.license}
Copyright:   © DuckDB Foundation, DuckDB Labs, and contributors.

Files in this directory (${WANTED.length}):
${WANTED.map((f) => `  - ${f}`).join("\n")}

------------------------------------------------------------------------
The MIT License (MIT)
------------------------------------------------------------------------

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
THE SOFTWARE.

------------------------------------------------------------------------
DataInsightGrove
------------------------------------------------------------------------

DIG's own source is licensed AGPL-3.0-or-later — see the top-level LICENSE
file. The DataInsightGrove name and 🌳 logo are unregistered trademarks of
Sebastian Cyris — see the top-level TRADEMARK.md.

For full third-party attribution across DIG's entire dependency tree, see
THIRD_PARTY.md at the repository root:
  https://github.com/SFCyris/DataInsightGrove/blob/main/THIRD_PARTY.md
`;
writeFileSync(join(DST, "NOTICE.txt"), noticeBody);

const mb = (bytes / 1024 / 1024).toFixed(1);
console.log(
  `copy-duckdb-wasm: ${copied} file(s) copied (${mb} MB), ${skipped} unchanged → public/duckdb-wasm/ (+ NOTICE.txt)`,
);
