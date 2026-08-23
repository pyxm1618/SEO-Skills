# Root Library Coverage Snapshot — 2026-08-22

This snapshot audits the bootstrap root library after three evidence-feedback passes: the existing 1,046-keyword Semrush US batch, the Wedding cross-domain experiment, and the Baking/Fermentation cross-domain experiment. It is **not a complete universe of SEO demand roots** and it is not an SEO opportunity report.

## Current state

The initial audited bootstrap contained **307** unique roots. The Semrush feedback pass added/promoted `travel budget`, `bitcoin mining`, and `itinerary planner`. Wedding then promoted six existing roots and added seven new roots. Baking/Fermentation promoted seven existing roots and added eight new roots.

Current library:

- Total roots: **323**
- Universal roots: **197**
- Domain roots: **126**
- Verified: **69**
- Active: **56**
- Candidate: **198**
- Usable (`active` + `verified`): **125**
- Candidate share: **61.3%**
- Tool-intent share: **37.5%**

Interpretation: breadth remains suitable for a bootstrap library and evidence maturity is improving without drifting back toward a tool-only library. Most roots are still candidates or published-list assets and should not be treated as validated opportunities.

## Where evidence is strongest

Evidence is strongest in domains actually researched with real keyword or SERP/site evidence:

| Domain | Total roots | Usable | Verified |
|---|---:|---:|---:|
| wedding | 18 | 13 | 13 |
| baking | 14 | 13 | 13 |
| fermentation | 8 | 8 | 8 |
| travel | 30 | 7 | 7 |
| bitcoin | 12 | 7 | 7 |
| relationships | 12 | 6 | 6 |
| pet | 9 | 6 | 6 |
| gaming | 11 | 4 | 4 |
| dreams | 7 | 4 | 4 |

This concentration follows research coverage. It must not be interpreted as a ranking of market attractiveness.

## Wedding cross-domain experiment

The Wedding pass reviewed real SERPs and first-party site structures from The Knot, WeddingWire, Zola, and Greenvelope.

Existing roots promoted to `verified/L2`:

- `wedding budget`
- `wedding checklist`
- `wedding timeline`
- `guest list`
- `seating chart`
- `wedding vows`

New `verified/L2` roots added:

- `wedding website`
- `wedding registry`
- `wedding venue`
- `wedding vendor`
- `wedding rsvp`
- `wedding invitation wording`
- `wedding dress code`

Evidence details: `references/wedding-demand-evidence-2026-08-22.md`.

## Baking / Fermentation cross-domain experiment

This pass intentionally used a domain structurally different from Wedding. Evidence came from King Arthur Baking, The Perfect Loaf, Breadtopia, Cultures For Health, Serious Eats, and repeated independent calculator SERPs.

Existing roots promoted from `candidate/L0` to `verified/L2`:

- `baker's percentage`
- `hydration calculator`
- `recipe scaler`
- `pan conversion`
- `proofing time`
- `substitute`
- `recipe`

New `verified/L2` roots added because the demand family repeated across independent sources:

- `sourdough starter`
- `starter feeding ratio`
- `bulk fermentation`
- `bulk fermentation calculator`
- `fermentation time calculator`
- `fermentation brine calculator`
- `fermentation troubleshooting`
- `sourdough schedule`

This pass strengthened both tool and non-tool structures: `calculate`, `convert`, `time`, `check`, `learn`, `replace`, and `plan`. Evidence details: `references/baking-fermentation-demand-evidence-2026-08-22.md`.

The pass deliberately did **not** add every observed baking concept. Items such as dough temperature, cold retard, crumb analysis, starter discard, scoring pattern, and individual fermentation defects remain unpromoted until they demonstrate a sufficiently reusable demand family.

## Thin demand families after three passes

Coverage audit still shows important evidence gaps. Categories with no verified roots include:

- `price`
- `lookup`
- `decide`
- `estimate`
- `measure`
- `navigate`
- `predict`
- `visualize`

Other areas have some usable roots but remain thin, including `content`, `track`, `find`, `identify`, `resource`, and `create`.

These are research priorities, not targets to fill mechanically. A category should gain roots only when a real domain exposes a repeated user-demand family.

## Research-loop feedback from the 1,046-keyword batch

Accepted evidence-backed changes from the first pass:

- `travel budget`: observed in 18 unique keywords; promoted to `verified/L2`.
- `bitcoin mining`: observed in 20 unique keywords; promoted to `verified/L2`.
- `itinerary planner`: observed in 26 unique keywords; added as `verified/L2`.

Other mined phrases were not automatically added. Candidate mining remains review-only because many repeated strings are entity fragments, grammatical fragments, or combinations already represented by existing roots.

## Coverage policy

Do **not** optimize for a raw root-count target such as 500 or 1,000. Optimize for distinct demand coverage and evidence:

1. Query existing roots for the target domain.
2. Run `scripts/audit_coverage.py` to locate candidate-only or missing demand families.
3. Do targeted real-world discovery for those gaps.
4. After real keyword/site/SERP research, run `scripts/mine_root_candidates.py` when a structured keyword batch exists.
5. Review recurring patterns; never auto-add or auto-promote them.
6. Record durable evidence and promote according to `root-taxonomy.md`.
7. Re-run validation and tests.

A larger library is useful only when additional roots represent distinct reusable user demand rather than synonyms, entities, or arbitrary phrases.
