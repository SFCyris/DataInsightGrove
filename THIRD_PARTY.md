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

## Summary

- Total Python dependencies (transitive): **78**
- Total npm dependencies (production, transitive): **461**

### By license family

| Family | Python | npm |
|---|---:|---:|
| LGPL | 0 | 1 |
| MPL-2.0 | 3 | 0 |
| Apache-2.0 | 5 | 10 |
| BSD | 27 | 14 |
| BlueOak | 0 | 2 |
| CC-BY | 0 | 1 |
| ISC | 0 | 58 |
| MIT | 41 | 372 |
| Other / Unclear | 0 | 1 |
| PSF | 2 | 1 |
| Unlicense | 0 | 1 |


## Per-family attribution

---

## MIT

### MIT (Python, 41 packages)

| Package | Version | License | Source / project URL |
|---|---|---|---|
| `aiosqlite` | 0.22.1 | MIT License | <https://aiosqlite.omnilib.dev> |
| `alembic` | 1.18.4 | MIT | <https://alembic.sqlalchemy.org> |
| `duckdb` | 1.5.2 | MIT License | <https://duckdb.org/docs/stable/clients/python/overview> |
| `fastapi` | 0.136.1 | MIT | <https://github.com/fastapi/fastapi> |
| `jsonschema` | 4.26.0 | MIT | <https://github.com/python-jsonschema/jsonschema> |
| `mypy` | 1.20.2 | MIT | <https://www.mypy-lang.org/> |
| `openpyxl` | 3.1.5 | MIT | <https://openpyxl.readthedocs.io> |
| `polars` | 1.40.1 | MIT License | <https://www.pola.rs/> |
| `pydantic` | 2.13.3 | MIT | <https://github.com/pydantic/pydantic> |
| `pytest` | 9.0.3 | MIT | <https://docs.pytest.org/en/stable/changelog.html> |
| `python-ulid` | 3.1.0 | MIT | <https://github.com/mdomke/python-ulid> |
| `ruff` | 0.15.12 | MIT | <https://docs.astral.sh/ruff> |
| `SQLAlchemy` | 2.0.49 | MIT | <https://www.sqlalchemy.org> |
| `annotated-doc` | 0.0.4 | MIT | <https://github.com/fastapi/annotated-doc> |
| `annotated-types` | 0.7.0 | MIT License | <https://github.com/annotated-types/annotated-types> |
| `anyio` | 4.13.0 | MIT | <https://anyio.readthedocs.io/en/latest/> |
| `attrs` | 26.1.0 | MIT | <https://www.attrs.org/> |
| `et_xmlfile` | 2.0.0 | MIT | <https://foss.heptapod.net/openpyxl/et_xmlfile> |
| `fonttools` | 4.62.1 | MIT | <http://github.com/fonttools/fonttools> |
| `greenlet` | 3.5.0 | MIT AND PSF-2.0 | <https://greenlet.readthedocs.io> |
| `h11` | 0.16.0 | MIT | <https://github.com/python-hyper/h11> |
| `httptools` | 0.7.1 | MIT | <https://github.com/MagicStack/httptools> |
| `iniconfig` | 2.3.0 | MIT | <https://github.com/pytest-dev/iniconfig> |
| `jsonschema-specifications` | 2025.9.1 | MIT | <https://jsonschema-specifications.readthedocs.io/> |
| `librt` | 0.9.0 | MIT | <https://github.com/mypyc/librt> |
| `Mako` | 1.3.12 | MIT | <https://www.makotemplates.org/> |
| `mypy_extensions` | 1.1.0 | MIT | <https://github.com/python/mypy_extensions> |
| `pillow` | 12.2.0 | MIT-CMU | <https://pillow.readthedocs.io/en/stable/releasenotes/index.html> |
| `pip` | 26.1 | MIT | <https://pip.pypa.io/en/stable/news/> |
| `pluggy` | 1.6.0 | MIT | — |
| `polars-runtime-32` | 1.40.1 | MIT | <https://www.pola.rs/> |
| `pydantic_core` | 2.46.3 | MIT | <https://github.com/pydantic/pydantic> |
| `pyparsing` | 3.3.2 | MIT | <https://pyparsing-docs.readthedocs.io/en/latest/> |
| `PyYAML` | 6.0.3 | MIT | <https://pyyaml.org/> |
| `referencing` | 0.37.0 | MIT | <https://referencing.readthedocs.io/> |
| `rpds-py` | 0.30.0 | MIT | <https://rpds.readthedocs.io/> |
| `setuptools` | 65.5.0 | MIT License | <https://github.com/pypa/setuptools> |
| `six` | 1.17.0 | MIT | <https://github.com/benjaminp/six> |
| `typing-inspection` | 0.4.2 | MIT | <https://github.com/pydantic/typing-inspection> |
| `uvloop` | 0.22.1 | MIT License | <https://github.com/MagicStack/uvloop> |
| `watchfiles` | 1.1.1 | MIT | <https://github.com/samuelcolvin/watchfiles> |

### MIT (npm, 372 packages)

