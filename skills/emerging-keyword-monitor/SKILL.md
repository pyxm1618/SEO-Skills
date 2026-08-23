---
name: emerging-keyword-monitor
description: Use when discovering or monitoring newly forming search demand, breakout queries, or new search expressions over time, including distinguishing net-new demand from breakout growth and routing confirmed emerging signals downstream.
---

# Emerging Keyword Monitor

Detect and maintain evidence for search demand that is newly observed, accelerating, or changing expression. This skill answers **what demand is forming or changing now**; it does not make final SEO opportunity decisions.

## Boundaries

Use this skill for temporal demand discovery and monitoring. It may consume `root_id` references from `keyword-root-library`, but it must never copy or mutate `root-library.csv`.

It may hand confirmed emerging candidates to `seo-keyword-selection`, but it must never emit `do_candidate`, `observe`, or `principle_eliminate` as final SEO decisions and must not modify that skill's thresholds.

Read before execution:

- `references/data-contracts.md` — observation/candidate fields and unknown semantics.
- `references/source-policy.md` — ingestion and provenance rules.
- `references/classification-rules.md` — net-new, breakout, variant, noise, and metric boundaries.
- `references/state-machine.md` — explainable states and transitions.
- `references/routing-rules.md` — downstream handoff rules.
- `references/thresholds.json` — v1 temporal-shape thresholds only.

## Evidence Discipline

`unknown != 0`. Missing values remain unknown; malformed values are invalid. Never invent Volume, KD, CPC, `intitle`, SERP facts, timestamps, first-seen dates, trend values, or growth.

`first_observed_at` means the first observation in the current evidence system. It is not an absolute keyword birth date. Google Trends zero is a relative signal, not proof of zero real searches.

Never add signals with different units or incomparable source contexts. Trends indexes, search volume, mentions, and other units remain separate series.

## Workflow

Validate observations:

```bash
python scripts/validate_observations.py --input observations.json --format json
```

Aggregate only comparable time series:

```bash
python scripts/aggregate_signals.py --input observations.json --format json
```

Classify temporal evidence:

```bash
python scripts/classify_emergence.py --input candidates.json --format json
```

Route without making final SEO decisions:

```bash
python scripts/route_candidates.py --input classified.json --format json
```

## Types and States

Signal types: `net_new`, `breakout`, `emerging_variant`. Variant subtypes: `new_expression`, `typo`, `modifier_shift`.

States: `new_signal`, `watch`, `emerging`, `breakout`, `mature`, `noise`, `insufficient_evidence`.

Every classification returns a reason, evidence used, remaining unknown fields, confidence, and explicit state-change metadata when a previous state is supplied. Anchor events may strengthen interpretation but are never mandatory.

## Data Sources

v1 supports clean CSV/JSON ingestion contracts for Google Trends exports, Semrush trend/keyword exports, competitor sitemap diffs, demand-source feeds, manual exports, API responses, or external connectors. These contracts do **not** claim that any third-party source is being scraped or monitored automatically.
