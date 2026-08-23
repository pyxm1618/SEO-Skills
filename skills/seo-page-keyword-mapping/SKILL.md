---
name: seo-page-keyword-mapping
description: Use when a predefined set of entity, category, location, product, glossary, or localized pages must be mapped to Primary/Secondary SEO keywords, ownership-confirmed query clusters, content modules, and possible child URLs using real keyword and SERP evidence.
---

# SEO Page Keyword Mapping

Map a known page/entity inventory to search demand without confusing discovery source, demand size, or monetization with URL ownership.

## Boundaries

Use this skill after the page universe is known. Use `keyword-root-library` for reusable demand roots and `seo-keyword-selection` for deciding which opportunities are worth building. This skill decides **which query belongs to which planned URL** and how strongly it should be represented there.

Read before execution:

- `references/workflow.md` — seven-stage workflow and resume rules.
- `references/data-contracts.md` — normalized fields and evidence types.
- `references/decision-rules.md` — Primary/Secondary, SERP, CPC, cannibalization, H2-vs-URL rules.
- `references/demand-scope.md` — market/language aggregation and Cluster Observed Demand.
- `references/source-acquisition.md` — real-data acquisition, including optional Semrush relay usage.

## Non-Negotiable Rules

- `source_seed` is discovery provenance, never page ownership.
- `unknown` is not zero. Never invent Volume, KD, CPC, rankings, SERP facts, or language adjustments.
- Every final Core Candidate requires a **SERP Fast Check**. Use **SERP Deep Review** only for conflicts, close decisions, ambiguity, cannibalization, or split-page decisions.
- Keep **Core Keyword Demand** separate from **Cluster Observed Demand**. The latter is an observed aggregate, not a traffic forecast.
- A modifier may become Primary when it is required to disambiguate the entity and SERP evidence confirms ownership.
- CPC does not override ownership or demand evidence; it is optional only as a final business tie-break after SEO evidence is otherwise tied.
- Language/market exclusions require observed evidence; never hard-code a country exclusion across projects.

## Mechanical Evaluation

Use the scripts for deterministic work:

```bash
python scripts/evaluate_mapping.py --input normalized.json --format json
python scripts/validate_mapping.py --input normalized.json --format json
```

`evaluate_mapping.py` ranks eligible Core Candidates, computes deduplicated cluster demand inside one metric scope, and classifies supplied architecture candidates. `validate_mapping.py` checks ownership collisions, missing Core SERP confirmation, and supplied high-overlap split/cannibalization risks.

## Completion

A batch is complete only when every page has explicit ownership evidence or an unresolved status, Primary/Secondary decisions preserve their evidence, Cluster Observed Demand reports scope/completeness, current-universe cannibalization checks are clear, and child URLs remain candidates unless independent intent is actually demonstrated.