| Package | Version | License | Source / project URL |
|---|---|---|---|
| `@babel/code-frame` | 7.29.0 | MIT | <https://babel.dev/docs/en/next/babel-code-frame> |
| `@babel/compat-data` | 7.29.3 | MIT | <https://github.com/babel/babel#readme> |
| `@babel/core` | 7.29.0 | MIT | <https://babel.dev/docs/en/next/babel-core> |
| `@babel/generator` | 7.29.1 | MIT | <https://babel.dev/docs/en/next/babel-generator> |
| `@babel/helper-annotate-as-pure` | 7.27.3 | MIT | <https://babel.dev/docs/en/next/babel-helper-annotate-as-pure> |
| `@babel/helper-compilation-targets` | 7.28.6 | MIT | <https://github.com/babel/babel#readme> |
| `@babel/helper-create-class-features-plugin` | 7.29.3 | MIT | <https://github.com/babel/babel#readme> |
| `@babel/helper-globals` | 7.28.0 | MIT | <https://github.com/babel/babel#readme> |
| `@babel/helper-member-expression-to-functions` | 7.28.5 | MIT | <https://babel.dev/docs/en/next/babel-helper-member-expression-to-functions> |
| `@babel/helper-module-imports` | 7.28.6 | MIT | <https://babel.dev/docs/en/next/babel-helper-module-imports> |
| `@babel/helper-module-transforms` | 7.28.6 | MIT | <https://babel.dev/docs/en/next/babel-helper-module-transforms> |
| `@babel/helper-optimise-call-expression` | 7.27.1 | MIT | <https://babel.dev/docs/en/next/babel-helper-optimise-call-expression> |
| `@babel/helper-plugin-utils` | 7.28.6 | MIT | <https://babel.dev/docs/en/next/babel-helper-plugin-utils> |
| `@babel/helper-replace-supers` | 7.28.6 | MIT | <https://babel.dev/docs/en/next/babel-helper-replace-supers> |
| `@babel/helper-skip-transparent-expression-wrappers` | 7.27.1 | MIT | <https://github.com/babel/babel#readme> |
| `@babel/helper-string-parser` | 7.27.1 | MIT | <https://babel.dev/docs/en/next/babel-helper-string-parser> |
| `@babel/helper-validator-identifier` | 7.28.5 | MIT | <https://github.com/babel/babel#readme> |
| `@babel/helper-validator-option` | 7.27.1 | MIT | <https://github.com/babel/babel#readme> |
| `@babel/helpers` | 7.29.2 | MIT | <https://babel.dev/docs/en/next/babel-helpers> |
| `@babel/parser` | 7.29.3 | MIT | <https://babel.dev/docs/en/next/babel-parser> |
| `@babel/plugin-syntax-jsx` | 7.28.6 | MIT | <https://babel.dev/docs/en/next/babel-plugin-syntax-jsx> |
| `@babel/plugin-syntax-typescript` | 7.28.6 | MIT | <https://babel.dev/docs/en/next/babel-plugin-syntax-typescript> |
| `@babel/plugin-transform-modules-commonjs` | 7.28.6 | MIT | <https://babel.dev/docs/en/next/babel-plugin-transform-modules-commonjs> |
| `@babel/plugin-transform-typescript` | 7.28.6 | MIT | <https://babel.dev/docs/en/next/babel-plugin-transform-typescript> |
| `@babel/preset-typescript` | 7.28.5 | MIT | <https://babel.dev/docs/en/next/babel-preset-typescript> |
| `@babel/runtime` | 7.29.2 | MIT | <https://babel.dev/docs/en/next/babel-runtime> |
| `@babel/template` | 7.28.6 | MIT | <https://babel.dev/docs/en/next/babel-template> |
| `@babel/traverse` | 7.29.0 | MIT | <https://babel.dev/docs/en/next/babel-traverse> |
| `@babel/types` | 7.29.0 | MIT | <https://babel.dev/docs/en/next/babel-types> |
| `@base-ui/react` | 1.4.1 | MIT | <https://base-ui.com> |
| `@base-ui/utils` | 0.2.8 | MIT | <https://github.com/mui/base-ui#readme> |
| `@duckdb/duckdb-wasm` | 1.33.1-dev45.0 | MIT | <https://github.com/duckdb/duckdb-wasm#readme> |
| `@ecies/ciphers` | 0.2.6 | MIT | <https://github.com/ecies/js-ciphers#readme> |
| `@floating-ui/core` | 1.7.5 | MIT | <https://floating-ui.com> |
| `@floating-ui/dom` | 1.7.6 | MIT | <https://floating-ui.com> |
| `@floating-ui/react-dom` | 2.1.8 | MIT | <https://floating-ui.com/docs/react-dom> |
| `@floating-ui/utils` | 0.2.11 | MIT | <https://floating-ui.com> |
| `@hono/node-server` | 1.19.14 | MIT | <https://github.com/honojs/node-server> |
| `@img/colour` | 1.1.0 | MIT | <https://github.com/lovell/colour#readme> |
| `@inquirer/ansi` | 2.0.5 | MIT | <https://github.com/SBoudrias/Inquirer.js/blob/main/packages/ansi/README.md> |
| `@inquirer/confirm` | 6.0.12 | MIT | <https://github.com/SBoudrias/Inquirer.js/blob/main/packages/confirm/README.md> |
| `@inquirer/core` | 11.1.9 | MIT | <https://github.com/SBoudrias/Inquirer.js/blob/main/packages/core/README.md> |
| `@inquirer/figures` | 2.0.5 | MIT | <https://github.com/SBoudrias/Inquirer.js#readme> |
| `@inquirer/type` | 4.0.5 | MIT | <https://github.com/SBoudrias/Inquirer.js#readme> |
| `@jridgewell/gen-mapping` | 0.3.13 | MIT | <https://github.com/jridgewell/sourcemaps/tree/main/packages/gen-mapping> |
| `@jridgewell/remapping` | 2.3.5 | MIT | <https://github.com/jridgewell/sourcemaps/tree/main/packages/remapping> |
| `@jridgewell/resolve-uri` | 3.1.2 | MIT | <https://github.com/jridgewell/resolve-uri#readme> |
| `@jridgewell/sourcemap-codec` | 1.5.5 | MIT | <https://github.com/jridgewell/sourcemaps/tree/main/packages/sourcemap-codec> |
| `@jridgewell/trace-mapping` | 0.3.31 | MIT | <https://github.com/jridgewell/sourcemaps/tree/main/packages/trace-mapping> |
| `@modelcontextprotocol/sdk` | 1.29.0 | MIT | <https://modelcontextprotocol.io> |
| `@mswjs/interceptors` | 0.41.7 | MIT | <https://github.com/mswjs/interceptors#readme> |
| `@next/env` | 16.2.4 | MIT | <https://github.com/vercel/next.js#readme> |
| `@next/swc-darwin-arm64` | 16.2.4 | MIT | <https://github.com/vercel/next.js#readme> |
| `@noble/ciphers` | 1.3.0 | MIT | <https://paulmillr.com/noble/> |
| `@noble/curves` | 1.9.7 | MIT | <https://paulmillr.com/noble/> |
| `@noble/hashes` | 1.8.0 | MIT | <https://paulmillr.com/noble/> |
| `@nodelib/fs.scandir` | 2.1.5 | MIT | <https://github.com/nodelib/nodelib/tree/master#readme> |
| `@nodelib/fs.stat` | 2.0.5 | MIT | <https://github.com/nodelib/nodelib/tree/master#readme> |
| `@nodelib/fs.walk` | 1.2.8 | MIT | <https://github.com/nodelib/nodelib/tree/master#readme> |
| `@open-draft/deferred-promise` | 2.2.0 | MIT | <https://github.com/open-draft/deferred-promise#readme> |
| `@open-draft/logger` | 0.3.0 | MIT | <https://github.com/open-draft/logger#readme> |
| `@open-draft/until` | 2.1.0 | MIT | <https://github.com/open-draft/until#readme> |
| `@radix-ui/primitive` | 1.1.3 | MIT | <https://radix-ui.com/primitives> |
| `@radix-ui/react-compose-refs` | 1.1.2 | MIT | <https://radix-ui.com/primitives> |
| `@radix-ui/react-context` | 1.1.2 | MIT | <https://radix-ui.com/primitives> |
| `@radix-ui/react-dialog` | 1.1.15 | MIT | <https://radix-ui.com/primitives> |
| `@radix-ui/react-dismissable-layer` | 1.1.11 | MIT | <https://radix-ui.com/primitives> |
| `@radix-ui/react-focus-guards` | 1.1.3 | MIT | <https://radix-ui.com/primitives> |
| `@radix-ui/react-focus-scope` | 1.1.7 | MIT | <https://radix-ui.com/primitives> |
| `@radix-ui/react-id` | 1.1.1 | MIT | <https://radix-ui.com/primitives> |
| `@radix-ui/react-portal` | 1.1.9 | MIT | <https://radix-ui.com/primitives> |
| `@radix-ui/react-presence` | 1.1.5 | MIT | <https://radix-ui.com/primitives> |
| `@radix-ui/react-primitive` | 2.1.3 | MIT | <https://radix-ui.com/primitives> |
| `@radix-ui/react-slot` | 1.2.3 | MIT | <https://radix-ui.com/primitives> |
| `@radix-ui/react-use-callback-ref` | 1.1.1 | MIT | <https://radix-ui.com/primitives> |
| `@radix-ui/react-use-controllable-state` | 1.2.2 | MIT | <https://radix-ui.com/primitives> |
| `@radix-ui/react-use-effect-event` | 0.0.2 | MIT | <https://radix-ui.com/primitives> |
| `@radix-ui/react-use-escape-keydown` | 1.1.1 | MIT | <https://radix-ui.com/primitives> |
| `@radix-ui/react-use-layout-effect` | 1.1.1 | MIT | <https://radix-ui.com/primitives> |
| `@sec-ant/readable-stream` | 0.4.1 | MIT | <https://github.com/Sec-ant/readable-stream> |
| `@sindresorhus/merge-streams` | 4.0.0 | MIT | <https://github.com/sindresorhus/merge-streams#readme> |
| `@tanstack/query-core` | 5.100.7 | MIT | <https://tanstack.com/query> |
| `@tanstack/react-query` | 5.100.7 | MIT | <https://tanstack.com/query> |
| `@ts-morph/common` | 0.27.0 | MIT | <https://github.com/dsherret/ts-morph#readme> |
| `@types/command-line-args` | 5.2.3 | MIT | <https://github.com/DefinitelyTyped/DefinitelyTyped/tree/master/types/command-line-args> |
| `@types/command-line-usage` | 5.0.4 | MIT | <https://github.com/DefinitelyTyped/DefinitelyTyped/tree/master/types/command-line-usage> |
| `@types/d3-color` | 3.1.3 | MIT | <https://github.com/DefinitelyTyped/DefinitelyTyped/tree/master/types/d3-color> |
| `@types/d3-drag` | 3.0.7 | MIT | <https://github.com/DefinitelyTyped/DefinitelyTyped/tree/master/types/d3-drag> |
| `@types/d3-interpolate` | 3.0.4 | MIT | <https://github.com/DefinitelyTyped/DefinitelyTyped/tree/master/types/d3-interpolate> |
| `@types/d3-selection` | 3.0.11 | MIT | <https://github.com/DefinitelyTyped/DefinitelyTyped/tree/master/types/d3-selection> |
| `@types/d3-transition` | 3.0.9 | MIT | <https://github.com/DefinitelyTyped/DefinitelyTyped/tree/master/types/d3-transition> |
| `@types/d3-zoom` | 3.0.8 | MIT | <https://github.com/DefinitelyTyped/DefinitelyTyped/tree/master/types/d3-zoom> |
| `@types/node` | 20.19.39 | MIT | <https://github.com/DefinitelyTyped/DefinitelyTyped/tree/master/types/node> |
| `@types/react` | 19.2.14 | MIT | <https://github.com/DefinitelyTyped/DefinitelyTyped/tree/master/types/react> |
| `@types/react-dom` | 19.2.3 | MIT | <https://github.com/DefinitelyTyped/DefinitelyTyped/tree/master/types/react-dom> |
| `@types/set-cookie-parser` | 2.4.10 | MIT | <https://github.com/DefinitelyTyped/DefinitelyTyped/tree/master/types/set-cookie-parser> |
| `@types/statuses` | 2.0.6 | MIT | <https://github.com/DefinitelyTyped/DefinitelyTyped/tree/master/types/statuses> |
| `@types/validate-npm-package-name` | 4.0.2 | MIT | <https://github.com/DefinitelyTyped/DefinitelyTyped/tree/master/types/validate-npm-package-name> |
| `@xyflow/react` | 12.10.2 | MIT | <https://reactflow.dev> |
| `@xyflow/system` | 0.0.76 | MIT | <https://github.com/xyflow/xyflow#readme> |
| `accepts` | 2.0.0 | MIT | <https://github.com/jshttp/accepts#readme> |
| `ag-charts-types` | 13.2.1 | MIT | <https://www.ag-grid.com/charts/> |
| `ag-grid-community` | 35.2.1 | MIT | <https://www.ag-grid.com/> |
| `ag-grid-react` | 35.2.1 | MIT | <https://www.ag-grid.com/react-grid/> |
| `agent-base` | 7.1.4 | MIT | <https://github.com/TooTallNate/proxy-agents#readme> |
| `ajv` | 8.20.0 | MIT | <https://ajv.js.org> |
| `ajv-formats` | 3.0.1 | MIT | <https://github.com/ajv-validator/ajv-formats#readme> |
| `ansi-regex` | 5.0.1 | MIT | <https://github.com/chalk/ansi-regex#readme> |
| `ansi-styles` | 4.3.0 | MIT | <https://github.com/chalk/ansi-styles#readme> |
| `aria-hidden` | 1.2.6 | MIT | <https://github.com/theKashey/aria-hidden#readme> |
| `array-back` | 3.1.0 | MIT | <https://github.com/75lb/array-back#readme> |
| `ast-types` | 0.16.1 | MIT | <http://github.com/benjamn/ast-types> |
| `attr-accept` | 2.2.5 | MIT | <https://github.com/react-dropzone/attr-accept#readme> |
| `balanced-match` | 4.0.4 | MIT | <https://github.com/juliangruber/balanced-match#readme> |
| `binary-search-bounds` | 2.0.5 | MIT | <https://github.com/mikolalysenko/binary-search-bounds#readme> |
| `body-parser` | 2.2.2 | MIT | <https://github.com/expressjs/body-parser#readme> |
| `brace-expansion` | 5.0.5 | MIT | <https://github.com/juliangruber/brace-expansion#readme> |
| `braces` | 3.0.3 | MIT | <https://github.com/micromatch/braces> |
| `browserslist` | 4.28.2 | MIT | <https://github.com/browserslist/browserslist#readme> |
| `bundle-name` | 4.1.0 | MIT | <https://github.com/sindresorhus/bundle-name#readme> |
| `bytes` | 3.1.2 | MIT | <https://github.com/visionmedia/bytes.js#readme> |
| `call-bind-apply-helpers` | 1.0.2 | MIT | <https://github.com/ljharb/call-bind-apply-helpers#readme> |
| `call-bound` | 1.0.4 | MIT | <https://github.com/ljharb/call-bound#readme> |
| `callsites` | 3.1.0 | MIT | <https://github.com/sindresorhus/callsites#readme> |
| `chalk` | 4.1.2 | MIT | <https://github.com/chalk/chalk#readme> |
| `chalk-template` | 0.4.0 | MIT | <https://github.com/chalk/chalk-template#readme> |
| `classcat` | 5.0.5 | MIT | <https://github.com/jorgebucaran/classcat#readme> |
| `cli-cursor` | 5.0.0 | MIT | <https://github.com/sindresorhus/cli-cursor#readme> |
| `cli-spinners` | 2.9.2 | MIT | <https://github.com/sindresorhus/cli-spinners#readme> |
| `client-only` | 0.0.1 | MIT | <https://reactjs.org/> |
| `clsx` | 2.1.1 | MIT | <https://github.com/lukeed/clsx#readme> |
| `cmdk` | 1.1.1 | MIT | <https://github.com/pacocoursey/cmdk#readme> |
| `code-block-writer` | 13.0.3 | MIT | <https://github.com/dsherret/code-block-writer#readme> |
| `color-convert` | 2.0.1 | MIT | <https://github.com/Qix-/color-convert#readme> |
| `color-name` | 1.1.4 | MIT | <https://github.com/colorjs/color-name> |
| `command-line-args` | 5.2.1 | MIT | <https://github.com/75lb/command-line-args#readme> |
| `command-line-usage` | 7.0.4 | MIT | <https://github.com/75lb/command-line-usage#readme> |
| `commander` | 7.2.0 | MIT | <https://github.com/tj/commander.js#readme> |
| `content-disposition` | 1.1.0 | MIT | <https://github.com/jshttp/content-disposition#readme> |
| `content-type` | 1.0.5 | MIT | <https://github.com/jshttp/content-type#readme> |
| `convert-source-map` | 2.0.0 | MIT | <https://github.com/thlorenz/convert-source-map> |
| `cookie` | 0.7.2 | MIT | <https://github.com/jshttp/cookie#readme> |
| `cookie-signature` | 1.2.2 | MIT | <https://github.com/visionmedia/node-cookie-signature#readme> |
| `cors` | 2.8.6 | MIT | <https://github.com/expressjs/cors#readme> |
| `cosmiconfig` | 9.0.1 | MIT | <https://github.com/cosmiconfig/cosmiconfig#readme> |
| `cross-spawn` | 7.0.6 | MIT | <https://github.com/moxystudio/node-cross-spawn> |
| `cssesc` | 3.0.0 | MIT | <https://mths.be/cssesc> |
| `csstype` | 3.2.3 | MIT | <https://github.com/frenic/csstype#readme> |
| `data-uri-to-buffer` | 4.0.1 | MIT | <https://github.com/TooTallNate/node-data-uri-to-buffer> |
| `debug` | 4.4.3 | MIT | <https://github.com/debug-js/debug#readme> |
| `dedent` | 1.7.2 | MIT | <https://github.com/dmnd/dedent> |
| `deepmerge` | 4.3.1 | MIT | <https://github.com/TehShrike/deepmerge> |
| `default-browser` | 5.5.0 | MIT | <https://github.com/sindresorhus/default-browser#readme> |
| `default-browser-id` | 5.0.1 | MIT | <https://github.com/sindresorhus/default-browser-id#readme> |
| `define-lazy-prop` | 3.0.0 | MIT | <https://github.com/sindresorhus/define-lazy-prop#readme> |
| `depd` | 2.0.0 | MIT | <https://github.com/dougwilson/nodejs-depd#readme> |
| `detect-node-es` | 1.1.0 | MIT | <https://github.com/thekashey/detect-node> |
| `dunder-proto` | 1.0.1 | MIT | <https://github.com/es-shims/dunder-proto#readme> |
| `eciesjs` | 0.4.18 | MIT | <https://github.com/ecies/js#readme> |
| `ee-first` | 1.1.1 | MIT | <https://github.com/jonathanong/ee-first#readme> |
| `emoji-regex` | 8.0.0 | MIT | <https://mths.be/emoji-regex> |
| `encodeurl` | 2.0.0 | MIT | <https://github.com/pillarjs/encodeurl#readme> |
| `env-paths` | 2.2.1 | MIT | <https://github.com/sindresorhus/env-paths#readme> |
| `error-ex` | 1.3.4 | MIT | <https://github.com/qix-/node-error-ex#readme> |
| `es-define-property` | 1.0.1 | MIT | <https://github.com/ljharb/es-define-property#readme> |
| `es-errors` | 1.3.0 | MIT | <https://github.com/ljharb/es-errors#readme> |
| `es-object-atoms` | 1.1.1 | MIT | <https://github.com/ljharb/es-object-atoms#readme> |
| `escalade` | 3.2.0 | MIT | <https://github.com/lukeed/escalade#readme> |
| `escape-html` | 1.0.3 | MIT | <https://github.com/component/escape-html#readme> |
| `etag` | 1.8.1 | MIT | <https://github.com/jshttp/etag#readme> |
| `eventsource` | 3.0.7 | MIT | <https://github.com/EventSource/eventsource#readme> |
| `eventsource-parser` | 3.0.8 | MIT | <https://github.com/rexxars/eventsource-parser#readme> |
| `execa` | 5.1.1 | MIT | <https://github.com/sindresorhus/execa#readme> |
| `express` | 5.2.1 | MIT | <https://expressjs.com/> |
| `express-rate-limit` | 8.4.1 | MIT | <https://github.com/express-rate-limit/express-rate-limit> |
| `fast-deep-equal` | 3.1.3 | MIT | <https://github.com/epoberezkin/fast-deep-equal#readme> |
| `fast-glob` | 3.3.3 | MIT | <https://github.com/mrmlnc/fast-glob#readme> |
| `fast-string-truncated-width` | 3.0.3 | MIT | <https://github.com/fabiospampinato/fast-string-truncated-width#readme> |
| `fast-string-width` | 3.0.2 | MIT | <https://github.com/fabiospampinato/fast-string-width#readme> |
| `fast-wrap-ansi` | 0.2.0 | MIT | <https://github.com/43081j/fast-wrap-ansi#readme> |
| `fdir` | 6.5.0 | MIT | <https://github.com/thecodrr/fdir#readme> |
| `fetch-blob` | 3.2.0 | MIT | <https://github.com/node-fetch/fetch-blob#readme> |
| `figures` | 6.1.0 | MIT | <https://github.com/sindresorhus/figures#readme> |
| `file-selector` | 2.1.2 | MIT | <https://github.com/react-dropzone/file-selector> |
| `fill-range` | 7.1.1 | MIT | <https://github.com/jonschlinkert/fill-range> |
| `finalhandler` | 2.1.1 | MIT | <https://github.com/pillarjs/finalhandler#readme> |
| `find-replace` | 3.0.0 | MIT | <https://github.com/75lb/find-replace#readme> |
| `formdata-polyfill` | 4.0.10 | MIT | <https://github.com/jimmywarting/FormData#readme> |
| `forwarded` | 0.2.0 | MIT | <https://github.com/jshttp/forwarded#readme> |
| `framer-motion` | 12.38.0 | MIT | <https://github.com/motiondivision/motion#readme> |
| `fresh` | 2.0.0 | MIT | <https://github.com/jshttp/fresh#readme> |
| `fs-extra` | 11.3.4 | MIT | <https://github.com/jprichardson/node-fs-extra> |
| `function-bind` | 1.1.2 | MIT | <https://github.com/Raynos/function-bind> |
| `fuzzysort` | 3.1.0 | MIT | <https://github.com/farzher/fuzzysort#readme> |
| `gensync` | 1.0.0-beta.2 | MIT | <https://github.com/loganfsmyth/gensync> |
| `get-east-asian-width` | 1.5.0 | MIT | <https://github.com/sindresorhus/get-east-asian-width#readme> |
| `get-intrinsic` | 1.3.0 | MIT | <https://github.com/ljharb/get-intrinsic#readme> |
| `get-nonce` | 1.0.1 | MIT | <https://github.com/theKashey/get-nonce> |
| `get-own-enumerable-keys` | 1.0.0 | MIT | <https://github.com/sindresorhus/get-own-enumerable-keys#readme> |
| `get-proto` | 1.0.1 | MIT | <https://github.com/ljharb/get-proto#readme> |
| `get-stream` | 6.0.1 | MIT | <https://github.com/sindresorhus/get-stream#readme> |
| `gopd` | 1.2.0 | MIT | <https://github.com/ljharb/gopd#readme> |
| `graphql` | 16.13.2 | MIT | <https://github.com/graphql/graphql-js> |
| `has-flag` | 4.0.0 | MIT | <https://github.com/sindresorhus/has-flag#readme> |
| `has-symbols` | 1.1.0 | MIT | <https://github.com/ljharb/has-symbols#readme> |
| `hasown` | 2.0.3 | MIT | <https://github.com/inspect-js/hasOwn#readme> |
| `headers-polyfill` | 5.0.1 | MIT | <https://github.com/mswjs/headers-polyfill#readme> |
| `hono` | 4.12.16 | MIT | <https://hono.dev> |
| `http-errors` | 2.0.1 | MIT | <https://github.com/jshttp/http-errors#readme> |
| `https-proxy-agent` | 7.0.6 | MIT | <https://github.com/TooTallNate/proxy-agents#readme> |
| `iconv-lite` | 0.6.3 | MIT | <https://github.com/pillarjs/iconv-lite> |
| `ignore` | 5.3.2 | MIT | <https://github.com/kaelzhang/node-ignore#readme> |
| `import-fresh` | 3.3.1 | MIT | <https://github.com/sindresorhus/import-fresh#readme> |
| `interval-tree-1d` | 1.0.4 | MIT | <https://github.com/mikolalysenko/interval-tree-1d#readme> |
| `ip-address` | 10.1.0 | MIT | <https://github.com/beaugunderson/ip-address#readme> |
| `ipaddr.js` | 1.9.1 | MIT | <https://github.com/whitequark/ipaddr.js#readme> |
| `is-arrayish` | 0.2.1 | MIT | <https://github.com/qix-/node-is-arrayish#readme> |
| `is-docker` | 3.0.0 | MIT | <https://github.com/sindresorhus/is-docker#readme> |
| `is-extglob` | 2.1.1 | MIT | <https://github.com/jonschlinkert/is-extglob> |
| `is-fullwidth-code-point` | 3.0.0 | MIT | <https://github.com/sindresorhus/is-fullwidth-code-point#readme> |
| `is-glob` | 4.0.3 | MIT | <https://github.com/micromatch/is-glob> |
| `is-in-ssh` | 1.0.0 | MIT | <https://github.com/sindresorhus/is-in-ssh#readme> |
| `is-inside-container` | 1.0.0 | MIT | <https://github.com/sindresorhus/is-inside-container#readme> |
| `is-interactive` | 2.0.0 | MIT | <https://github.com/sindresorhus/is-interactive#readme> |
| `is-node-process` | 1.2.0 | MIT | <https://github.com/mswjs/is-node-process#readme> |
| `is-number` | 7.0.0 | MIT | <https://github.com/jonschlinkert/is-number> |
| `is-obj` | 3.0.0 | MIT | <https://github.com/sindresorhus/is-obj#readme> |
| `is-plain-obj` | 4.1.0 | MIT | <https://github.com/sindresorhus/is-plain-obj#readme> |
| `is-promise` | 4.0.0 | MIT | <https://github.com/then/is-promise#readme> |
| `is-regexp` | 3.1.0 | MIT | <https://github.com/sindresorhus/is-regexp#readme> |
| `is-stream` | 2.0.1 | MIT | <https://github.com/sindresorhus/is-stream#readme> |
| `is-unicode-supported` | 1.3.0 | MIT | <https://github.com/sindresorhus/is-unicode-supported#readme> |
| `is-wsl` | 3.1.1 | MIT | <https://github.com/sindresorhus/is-wsl#readme> |
| `jose` | 6.2.3 | MIT | <https://github.com/panva/jose> |
| `js-tokens` | 4.0.0 | MIT | <https://github.com/lydell/js-tokens#readme> |
| `js-yaml` | 4.1.1 | MIT | <https://github.com/nodeca/js-yaml#readme> |
| `jsesc` | 3.1.0 | MIT | <https://mths.be/jsesc> |
| `json-bignum` | 0.0.3 | MIT | <https://github.com/datalanche/json-bignum> |
| `json-parse-even-better-errors` | 2.3.1 | MIT | <https://github.com/npm/json-parse-even-better-errors#readme> |
| `json-schema-traverse` | 1.0.0 | MIT | <https://github.com/epoberezkin/json-schema-traverse#readme> |
| `json5` | 2.2.3 | MIT | <http://json5.org/> |
| `jsonfile` | 6.2.1 | MIT | <https://github.com/jprichardson/node-jsonfile#readme> |
| `kleur` | 3.0.3 | MIT | <https://github.com/lukeed/kleur#readme> |
| `lines-and-columns` | 1.2.4 | MIT | <https://github.com/eventualbuddha/lines-and-columns#readme> |
| `lodash.camelcase` | 4.3.0 | MIT | <https://lodash.com/> |
| `log-symbols` | 6.0.0 | MIT | <https://github.com/sindresorhus/log-symbols#readme> |
| `loose-envify` | 1.4.0 | MIT | <https://github.com/zertosh/loose-envify> |
| `math-intrinsics` | 1.1.0 | MIT | <https://github.com/es-shims/math-intrinsics#readme> |
| `media-typer` | 1.1.0 | MIT | <https://github.com/jshttp/media-typer#readme> |
| `merge-descriptors` | 2.0.0 | MIT | <https://github.com/sindresorhus/merge-descriptors#readme> |
| `merge-stream` | 2.0.0 | MIT | <https://github.com/grncdr/merge-stream#readme> |
| `merge2` | 1.4.1 | MIT | <https://github.com/teambition/merge2> |
| `micromatch` | 4.0.8 | MIT | <https://github.com/micromatch/micromatch> |
| `mime-db` | 1.54.0 | MIT | <https://github.com/jshttp/mime-db#readme> |
| `mime-types` | 3.0.2 | MIT | <https://github.com/jshttp/mime-types#readme> |
| `mimic-fn` | 2.1.0 | MIT | <https://github.com/sindresorhus/mimic-fn#readme> |
| `mimic-function` | 5.0.1 | MIT | <https://github.com/sindresorhus/mimic-function#readme> |
| `minimist` | 1.2.8 | MIT | <https://github.com/minimistjs/minimist> |
| `motion` | 12.38.0 | MIT | <https://github.com/motiondivision/motion#readme> |
| `motion-dom` | 12.38.0 | MIT | <https://github.com/motiondivision/motion#readme> |
| `motion-utils` | 12.36.0 | MIT | <https://github.com/motiondivision/motion#readme> |
| `ms` | 2.1.3 | MIT | <https://github.com/vercel/ms#readme> |
| `msw` | 2.14.2 | MIT | <https://mswjs.io> |
| `nanoid` | 3.3.12 | MIT | <https://github.com/ai/nanoid#readme> |
| `negotiator` | 1.0.0 | MIT | <https://github.com/jshttp/negotiator#readme> |
| `next` | 16.2.4 | MIT | <https://nextjs.org> |
| `node-domexception` | 1.0.0 | MIT | <https://github.com/jimmywarting/node-domexception#readme> |
| `node-fetch` | 3.3.2 | MIT | <https://github.com/node-fetch/node-fetch> |
| `node-releases` | 2.0.38 | MIT | <https://github.com/chicoxyzzy/node-releases#readme> |
| `npm-run-path` | 4.0.1 | MIT | <https://github.com/sindresorhus/npm-run-path#readme> |
| `object-assign` | 4.1.1 | MIT | <https://github.com/sindresorhus/object-assign#readme> |
| `object-inspect` | 1.13.4 | MIT | <https://github.com/inspect-js/object-inspect> |
| `object-treeify` | 1.1.33 | MIT | <https://github.com/blackflux/object-treeify#readme> |
| `on-finished` | 2.4.1 | MIT | <https://github.com/jshttp/on-finished#readme> |
| `onetime` | 5.1.2 | MIT | <https://github.com/sindresorhus/onetime#readme> |
| `open` | 11.0.0 | MIT | <https://github.com/sindresorhus/open#readme> |
| `ora` | 8.2.0 | MIT | <https://github.com/sindresorhus/ora#readme> |
| `outvariant` | 1.4.3 | MIT | <https://github.com/open-draft/outvariant#readme> |
| `parent-module` | 1.0.1 | MIT | <https://github.com/sindresorhus/parent-module#readme> |
| `parse-json` | 5.2.0 | MIT | <https://github.com/sindresorhus/parse-json#readme> |
| `parse-ms` | 4.0.0 | MIT | <https://github.com/sindresorhus/parse-ms#readme> |
| `parseurl` | 1.3.3 | MIT | <https://github.com/pillarjs/parseurl#readme> |
| `path-browserify` | 1.0.1 | MIT | <https://github.com/browserify/path-browserify> |
| `path-key` | 3.1.1 | MIT | <https://github.com/sindresorhus/path-key#readme> |
| `path-to-regexp` | 6.3.0 | MIT | <https://github.com/pillarjs/path-to-regexp#readme> |
| `picomatch` | 2.3.2 | MIT | <https://github.com/micromatch/picomatch> |
| `pkce-challenge` | 5.0.1 | MIT | <https://github.com/crouchcd/pkce-challenge#readme> |
| `postcss` | 8.4.31 | MIT | <https://postcss.org/> |
| `postcss-selector-parser` | 7.1.1 | MIT | <https://github.com/postcss/postcss-selector-parser> |
| `powershell-utils` | 0.1.0 | MIT | <https://github.com/sindresorhus/powershell-utils#readme> |
| `pretty-ms` | 9.3.0 | MIT | <https://github.com/sindresorhus/pretty-ms#readme> |
| `prompts` | 2.4.2 | MIT | <https://github.com/terkelg/prompts#readme> |
| `prop-types` | 15.8.1 | MIT | <https://facebook.github.io/react/> |
| `proxy-addr` | 2.0.7 | MIT | <https://github.com/jshttp/proxy-addr#readme> |
| `queue-microtask` | 1.2.3 | MIT | <https://github.com/feross/queue-microtask> |
| `range-parser` | 1.2.1 | MIT | <https://github.com/jshttp/range-parser#readme> |
| `raw-body` | 3.0.2 | MIT | <https://github.com/stream-utils/raw-body#readme> |
| `react` | 19.2.4 | MIT | <https://react.dev/> |
| `react-dom` | 19.2.4 | MIT | <https://react.dev/> |
| `react-dropzone` | 15.0.0 | MIT | <https://github.com/react-dropzone/react-dropzone> |
| `react-is` | 16.13.1 | MIT | <https://reactjs.org/> |
| `react-remove-scroll` | 2.7.2 | MIT | <https://github.com/theKashey/react-remove-scroll#readme> |
| `react-remove-scroll-bar` | 2.3.8 | MIT | <https://github.com/theKashey/react-remove-scroll-bar#readme> |
| `react-style-singleton` | 2.2.3 | MIT | <https://github.com/theKashey/react-style-singleton#readme> |
| `recast` | 0.23.11 | MIT | <http://github.com/benjamn/recast> |
| `require-directory` | 2.1.1 | MIT | <https://github.com/troygoode/node-require-directory/> |
| `require-from-string` | 2.0.2 | MIT | <https://github.com/floatdrop/require-from-string#readme> |
| `reselect` | 5.1.1 | MIT | <https://github.com/reduxjs/reselect#readme> |
| `resolve-from` | 4.0.0 | MIT | <https://github.com/sindresorhus/resolve-from#readme> |
| `restore-cursor` | 5.1.0 | MIT | <https://github.com/sindresorhus/restore-cursor#readme> |
| `rettime` | 0.11.8 | MIT | <https://github.com/kettanaito/rettime#readme> |
| `reusify` | 1.1.0 | MIT | <https://github.com/mcollina/reusify#readme> |
| `router` | 2.2.0 | MIT | <https://github.com/pillarjs/router#readme> |
| `run-applescript` | 7.1.0 | MIT | <https://github.com/sindresorhus/run-applescript#readme> |
| `run-parallel` | 1.2.0 | MIT | <https://github.com/feross/run-parallel> |
| `safer-buffer` | 2.1.2 | MIT | <https://github.com/ChALkeR/safer-buffer#readme> |
| `scheduler` | 0.27.0 | MIT | <https://react.dev/> |
| `send` | 1.2.1 | MIT | <https://github.com/pillarjs/send#readme> |
| `serve-static` | 2.2.1 | MIT | <https://github.com/expressjs/serve-static#readme> |
| `set-cookie-parser` | 3.1.0 | MIT | <https://github.com/nfriedly/set-cookie-parser> |
| `shadcn` | 4.6.0 | MIT | <https://github.com/shadcn-ui/ui#readme> |
| `shebang-command` | 2.0.0 | MIT | <https://github.com/kevva/shebang-command#readme> |
| `shebang-regex` | 3.0.0 | MIT | <https://github.com/sindresorhus/shebang-regex#readme> |
| `side-channel` | 1.1.0 | MIT | <https://github.com/ljharb/side-channel#readme> |
| `side-channel-list` | 1.0.1 | MIT | <https://github.com/ljharb/side-channel-list#readme> |
| `side-channel-map` | 1.0.1 | MIT | <https://github.com/ljharb/side-channel-map#readme> |
| `side-channel-weakmap` | 1.0.2 | MIT | <https://github.com/ljharb/side-channel-weakmap#readme> |
| `sisteransi` | 1.0.5 | MIT | <https://github.com/terkelg/sisteransi#readme> |
| `sonner` | 2.0.7 | MIT | <https://sonner.emilkowal.ski/> |
| `statuses` | 2.0.2 | MIT | <https://github.com/jshttp/statuses#readme> |
| `stdin-discarder` | 0.2.2 | MIT | <https://github.com/sindresorhus/stdin-discarder#readme> |
| `strict-event-emitter` | 0.5.1 | MIT | <https://github.com/open-draft/strict-event-emitter#readme> |
| `string-width` | 4.2.3 | MIT | <https://github.com/sindresorhus/string-width#readme> |
| `strip-ansi` | 6.0.1 | MIT | <https://github.com/chalk/strip-ansi#readme> |
| `strip-bom` | 3.0.0 | MIT | <https://github.com/sindresorhus/strip-bom#readme> |
| `strip-final-newline` | 2.0.0 | MIT | <https://github.com/sindresorhus/strip-final-newline#readme> |
| `styled-jsx` | 5.1.6 | MIT | <https://github.com/vercel/styled-jsx#readme> |
| `supports-color` | 7.2.0 | MIT | <https://github.com/chalk/supports-color#readme> |
| `table-layout` | 4.1.1 | MIT | <https://github.com/75lb/table-layout#readme> |
| `tagged-tag` | 1.0.0 | MIT | <https://github.com/sindresorhus/tagged-tag#readme> |
| `tailwind-merge` | 3.5.0 | MIT | <https://github.com/dcastil/tailwind-merge> |
| `tiny-invariant` | 1.3.3 | MIT | <https://github.com/alexreardon/tiny-invariant#readme> |
| `tldts` | 7.0.29 | MIT | <https://github.com/remusao/tldts#readme> |
| `tldts-core` | 7.0.29 | MIT | <https://github.com/remusao/tldts#readme> |
| `to-regex-range` | 5.0.1 | MIT | <https://github.com/micromatch/to-regex-range> |
| `toidentifier` | 1.0.1 | MIT | <https://github.com/component/toidentifier#readme> |
| `ts-morph` | 26.0.0 | MIT | <https://github.com/dsherret/ts-morph#readme> |
| `tsconfig-paths` | 4.2.0 | MIT | <https://github.com/dividab/tsconfig-paths#readme> |
| `tw-animate-css` | 1.4.0 | MIT | <https://github.com/Wombosvideo/tw-animate-css#readme> |
| `type-fest` | 5.6.0 | (MIT OR CC0-1.0) | <https://github.com/sindresorhus/type-fest#readme> |
| `type-is` | 2.0.1 | MIT | <https://github.com/jshttp/type-is#readme> |
| `typical` | 4.0.0 | MIT | <https://github.com/75lb/typical#readme> |
| `undici-types` | 6.21.0 | MIT | <https://undici.nodejs.org> |
| `unicorn-magic` | 0.3.0 | MIT | <https://github.com/sindresorhus/unicorn-magic#readme> |
| `universalify` | 2.0.1 | MIT | <https://github.com/RyanZim/universalify#readme> |
| `unpipe` | 1.0.0 | MIT | <https://github.com/stream-utils/unpipe#readme> |
| `until-async` | 3.0.2 | MIT | <https://github.com/kettanaito/until-async> |
| `update-browserslist-db` | 1.2.3 | MIT | <https://github.com/browserslist/update-db#readme> |
| `use-callback-ref` | 1.3.3 | MIT | <https://github.com/theKashey/use-callback-ref#readme> |
| `use-sidecar` | 1.1.3 | MIT | <https://github.com/theKashey/use-sidecar> |
| `use-sync-external-store` | 1.6.0 | MIT | <https://github.com/facebook/react#readme> |
| `util-deprecate` | 1.0.2 | MIT | <https://github.com/TooTallNate/util-deprecate> |
| `vary` | 1.1.2 | MIT | <https://github.com/jshttp/vary#readme> |
| `web-streams-polyfill` | 3.3.3 | MIT | <https://github.com/MattiasBuelens/web-streams-polyfill#readme> |
| `wordwrapjs` | 5.1.1 | MIT | <https://github.com/75lb/wordwrapjs#readme> |
| `wrap-ansi` | 7.0.0 | MIT | <https://github.com/chalk/wrap-ansi#readme> |
| `wsl-utils` | 0.3.1 | MIT | <https://github.com/sindresorhus/wsl-utils#readme> |
| `yargs` | 17.7.2 | MIT | <https://yargs.js.org/> |
| `yocto-spinner` | 1.1.0 | MIT | <https://github.com/sindresorhus/yocto-spinner#readme> |
| `yoctocolors` | 2.1.2 | MIT | <https://github.com/sindresorhus/yoctocolors#readme> |
| `zod` | 3.25.76 | MIT | <https://zod.dev> |
| `zustand` | 4.5.7 | MIT | <https://github.com/pmndrs/zustand> |


