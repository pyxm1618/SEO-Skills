# Data Contracts and Unknown Semantics

## Data-state rule

Every value is one of **observed**, **calculated**, **analysis**, or **unknown**. Missing data remains `null`/`unknown`. Malformed supplied data is invalid, never converted to zero.

`unknown != 0`, `failed != noise`, and `not_attempted != no demand`.

## Candidate identity and run ledger

Every Radar candidate in current run scope has a stable `candidate_id`. The candidate ledger is the complete run inventory, including candidates that are:

- in scope and observed;
- in scope but failed/not attempted;
- `valid_no_data`;
- `unknown` domain relation;
- `out_of_scope`;
- carry-forward;
- excluded by the hard batch cap.

Candidates with zero observations stay in the ledger. They do not disappear and do not enter temporal classification.

Canonical reconciliation invariant:

`delivery_ids ⊆ route_ids = classified_ids ⊆ candidate_ids`.

The receipt records all four identity sets plus an identity digest and binds the candidate-ledger path/hash. Canonical replay and the Hook consume that same ledger-qualified set and recompute reconciliation. An explicit empty delivery set remains empty. Any mismatch is a run error.

## Independent state axes

Keep these fields semantically separate:

### Acquisition

`acquisition_status`:

- `data_acquired`
- `valid_no_data`
- `failed`
- `not_attempted`
- `not_applicable`

`acquisition_reason` explains failure, circuit-open skip, domain exclusion, batch cap, etc.

### Verification

`verification_status`:

- `verified`
- `verified_no_data`
- `pending_evidence`
- `not_run`

Example: valid Trends raw JSON followed by required screenshot timeout is `data_acquired + pending_evidence`, never verified delivery evidence.

### Temporal classification

Canonical `status`:

`new_signal | watch | emerging | breakout | mature | noise | insufficient_evidence`

Canonical `signal_type`:

`net_new | breakout | emerging_variant | unknown`

### Workflow/routing

Canonical `route`:

`selection_handoff | root_candidate_handoff | new_root_watchlist | monitor_only | no_handoff`

The shared Sheet human workflow status is independent of all the above.

## Observation-level schema

Preserve when available:

`keyword | candidate_id | domain | domain_relation | domain_relation_reason | observed_at | source | source_type | source_url | root_id | root_relation | root_candidate_hypothesis | variant_subtype | variant_evidence | previous_status | signal_value | signal_unit | country | time_window | metric_source | metric_database | first_observed_at | anchor_event | anchor_event_date | anchor_event_source | provenance_status | evidence_ref | screenshot_ref | acquisition_status | verification_status`

Required provenance dimensions for a complete temporal observation are:

`source | source_type | source_url | observed_at | country | time_window | signal_unit`

Incomplete provenance is never silently upgraded to verified evidence.

## Candidate context through the canonical pipeline

`runtime/emerging_pipeline.py` owns canonical aggregation, classification, routing, and identity reconciliation.

Non-temporal candidate context preserved through aggregation includes at least:

`candidate_id | domain | domain_relation | domain_relation_reason | root_id | root_relation | root_candidate_hypothesis | variant_subtype | variant_evidence | previous_status | acquisition_status | verification_status`

Conflicting non-missing context for one canonical keyword fails closed instead of guessing.

## Comparable-series key

Signals are comparable only inside the same:

`source × source_type × country × signal_unit × metric_database × time_window`

Never add or concatenate incompatible Google Trends timeframes, Semrush Volume, mentions, sitemap counts, or other unlike units.

Google Trends `5y`, `12m`, `90d`, `30d`, and `7d` indexes are independently normalized. Birth/history uses one long comparable series; shape uses the medium series; persistence/acceleration uses recent series.

Missing buckets remain unknown. They are not filled with zero.

## First observation and birth/history semantics

`first_observed_at` is the earliest timestamp known to the current evidence system, not the first search ever made.

`estimated_birth_window` is optional and evidence-backed. It must not be synthesized from a first non-zero point alone.

`demand_history_type` is:

`newly_observed | preexisting | resurgent | unknown`

When the first available buckets already contain sustained demand, classify the history as `preexisting` with `birth_reason=before_available_history`. Human-facing output should render that reason as **“早于可观测窗口”**. It is not an absolute birth date.

A quiet gap followed by a persistent return may be `resurgent`. An isolated spike is not a high-confidence birth.

## Domain relation

`domain_relation` is independent of temporal classification:

- `in_scope`: admitted to formal evidence collection/classification;
- `out_of_scope`: excluded with an auditable reason;
- `unknown`: traceable review item, not formally classified/delivered.

Generic lexical overlap alone is not enough to set `in_scope`.

The same gate applies to Rising discovery, supplemental discovery, and carry-forward. Carry-forward preserves its original `parent_anchor`/domain evidence; missing evidence remains `unknown` and the keyword itself is never substituted as parent proof.

## Historical persistence

The monitoring database stores both current acquisition health and last confirmed temporal state.

Confirmed history fields include:

`last_confirmed_status | last_confirmed_source_evidence | last_confirmed_at`

Current-run acquisition fields include:

`last_run_acquisition_status | last_run_acquisition_reason | acquisition_failure_count`

A current acquisition failure must not overwrite a prior confirmed `status` or confirmed evidence. Repeated acquisition failure leads to bounded retry/review behavior, not automatic `noise`, `out_of_scope`, or deletion. Future `next_review_at` and `paused_review` are request-admission gates for both carry-forward and current rediscovery; neither state is bypassed merely because a source rediscovers the keyword.

## Metric ownership and compatibility

`volume`, `kd`, `cpc`, `kdroi`, `kgr`, `intitle_results`, SERP evidence, and Selection intent are Selection-owned/commercial fields. Emerging does not fabricate or refresh them as part of temporal monitoring.

Their absence remains unknown.

Existing metric provenance rules still apply: a numerically complete but cross-provider/cross-market set is not automatically a compatible metric set.

## Unified keyword-library mirror

The shared Sheet is a human-facing mirror, not an input to temporal classification.

Stable identity is:

`normalized_keyword + market + language`.

Emerging may update only Emerging-owned temporal/provenance fields. It must preserve Discovery provenance, Selection-owned commercial metrics, and the human workflow `状态`.

Human status vocabulary such as `新发现 / 已选 / 已建站 / 放弃` is workflow metadata only. `新发现` means first entry into the human workflow and does not prove newly formed demand.

Display projection:

- `net_new` / `newly_observed` → `新词`
- canonical `breakout` → `上升`
- canonical `mature` may display `成熟需求`
- unsupported states → `unknown`

Never derive `平稳` from `mature`, and never derive `上升 / 下降 / 平稳` merely from the sign of `growth_rate`.

## Production delivery gate

Production Sheet delivery is fail-closed: only explicit `run_status=PASS` is eligible. `BLOCKED`, missing, or unknown run status performs zero production Sheet reads/writes; legacy databases are dry-run inspection only.

Monitoring database membership is not delivery eligibility. Production delivery requires explicit `delivery_eligible` on every record and delivers only records with `delivery_eligible=true`; missing eligibility never falls back to all records.

Unknown/out-of-scope/failed/not-attempted records remain auditable in run artifacts rather than being silently deleted.
