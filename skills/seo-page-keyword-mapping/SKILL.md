---
name: seo-page-keyword-mapping
description: Use when a predefined page inventory needs Primary/Secondary keyword ownership, query clusters, content modules, or possible child URLs mapped.
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
- **SERP Fast Check** and **SERP Deep Review** are optional enhancements. Missing SERP stays `unknown` and does not block Primary selection or batch completion; an observed `mismatch` still disqualifies the contradicted ownership.
- Keep **Core Keyword Demand** separate from **Cluster Observed Demand**. The latter is an observed aggregate, not a traffic forecast.
- A modifier may become Primary when it is required to disambiguate the entity and ownership evidence confirms the target page. Optional SERP may strengthen that decision; an observed mismatch rejects it.
- CPC does not override ownership or demand evidence; it is optional only as a final business tie-break after SEO evidence is otherwise tied.
- Language/market exclusions require observed evidence; never hard-code a country exclusion across projects.

## Mechanical Evaluation

Use the scripts for deterministic work:

```bash
python scripts/evaluate_mapping.py --input normalized.json --format json
python scripts/validate_mapping.py --input normalized.json --format json
```

`evaluate_mapping.py` ranks eligible Core Candidates, computes deduplicated cluster demand inside one metric scope, and classifies supplied architecture candidates. `validate_mapping.py` checks ownership collisions, observed Core SERP mismatches, and unsupported or high-overlap URL splits.

## Completion

A batch is complete when every page has explicit ownership evidence or an unresolved status, Primary/Secondary decisions preserve their evidence, Cluster Observed Demand reports scope/completeness, and current-universe cannibalization findings are retained. Missing optional SERP remains `unknown`; child URLs stay `review` unless independent intent is actually demonstrated.