#### Full license text — MIT

```
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
THE SOFTWARE.
```

---

## BSD

### BSD (Python, 27 packages)

| Package | Version | License | Source / project URL |
|---|---|---|---|
| `httpx` | 0.28.1 | BSD-3-Clause | <https://github.com/encode/httpx/blob/master/CHANGELOG.md> |
| `scikit-learn` | 1.8.0 | BSD-3-Clause | <https://scikit-learn.org> |
| `scipy` | 1.17.1 | BSD License | <https://scipy.org/> |
| `seaborn` | 0.13.2 | BSD License | <http://seaborn.pydata.org> |
| `statsmodels` | 0.14.6 | BSD License | <https://www.statsmodels.org/> |
| `umap-learn` | 0.5.12 | BSD | <http://github.com/lmcinnes/umap> |
| `uvicorn` | 0.46.0 | BSD-3-Clause | <https://uvicorn.dev/release-notes> |
| `click` | 8.3.3 | BSD-3-Clause | <https://click.palletsprojects.com/page/changes/> |
| `contourpy` | 1.3.3 | BSD License | <https://github.com/contourpy/contourpy> |
| `cycler` | 0.12.1 | BSD License | <https://matplotlib.org/cycler/> |
| `httpcore` | 1.0.9 | BSD-3-Clause | <https://www.encode.io/httpcore> |
| `idna` | 3.13 | BSD-3-Clause | <https://github.com/kjd/idna/blob/master/HISTORY.rst> |
| `joblib` | 1.5.3 | BSD-3-Clause | <https://joblib.readthedocs.io> |
| `kiwisolver` | 1.5.0 | BSD License | <https://github.com/nucleic/kiwi> |
| `MarkupSafe` | 3.0.3 | BSD-3-Clause | <https://palletsprojects.com/donate> |
| `numba` | 0.65.1 | BSD | <https://numba.pydata.org> |
| `numpy` | 2.4.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | <https://numpy.org> |
| `pandas` | 3.0.2 | BSD License | <https://pandas.pydata.org> |
| `patsy` | 1.0.2 | 2-clause BSD | <https://github.com/pydata/patsy> |
| `Pygments` | 2.20.0 | BSD-2-Clause | <https://pygments.org> |
| `pynndescent` | 0.6.0 | BSD-2-Clause | <http://github.com/lmcinnes/pynndescent> |
| `python-dateutil` | 2.9.0.post0 | Dual License | <https://github.com/dateutil/dateutil> |
| `python-dotenv` | 1.2.2 | BSD-3-Clause | <https://github.com/theskumar/python-dotenv> |
| `starlette` | 1.0.0 | BSD-3-Clause | <https://github.com/Kludex/starlette> |
| `threadpoolctl` | 3.6.0 | BSD-3-Clause | <https://github.com/joblib/threadpoolctl> |
| `websockets` | 16.0 | BSD-3-Clause | <https://github.com/python-websockets/websockets> |
| `xlsxwriter` | 3.2.9 | BSD-2-Clause | <https://github.com/jmcnamara/XlsxWriter> |

