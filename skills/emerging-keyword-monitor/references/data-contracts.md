# Data Contracts and Unknown Semantics

## Data-state rule

Every value is one of: **observed**, **calculated**, **analysis**, or **unknown**. Missing data remains `null`/unknown. A malformed supplied value is **invalid**, never converted to unknown or zero.

## Observation-level schema

Preserve when available:

`keyword | observed_at | source | source_type | source_url | root_id | signal_value | signal_unit | country | time_window | metric_source | metric_database | first_observed_at | anchor_event | anchor_event_date | anchor_event_source | provenance_status`

Required provenance dimensions for a complete observation are:

`source | source_type | source_url | observed_at | country | time_window`

If any are missing, `provenance_status=incomplete`. The row may still be structurally valid; incomplete provenance must never be silently upgraded to verified evidence.

## Candidate schema

Aggregation/classification may preserve:

`keyword | root_id | signal_type | variant_subtype | first_observed_at | estimated_birth_window | age_days | baseline_signal | recent_signal | growth_rate | acceleration | persistence | source_count | source_evidence | anchor_event | anchor_event_date | volume | kd | cpc | intitle_results | serp_dedicated_pages | serp_ugc_pages | serp_intent_mismatch | emd_status | status | confidence | observed_at`

Fields are optional unless a rule explicitly requires them. Unknown fields stay unknown.

## Comparable-series key

Signals are comparable only inside the same:

`source × source_type × country × signal_unit × metric_database × time_window`

The aggregator computes each series independently. It never adds Google Trends indexes to Semrush Volume, social/community mentions, sitemap counts, or any other incompatible unit.

Source-reported aggregation windows are part of comparability. For example, a Google Trends `Past 24h` search-count observation and a `Past 48h` search-count observation are different measurement windows, not two persistence observations, even if they were captured at the same time for the same query.

A deterministic primary series is selected only to expose top-level baseline/recent fields. All series remain in `source_evidence`.

## Time windows

When observations exist, the aggregator may compute:

- `recent_7d`
- `previous_7d`
- `recent_30d`
- `previous_30d`
- `baseline_90d`
- `baseline_12m`

A missing window remains unknown. Missing days are not filled with zero.

## First observation and birth window

`first_observed_at` is the earliest timestamp present in the current evidence set. It does not establish the first search ever made for the keyword.

`estimated_birth_window` is optional and must be evidence-backed. It must not be synthesized from the first non-zero Google Trends point alone.

## Metrics and KGR

`volume`, `kd`, `cpc`, and `intitle_results` are observed metrics only. Their absence makes `metric_status=incomplete`, not zero/easy/new.

KGR is calculated only when both real `volume > 0` and real non-negative integer `intitle_results` are present:

`kgr = intitle_results / volume`

If `intitle_results` exists but Volume is unknown, KGR remains unknown. The monitor may label this `low_supply_signal`, but never `KGR pass`.

## Validation

Invalid inputs include negative signal values, negative Volume/CPC, KD outside `0..100`, NaN, Infinity, invalid dates, future `first_observed_at`, blank keyword, and malformed integer SERP counts. Invalid rows retain `validation_errors`.

Exact duplicate observations remain visible for audit but do not inflate aggregation, persistence, or source counts.
