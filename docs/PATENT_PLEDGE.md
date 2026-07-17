# DataInsightGrove Patent Non-Aggression Pledge

This pledge supplements (does **not** replace) the AGPL-3.0 license
under which DataInsightGrove ("DIG") is distributed. It addresses the
patent dimension explicitly — AGPL-3.0 contains only a narrow patent
clause, and good-faith downstream users deserve a stronger commitment.

This pledge is modeled on the established frameworks below and adopts
language compatible with the spirit of all of them:

- The [Apache 2.0 patent grant clause](https://www.apache.org/licenses/LICENSE-2.0#patent) (§ 3)
- [Twitter's Innovator's Patent Agreement (IPA)](https://github.com/twitter/innovators-patent-agreement)
- The [Open Patent Non-Assertion Pledge (OPN)](https://opennetworking.org/about/policies/) tradition
- [Microsoft's Open Specification Promise (OSP)](https://learn.microsoft.com/en-us/openspecs/dev_center/ms-devcentlp/1c24c7c8-28b0-4ce1-a47d-95fe1ff504bc)
- [Tesla's Patent Pledge](https://www.tesla.com/blog/all-our-patent-are-belong-you)
- The Open Invention Network's [Linux System Definition](https://openinventionnetwork.com/)

---

## 1. Definitions

In this pledge:

- **"DIG"** means the DataInsightGrove software project, including all
  source code, manifests, plugins, documentation, and assets in the
  upstream repository at <https://github.com/SFCyris/DataInsightGrove>
  as of any release tag.
- **"Maintainer"** means Sebastian Cyris, the original author and
  current copyright holder of DIG, and any successor in interest who
  acquires the project repository or its trademarks.
- **"DIG Patents"** means any patent claims, in any jurisdiction, that
  are now or hereafter owned or controlled by the Maintainer and that
  are necessarily infringed by an unmodified release of DIG existing
  on or before the date of this pledge.
- **"User"** means any natural person, organisation, or legal entity
  that uses, copies, modifies, or distributes DIG in compliance with
  the AGPL-3.0 license.

## 2. Affirmative Patent Grant

The Maintainer hereby grants every User a **perpetual, worldwide,
non-exclusive, no-charge, royalty-free, irrevocable license** under
all DIG Patents to make, have made, use, offer to sell, sell, import,
and otherwise transfer DIG (and modifications thereof permitted by
AGPL-3.0).

This grant is parallel to and consistent with the Apache 2.0 patent
clause (§ 3): if any DIG Patent claim is necessarily infringed by an
unmodified release of DIG, this license covers that claim.

## 3. Non-Assertion Pledge

The Maintainer pledges not to initiate, fund, or knowingly assist any
patent infringement litigation or threat thereof against any User on
the basis of any DIG Patent for the User's use, modification,
distribution, or sale of DIG, except as permitted by Section 4.

This pledge is **irrevocable** and survives any change of ownership of
the DIG project, repository, or trademarks. Any successor in interest
to the Maintainer is bound by it.

## 4. Reserved Defensive Use

This pledge does **not** grant patent rights, and the Maintainer
expressly reserves the right to assert any patent (DIG-related or
otherwise), against any party that:

a) **Initiates first.** Files a patent infringement claim, or any
   action or threat thereof, against the Maintainer, against the DIG
   project, or against any User specifically *because* of their use
   of DIG; or

b) **Bad-faith assertion.** Asserts a patent against the open-source
   community in a manner widely regarded as patent abuse (e.g.
   non-practicing entity assertion of a software patent against a
   commodity OSS project).

Defensive assertions under this section are limited to the minimum
necessary to terminate the asserted action and reach a stable
non-aggression posture.

## 5. Scope of Pledge

This pledge applies to:

- DIG as released under AGPL-3.0 from the upstream repository.
- All historical releases up to and including the date of this pledge.
- Subsequent releases unless and until the pledge is explicitly
  modified in writing in this file (and any modification applies only
  to releases made *after* the modification date — prior releases
  retain their original pledge).

This pledge does **not** apply to:

- Software, services, or features developed independently of DIG that
  do not appear in the DIG codebase.
- Patents owned by third parties (including patents acquired by the
  Maintainer from a third party that were not subject to a comparable
  pledge at the time of acquisition).
- Offerings developed *outside* the AGPL-3.0 codebase. Such offerings
  carry their own licensing and patent terms, separate from this
  pledge.

## 6. Cumulative with AGPL-3.0

This pledge is **in addition to** the patent provisions of AGPL-3.0,
not a substitute for them. Where this pledge grants more than AGPL-3.0,
the more permissive terms apply. Where AGPL-3.0 grants something not
addressed here, the AGPL terms govern.

## 7. No Trademark License

This pledge does **not** grant any rights to use the names, logos, or
trademarks of the Maintainer or the DIG project. Trademark use is
governed separately — see `TRADEMARK.md`.

## 8. Standard Disclaimers

This pledge is provided "AS IS" without warranty of any kind, and is
not legal advice. Users seeking certainty about patent risk in their
specific deployment should consult their own patent attorney.

## 9. Acceptance & Effective Date

This pledge becomes effective on the commit date that adds this file
to the upstream repository, and applies to all releases of DIG made on
or after that date. Prior releases benefit from this pledge
retroactively to the extent the Maintainer has authority to bind them.

## 10. Contact

For inquiries about this pledge, including notices required under
Section 4, contact the Maintainer via GitHub at
<https://github.com/SFCyris/DataInsightGrove>.

---

## Appendix A — Recommended README Note

Add the following line to the project README near the licensing note:

> DIG is released under [AGPL-3.0](LICENSE) and additionally covered
> by a [Patent Non-Aggression Pledge](docs/PATENT_PLEDGE.md).

## Appendix B — How This Pledge Compares

| Framework | What it grants | What it reserves | Why we picked elements from it |
|---|---|---|---|
| Apache 2.0 § 3 | explicit patent license to contributors + users | termination if user sues | clearest "license you to my own patents" language |
| Twitter IPA | inventor retains patent; company gets defensive license only | offensive use is opt-in by inventor | clean separation of offensive vs defensive |
| Tesla Pledge | "we will not sue" | bad-faith actors not protected | simplicity + good-faith carve-out |
| OIN Linux System | non-aggression among members | non-members can be sued | scope limited to a defined system |
| Mozilla MPL § 2.4 | termination on patent assertion | reciprocal protection | clarity on what triggers loss of grant |

DIG's pledge takes:

- **Explicit patent grant** (§ 2) from Apache 2.0
- **Non-assertion pledge** (§ 3) from Tesla / OIN
- **Defensive carve-out** (§ 4) from Twitter IPA + Mozilla MPL
- **Scope clarity** (§ 5) so offerings developed outside the AGPL-3.0
  codebase can carry their own terms without affecting the open-source
  promise

## Appendix C — What This Pledge Does Not Cover

- **Implementation patents** held by third parties (for example,
  patents on automated transformation-suggestion algorithms in the
  data-preparation space). Avoidance of such patents is a separate
  engineering concern.
- **Standards-essential patents** required to interoperate with closed
  protocols (e.g. proprietary data warehouse APIs).
- **Trademark protection** for the names "DataInsightGrove" and "DIG".
  Those are addressed separately in `TRADEMARK.md`.

---

*Document last updated when committed. Use `git log -- docs/PATENT_PLEDGE.md`
for the precise effective date and any subsequent modifications.*