### BSD (npm, 14 packages)

| Package | Version | License | Source / project URL |
|---|---|---|---|
| `@dotenvx/dotenvx` | 1.64.0 | BSD-3-Clause | <https://github.com/dotenvx/dotenvx> |
| `d3-ease` | 3.0.1 | BSD-3-Clause | <https://d3js.org/d3-ease/> |
| `diff` | 8.0.4 | BSD-3-Clause | <https://github.com/kpdecker/jsdiff#readme> |
| `dotenv` | 17.4.2 | BSD-2-Clause | <https://github.com/motdotla/dotenv#readme> |
| `esprima` | 4.0.1 | BSD-2-Clause | <http://esprima.org> |
| `fast-uri` | 3.1.0 | BSD-3-Clause | <https://github.com/fastify/fast-uri> |
| `json-schema-typed` | 8.0.2 | BSD-2-Clause | <https://github.com/RemyRylan/json-schema-typed/tree/main/dist/node> |
| `qs` | 6.15.1 | BSD-3-Clause | <https://github.com/ljharb/qs> |
| `rw` | 1.3.3 | BSD-3-Clause | <https://github.com/mbostock/rw> |
| `source-map` | 0.6.1 | BSD-3-Clause | <https://github.com/mozilla/source-map> |
| `source-map-js` | 1.2.1 | BSD-3-Clause | <https://github.com/7rulnik/source-map-js> |
| `stringify-object` | 5.0.0 | BSD-2-Clause | <https://github.com/yeoman/stringify-object#readme> |
| `tough-cookie` | 6.0.1 | BSD-3-Clause | <https://github.com/salesforce/tough-cookie> |
| `tslib` | 2.8.1 | 0BSD | <https://www.typescriptlang.org/> |


