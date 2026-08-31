# Data Contracts

## Evidence types

Every material field is one of:

- **observed** — returned by a real keyword/SERP/source;
- **calculated** — deterministic transform of observed inputs;
- **analysis** — analyst/model interpretation, labeled as such;
- **unknown** — missing and left missing.

Never convert `unknown` to `0`.

## Normalized keyword row

Minimum fields:

| Field | Meaning |
|---|---|
| `page_id` | Planned page in the current mapping universe |
| `keyword` | Exact query string |
| `source_seed` | Discovery provenance only |
| `role_candidate` | `core`, `intent`, `non_target`, or `unknown` |
| `ownership_status` | `confirmed`, `rejected`, or `unknown` |
| `ownership_page_id` | Page that observed/analysed evidence assigns the query to |
| `serp_fast_status` | Optional SERP result: exactly `confirmed`, `mismatch`, or `unknown`; unknown is non-blocking and other values are invalid |
| `target_scope_demand` | Observed demand after explicit scope aggregation; null if unknown |
| `target_market_volume` | Optional observed priority-market demand |
| `kd` | Optional observed difficulty |
| `cpc` | Optional observed commercial signal |
| `metric_scope_id` | Identifier for compatible source/market/language/method scope |
| `cluster_include` | Whether this owned query participates in Cluster Observed Demand |

Recommended provenance fields: `metric_source`, `metric_database`, `language`, `market`, `observed_at`, `evidence_ref`, `metric_notes`.

## Architecture candidate

```json
{
  "parent_page_id": "hex-54",
  "child_page_id": "hex-54-romance",
  "keyword": "hexagram 54 in romance reading",
  "serp_overlap": 0.2,
  "task_divergence": true,
  "content_independent": true,
  "target_scope_demand": 260
}
```

Unknown evidence stays null. `serp_overlap` must be a finite ratio from 0 to 1 from an actually observed result set or deterministic comparison of stored SERP URLs. The evaluator emits `serp_overlap_status=observed|unknown|invalid`; only `observed` may support an independent URL.

## Page-pair cannibalization input

Use explicit pairs only inside the current mapping universe:

```json
{"page_a":"/hexagram-1/","page_b":"/hexagram-1-love/","serp_overlap":0.8}
```

The validator does not crawl the whole site and does not invent pairwise SERP similarity. Page-pair `serp_overlap` follows the same finite 0-to-1 contract: missing is unknown and non-blocking, while malformed or out-of-range values are invalid.
