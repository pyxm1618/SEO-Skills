# Decision Rules

## Primary eligibility

A row may compete for Primary only when all are true:

1. `role_candidate = core`;
2. `ownership_status = confirmed`;
3. `ownership_page_id = page_id`;
4. `serp_fast_status = confirmed`.

`source_seed`, high Volume, low KD, or high CPC cannot create ownership.

## Primary ranking

Among eligible Core Candidates:

1. prefer higher `target_scope_demand` when observed;
2. if tied, prefer higher `target_market_volume` when observed;
3. if still tied, keep stable order unless the caller explicitly enables CPC tie-break;
4. CPC may then break a true SEO-evidence tie, but may not overturn ownership, intent, or demand evidence.

A modifier is allowed to be Primary if it has been reclassified as `core` because it is necessary for entity disambiguation and its SERP Fast Check confirms target intent.

## SERP Fast vs SERP Deep

**SERP Fast Check:** required for every final Core Candidate. Confirm target entity intent from live result titles/types; record evidence.

**SERP Deep Review:** required only when:

- top Core candidates are close;
- generic wording creates entity ambiguity;
- hub/list and entity intent compete;
- brand/navigation or language contamination is plausible;
- two planned URLs may cannibalize;
- an intent/modifier may deserve its own URL.

## Cluster Observed Demand

Sum each normalized owned query once, inside one compatible `metric_scope_id`. Preserve unknown counts and scope mismatches. Do not label the result “traffic potential” or forecast ranking traffic.

## Cannibalization

Within the current mapping universe, flag:

- the same normalized keyword confirmed to multiple URLs;
- supplied page pairs with high SERP overlap;
- parent-child splits whose supplied SERP overlap is high.

The scripts use overlap thresholds only as review signals, not universal SEO laws.

## Content Module vs Independent URL

Prefer **Content Module** when parent/child SERPs substantially overlap or the user task/content is not independently established.

Raise **Independent URL Candidate** when all are observed/analysed:

- parent/child SERP overlap is low enough to support distinct intent;
- `task_divergence = true`;
- `content_independent = true`;
- target-scope demand is observed and positive.

Keep it a candidate until real SERP evidence supports the split. Never create programmatic child URLs solely because a modifier has Volume.