#### Full license text — BSD

```
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
POSSIBILITY OF SUCH DAMAGE.
```

---

## Apache-2.0

### Apache-2.0 (Python, 5 packages)

| Package | Version | License | Source / project URL |
|---|---|---|---|
| `pyarrow` | 24.0.0 | Apache-2.0 | <https://arrow.apache.org/> |
| `pytest-asyncio` | 1.3.0 | Apache-2.0 | <https://github.com/pytest-dev/pytest-asyncio/issues> |
| `python-multipart` | 0.0.27 | Apache-2.0 | <https://github.com/Kludex/python-multipart> |
| `llvmlite` | 0.47.0 | BSD-2-Clause AND Apache-2.0 WITH LLVM-exception | <http://llvmlite.readthedocs.io> |
| `packaging` | 26.2 | Apache-2.0 OR BSD-2-Clause | <https://packaging.pypa.io/> |

### Apache-2.0 (npm, 10 packages)

| Package | Version | License | Source / project URL |
|---|---|---|---|
| `@img/sharp-darwin-arm64` | 0.34.5 | Apache-2.0 | <https://sharp.pixelplumbing.com> |
| `@swc/helpers` | 0.5.15 | Apache-2.0 | <https://swc.rs> |
| `apache-arrow` | 17.0.0 | Apache-2.0 | <https://arrow.apache.org/js/> |
| `baseline-browser-mapping` | 2.10.24 | Apache-2.0 | <https://github.com/web-platform-dx/baseline-browser-mapping#readme> |
| `class-variance-authority` | 0.7.1 | Apache-2.0 | <https://github.com/joe-bell/cva#readme> |
| `detect-libc` | 2.1.2 | Apache-2.0 | <https://github.com/lovell/detect-libc#readme> |
| `flatbuffers` | 24.12.23 | Apache-2.0 | <https://google.github.io/flatbuffers/> |
| `human-signals` | 2.1.0 | Apache-2.0 | <https://www.github.com/ehmicky/human-signals> |
| `sharp` | 0.34.5 | Apache-2.0 | <https://sharp.pixelplumbing.com> |
| `typescript` | 5.9.3 | Apache-2.0 | <https://www.typescriptlang.org/> |


