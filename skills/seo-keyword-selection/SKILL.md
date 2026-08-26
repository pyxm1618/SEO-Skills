---
name: seo-keyword-selection
description: Use when concrete keyword candidates must be screened from the former Step 5 onward with real metrics, KGR, SERP evidence, trend validation, opportunity clustering, and human decision support.
---

# SEO Keyword Selection

Run the existing SEO opportunity-selection method from concrete keyword candidates onward. Resume from the earliest unfinished selection contract and do not redo compatible fresh evidence.

## Boundaries

This skill starts at the former Step 5 / Ideas-stage wide recall. Seed generation, Google Autocomplete discovery, Semrush Ideas/Related discovery, and low-risk discovery cleaning belong to `seo-keyword-discovery`.

Inputs may come from:

- a valid `seo-keyword-discovery` handoff; or
- confirmed `emerging`/`breakout` `selection_handoff` directly from `emerging-keyword-monitor`.

Confirmed emerging keywords never route back through Seed/Autocomplete/Ideas discovery. Reuse compatible fresh evidence and acquire only the earliest missing selection contract.

Read before execution:

- `references/selection-sop.md`
- `references/data-contracts.md`
- `references/decision-rules.md`
- `references/thresholds.json` — unchanged source of truth.
- `references/source-acquisition.md`

## Execution integrity

The existing evaluator remains the calculator/classifier. Do not change its treatment of `pending_metrics`, KGR, SERP weak evidence, or KDRoi merely to enforce production completeness.

Production decisions are separately gated:

- Stage 6 Exact must pass the machine-readable `stage6_exact` contract before Stage 7+ production evaluation for that candidate.
- KGR requires project-collected real Google `intitle:"keyword"` evidence; KGR itself remains calculated by the evaluator.
- Real SERP review must pass `serp_review` before SERP-dependent final evaluation. KD 40–50 upgrade still requires the existing KGR + at least two structured weak-position rule.
- Serious finalists require real Google Trends cross-check. Keyword Planner remains optional.

New/current Semrush acquisition is only through the authenticated same-origin `sem.3ue.com` collector. No official API or alternative-provider fallback is permitted.

## Evidence discipline

Keep the existing `observed`, `calculated`, `analysis`, `unknown` meanings. Missing, invalid, numeric zero, and `not_applicable` remain distinct. Never manufacture Volume, KD, CPC, `intitle`, rank/url, DR, or trend observations.

## Completion

Blocked candidates remain reported with their reason while evidence-complete candidates may continue. A finished selection batch exposes complete/blocked counts and preserves the human final decision; `do_candidate` is not an automatic final choice.
