# Contributing to DataInsightGrove

Thanks for your interest! Quick read of how the project is set up to receive
contributions today.

## TL;DR

| You want to… | How |
|---|---|
| 🐛 Report a bug | [Open an issue](https://github.com/SFCyris/DataInsightGrove/issues) — please include OS, DIG version, and steps to reproduce. |
| 💡 Request a feature | [Open an issue](https://github.com/SFCyris/DataInsightGrove/issues) or start a [discussion](https://github.com/SFCyris/DataInsightGrove/discussions) — say what problem you're trying to solve, not just the solution you have in mind. |
| 💬 Ask a question / share a use case | [Discussions](https://github.com/SFCyris/DataInsightGrove/discussions) is the best venue. |
| 🔌 Build your own step or connector | Drop it in your local `plugins/` folder — see [`docs/PLUGIN_AUTHORING.md`](docs/PLUGIN_AUTHORING.md) and [`docs/AUTHORING_GUIDE.md`](docs/AUTHORING_GUIDE.md). No PR needed; the plugin loader picks it up automatically. |
| 🍴 Fork and modify for your own use | Welcome under [AGPL-3.0-or-later](LICENSE). Please rename your fork — see [`TRADEMARK.md`](TRADEMARK.md). |

## Code contributions

> 🚧 **DataInsightGrove is not currently accepting external code
> contributions** (pull requests). This may change in the future, but for
> now please don't open a PR — it'll be politely closed.

Why: DIG is in beta (v0.5.0), the architecture is still settling, and the
maintainer wants the code to converge with a single voice before opening
the contribution surface. When that changes, this document will be updated
and a `CODEOWNERS` + PR-template + contributor-license-agreement workflow
will be added.

In the meantime, **issues and discussions are the most valuable thing you
can offer.** A good issue often shapes the design more than a PR would,
because it surfaces the real-world problem before any code is committed.

## What makes a great issue

- **Title**: short and specific (e.g. *"`reorder_columns` step duplicates
  the column when target is the same as source"* — not *"reorder bug"*).
- **Body**: what you tried, what you expected, what happened, your OS +
  DIG version + browser if it's a UI issue.
- **Repro**: minimum dataset (a 5-row CSV is fine) + the pipeline JSON
  that triggers the bug. The Export menu in the editor (📤 →
  *Pipeline (.dig.json)*) gives you the exact JSON to paste.
- **One issue per report.** Multiple unrelated bugs in one thread make
  triage hard.

## Security

If you find something that looks like a security vulnerability — auth
bypass, RCE in a step, secret exfiltration — please **don't** open a
public issue. Email the maintainer directly, or use GitHub's
*Report a vulnerability* button under the **Security** tab. The basics:

- DIG's threat model assumes loopback or LAN with the bearer-token gate
  on. If you can compromise a default loopback install, that's a finding.
- Anything involving file or network IO triggered by user-authored
  expressions / SQL is in scope (we have an `assert_safe_expr` denylist
  exactly for this — bypasses welcome).

## Local development

Even though external PRs aren't accepted yet, you can run the project
locally as a contributor would:

```bash
./install.sh          # set up backend/.venv + frontend/node_modules
./start.sh            # bring up API + web
```

See [`docs/getting_started.md`](docs/getting_started.md) for a deeper
walkthrough.

## Forks

The AGPL-3.0 source license freely permits forks. Two requests:

1. **Rename the fork** to a name that doesn't incorporate the
   *DataInsightGrove* or *DIG* word marks — see [`TRADEMARK.md`](TRADEMARK.md)
   for what's claimed and what's not.
2. **Keep AGPL §13 in mind**: if you run a modified version over a
   network (a hosted service), you must make your modified source
   available to that service's users.

Otherwise: have at it. Different vision for a feature? Build it in your
fork — the AGPL is designed to make this work cleanly.

---

This document will be updated when the contribution policy changes.
Last updated: 2026-05-02 (v0.5.0).