#### Full license text — Apache-2.0

```
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
      patent grant covering the unmodified upstream code.
```

---

## ISC

### ISC (npm, 58 packages)

| Package | Version | License | Source / project URL |
|---|---|---|---|
| `@observablehq/plot` | 0.6.17 | ISC | <https://github.com/observablehq/plot#readme> |
| `cli-width` | 4.1.0 | ISC | <https://github.com/knownasilya/cli-width> |
| `cliui` | 8.0.1 | ISC | <https://github.com/yargs/cliui#readme> |
| `d3` | 7.9.0 | ISC | <https://d3js.org> |
| `d3-array` | 3.2.4 | ISC | <https://d3js.org/d3-array/> |
| `d3-axis` | 3.0.0 | ISC | <https://d3js.org/d3-axis/> |
| `d3-brush` | 3.0.0 | ISC | <https://d3js.org/d3-brush/> |
| `d3-chord` | 3.0.1 | ISC | <https://d3js.org/d3-chord/> |
| `d3-color` | 3.1.0 | ISC | <https://d3js.org/d3-color/> |
| `d3-contour` | 4.0.2 | ISC | <https://d3js.org/d3-contour/> |
| `d3-delaunay` | 6.0.4 | ISC | <https://github.com/d3/d3-delaunay> |
| `d3-dispatch` | 3.0.1 | ISC | <https://d3js.org/d3-dispatch/> |
| `d3-drag` | 3.0.0 | ISC | <https://d3js.org/d3-drag/> |
| `d3-dsv` | 3.0.1 | ISC | <https://d3js.org/d3-dsv/> |
| `d3-fetch` | 3.0.1 | ISC | <https://d3js.org/d3-fetch/> |
| `d3-force` | 3.0.0 | ISC | <https://d3js.org/d3-force/> |
| `d3-format` | 3.1.2 | ISC | <https://d3js.org/d3-format/> |
| `d3-geo` | 3.1.1 | ISC | <https://d3js.org/d3-geo/> |
| `d3-hierarchy` | 3.1.2 | ISC | <https://d3js.org/d3-hierarchy/> |
| `d3-interpolate` | 3.0.1 | ISC | <https://d3js.org/d3-interpolate/> |
| `d3-path` | 3.1.0 | ISC | <https://d3js.org/d3-path/> |
| `d3-polygon` | 3.0.1 | ISC | <https://d3js.org/d3-polygon/> |
| `d3-quadtree` | 3.0.1 | ISC | <https://d3js.org/d3-quadtree/> |
| `d3-random` | 3.0.1 | ISC | <https://d3js.org/d3-random/> |
| `d3-scale` | 4.0.2 | ISC | <https://d3js.org/d3-scale/> |
| `d3-scale-chromatic` | 3.1.0 | ISC | <https://d3js.org/d3-scale-chromatic/> |
| `d3-selection` | 3.0.0 | ISC | <https://d3js.org/d3-selection/> |
| `d3-shape` | 3.2.0 | ISC | <https://d3js.org/d3-shape/> |
| `d3-time` | 3.1.0 | ISC | <https://d3js.org/d3-time/> |
| `d3-time-format` | 4.1.0 | ISC | <https://d3js.org/d3-time-format/> |
| `d3-timer` | 3.0.1 | ISC | <https://d3js.org/d3-timer/> |
| `d3-transition` | 3.0.1 | ISC | <https://d3js.org/d3-transition/> |
| `d3-zoom` | 3.0.0 | ISC | <https://d3js.org/d3-zoom/> |
| `delaunator` | 5.1.0 | ISC | <https://github.com/mapbox/delaunator#readme> |
| `electron-to-chromium` | 1.5.348 | ISC | <https://github.com/Kilian/electron-to-chromium#readme> |
| `fastq` | 1.20.1 | ISC | <https://github.com/mcollina/fastq#readme> |
| `get-caller-file` | 2.0.5 | ISC | <https://github.com/stefanpenner/get-caller-file#readme> |
| `glob-parent` | 5.1.2 | ISC | <https://github.com/gulpjs/glob-parent#readme> |
| `graceful-fs` | 4.2.11 | ISC | <https://github.com/isaacs/node-graceful-fs#readme> |
| `inherits` | 2.0.4 | ISC | <https://github.com/isaacs/inherits#readme> |
| `internmap` | 2.0.3 | ISC | <https://github.com/mbostock/internmap/> |
| `isexe` | 2.0.0 | ISC | <https://github.com/isaacs/isexe#readme> |
| `isoformat` | 0.2.1 | ISC | <https://github.com/mbostock/isoformat/> |
| `lru-cache` | 5.1.1 | ISC | <https://github.com/isaacs/node-lru-cache#readme> |
| `lucide-react` | 1.14.0 | ISC | <https://lucide.dev> |
| `mute-stream` | 3.0.0 | ISC | <https://github.com/npm/mute-stream#readme> |
| `once` | 1.4.0 | ISC | <https://github.com/isaacs/once#readme> |
| `picocolors` | 1.1.1 | ISC | <https://github.com/alexeyraspopov/picocolors#readme> |
| `semver` | 6.3.1 | ISC | <https://github.com/npm/node-semver#readme> |
| `setprototypeof` | 1.2.0 | ISC | <https://github.com/wesleytodd/setprototypeof> |
| `signal-exit` | 3.0.7 | ISC | <https://github.com/tapjs/signal-exit#readme> |
| `validate-npm-package-name` | 7.0.2 | ISC | <https://github.com/npm/validate-npm-package-name> |
| `which` | 2.0.2 | ISC | <https://github.com/npm/node-which#readme> |
| `wrappy` | 1.0.2 | ISC | <https://github.com/npm/wrappy> |
| `y18n` | 5.0.8 | ISC | <https://github.com/yargs/y18n> |
| `yallist` | 3.1.1 | ISC | <https://github.com/isaacs/yallist#readme> |
| `yargs-parser` | 21.1.1 | ISC | <https://github.com/yargs/yargs-parser#readme> |
| `zod-to-json-schema` | 3.25.2 | ISC | <https://github.com/StefanTerdell/zod-to-json-schema#readme> |


