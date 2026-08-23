# Demand Scope and Language/Market Rules

`Raw Global` is not automatically the demand of the target language. Market, language, script, and source behavior are separate dimensions.

## Required outputs

When the source permits it, preserve:

- `raw_global_volume` — source-provided or raw country sum for audit;
- `exact/core observed demand` — reliable observed demand for the query itself;
- `target_scope_demand` — the explicitly aggregated market/language/script scope used for Mapping;
- `metric_scope_id` — stable identifier for the aggregation contract.

## Demand Scope Aggregation

Prefer source-native geography/language controls when available. If aggregation is still required, document:

1. included markets;
2. included languages/scripts/query variants;
3. deduplication rule;
4. close-variant policy;
5. exclusions and their evidence;
6. observation date/source.

Do not mix scopes inside Cluster Observed Demand.

## Evidence-based exclusions

Never hard-code a rule such as “Chinese always excludes Japan.” Exclude a market only when observed evidence shows that its volume is not the target-language demand being mapped, for example same-script or same-character contamination in the actual dataset/SERP.

Likewise, close-match rows may be incorporated only when the project has evidence that they represent the intended script/language variant rather than semantic expansion.

## Multi-script languages

When Simplified/Traditional, spelling variants, transliteration, or other script forms are separate real queries, query them directly when feasible. Aggregate only after documenting whether they are distinct observed strings or source-level close variants.

## Cluster Observed Demand

Definition:

> Sum of deduplicated, ownership-confirmed query strings with observed demand, assigned to the same page under one compatible metric scope.

Report alongside:

- `cluster_keyword_count`;
- `cluster_unknown_keyword_count`;
- `cluster_scope_mismatch_count`;
- `cluster_demand_complete`.

This is an observed aggregate for relative comparison, not an estimate of clicks, sessions, or ranking traffic.