#### Full license text — ISC

```
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
IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
```

---

## PSF

### PSF (Python, 2 packages)

| Package | Version | License | Source / project URL |
|---|---|---|---|
| `matplotlib` | 3.10.9 | Python Software Foundation License | <https://matplotlib.org> |
| `typing_extensions` | 4.15.0 | PSF-2.0 | <https://github.com/python/typing_extensions/issues> |

### PSF (npm, 1 package)

| Package | Version | License | Source / project URL |
|---|---|---|---|
| `argparse` | 2.0.1 | Python-2.0 | <https://github.com/nodeca/argparse#readme> |


#### Full license text — PSF

```
PYTHON SOFTWARE FOUNDATION LICENSE VERSION 2 (PSF-2.0)

The full text is at https://docs.python.org/3/license.html#psf-license-agreement-for-python-release

Permissive: allows redistribution, modification, derivative works, and
commercial use, subject to including the PSF copyright notice + a
disclaimer of warranty. Functionally similar to BSD/MIT for our purposes.
```

---

## BlueOak

### BlueOak (npm, 2 packages)

| Package | Version | License | Source / project URL |
|---|---|---|---|
| `isexe` | 3.1.5 | BlueOak-1.0.0 | <https://github.com/isaacs/isexe#readme> |
| `minimatch` | 10.2.5 | BlueOak-1.0.0 | <https://github.com/isaacs/minimatch#readme> |


#### Full license text — BlueOak

```
Blue Oak Model License 1.0.0

The full text is at https://blueoakcouncil.org/license/1.0.0

A modern permissive license. Allows unrestricted use, copying, modification,
and distribution, with explicit patent grant. Equivalent in effect to MIT
for redistribution purposes.
```

---

## Unlicense

### Unlicense (npm, 1 package)

| Package | Version | License | Source / project URL |
|---|---|---|---|
| `robust-predicates` | 3.0.3 | Unlicense | <https://github.com/mourner/robust-predicates#readme> |


#### Full license text — Unlicense

```
The Unlicense

The full text is at https://unlicense.org/

This is free and unencumbered software released into the public domain.
Anyone is free to copy, modify, publish, use, compile, sell, or distribute
this software, either in source code form or as a compiled binary, for
any purpose, commercial or non-commercial, and by any means.

In jurisdictions that recognize copyright laws, the author or authors of
this software dedicate any and all copyright interest in the software to
the public domain.
```

---

## CC-BY

### CC-BY (npm, 1 package)

| Package | Version | License | Source / project URL |
|---|---|---|---|
| `caniuse-lite` | 1.0.30001791 | CC-BY-4.0 | <https://github.com/browserslist/caniuse-lite#readme> |


#### Full license text — CC-BY

```
Creative Commons Attribution

The full text varies by version (typically CC-BY-3.0 or CC-BY-4.0):
  https://creativecommons.org/licenses/by/4.0/legalcode

Permissive in effect: allows redistribution, modification, derivative
works, and commercial use, provided you give appropriate credit (the
attributions in the per-package table above), provide a link to the
license, and indicate if changes were made.

CC-BY is typically applied to data/spec packages (e.g., country lists,
mime-types) rather than executable code.
```

---

## MPL-2.0

### MPL-2.0 (Python, 3 packages)

| Package | Version | License | Source / project URL |
|---|---|---|---|
| `certifi` | 2026.4.22 | MPL-2.0 | <https://github.com/certifi/python-certifi> |
| `pathspec` | 1.1.1 | Mozilla Public License 2.0 (MPL 2.0) | <https://python-path-specification.readthedocs.io/en/latest/changes.html> |
| `tqdm` | 4.67.3 | MPL-2.0 AND MIT | <https://tqdm.github.io> |


#### Full license text — MPL-2.0

```
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
canonical source repository linked in each package's project URL.
```

---

## LGPL

### LGPL (npm, 1 package)

| Package | Version | License | Source / project URL |
|---|---|---|---|
| `@img/sharp-libvips-darwin-arm64` | 1.2.4 | LGPL-3.0-or-later | <https://sharp.pixelplumbing.com> |


#### Full license text — LGPL

```
GNU LESSER GENERAL PUBLIC LICENSE Version 3.0 (LGPL-3.0-or-later)

The full text is at https://www.gnu.org/licenses/lgpl-3.0.txt

Key obligation for redistribution:
  - Recipients must be able to relink/replace the LGPL'd library with a
    different version. Achievable via dynamic linking (the default for
    native binaries) or by shipping object files alongside the
    application.

DIG attests in the LGPL section below that the single LGPL transitive
dependency in the npm tree is *never invoked* by DIG and is not part of
the runtime call graph. See that section for details.
```

---

## Other / Unclear

### Other / Unclear (npm, 1 package)

| Package | Version | License | Source / project URL |
|---|---|---|---|
| `geist` | 1.7.0 | SIL OPEN FONT LICENSE | <https://vercel.com/font> |


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
