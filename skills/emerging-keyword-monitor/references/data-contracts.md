# Data Contracts and Unknown Semantics

## Data-state rule

Every value is one of: **observed**, **calculated**, **analysis**, or **unknown**. Missing data remains `null`/unknown. A malformed supplied value is **invalid**, never converted to unknown or zero.

## Observation-level schema

Preserve when available:

`keyword | observed_at | source | source_type | source_url | root_id | signal_value | signal_unit | country | time_window | metric_source | metric_database | first_observed_at | anchor_event | anchor_event_date | anchor_event_source | provenance_status`

Required provenance dimensions for a complete signal observation are:

`source | source_type | source_url | observed_at | country | time_window | signal_unit`

If any are missing, `provenance_status=incomplete`. The row may still be structurally valid; incomplete provenance must never be silently upgraded to verified evidence.

## Candidate schema

Aggregation/classification may preserve:

`keyword | root_id | signal_type | variant_subtype | first_observed_at | estimated_birth_window | age_days | baseline_signal | novelty_baseline_signal | novelty_baseline_window | novelty_baseline_observations | recent_signal | growth_rate | acceleration | persistence | persistence_window | persistence_observations | latest_observation_age_days | distinct_observation_days | coverage_ratio | max_observation_gap_days | historical_positive_seen | historical_positive_observations | historical_positive_windows | source_count | source_evidence | anchor_event | anchor_event_date | volume | kd | cpc | intitle_results | metric_provenance | metric_compatibility_status | serp_dedicated_pages | serp_ugc_pages | serp_intent_mismatch | emd_status | status | confidence | observed_at`

Fields are optional unless a rule explicitly requires them. Unknown fields stay unknown.

## Comparable-series key

Signals are comparable only inside the same:

`source × source_type × country × signal_unit × metric_database × time_window`

The aggregator computes each series independently. It never adds Google Trends indexes to Semrush Volume, social/community mentions, sitemap counts, or any other incompatible unit.

Source-reported aggregation windows are part of comparability. For example, a Google Trends `Past 24h` search-count observation and a `Past 48h` search-count observation are different measurement windows, not two persistence observations, even if they were captured at the same time for the same query.

All series remain in `source_evidence`. Classification may prefer an independently verified fresh non-ended series over an ended series; it does not combine their numeric signal values.

## Time windows and persistence evidence

When observations exist, the aggregator may compute:

- `recent_7d`: days `0..6`
- `recent_30d`: days `0..29`
- matched 7-day growth baseline: days `7..89`
- matched 30-day growth baseline: days `30..89`
- `baseline_12m`: observed history through day `364`

The recent window and its growth baseline are mutually exclusive. If classification uses `recent_7d`, growth uses the day `7..89` baseline. If classification falls back to `recent_30d`, growth uses the day `30..89` baseline. An observation must never contribute to both the selected recent window and its selected growth baseline.

For persistence, comparable series may expose:

- `persistence_7d`
- `persistence_30d`
- `recent_7d_observations`
- `recent_30d_observations`
- `positive_7d_observations`
- `positive_30d_observations`

The classifier prefers the shortest recent window that satisfies the configured minimum observation depth. It uses 7-day evidence when sufficient and may fall back to 30-day evidence when the 7-day sample is too sparse. Missing observations are never synthesized to satisfy a threshold.

A missing window remains unknown. Missing days are not filled with zero.

## Freshness evidence

The aggregator exposes at least:

- `latest_observation_age_days`
- `distinct_observation_days`
- `coverage_ratio`
- `max_observation_gap_days`

These fields describe actual observation coverage; they do not fabricate missing daily observations. v1 uses `freshness.max_latest_observation_age_days_confirmed` as a calibratable temporal heuristic before confirming `emerging` or `breakout`. The current value is 7 days. Coverage ratio and maximum gap are retained as evidence and are not combined into a synthetic score.

If the latest observation is older than the configured freshness limit, or freshness is unknown, repeated historical positives cannot by themselves keep a candidate confirmed as `emerging`/`breakout`; the candidate remains `watch` unless fresh evidence arrives.

## Growth baseline, novelty baseline, and older history

`baseline_signal` is the non-overlapping temporal baseline used for growth, breakout, and mature-state calculations.

`net_new` also uses a novelty baseline whose history ends before the selected persistence window:

- when `persistence_window=recent_7d`, novelty baseline uses observed relative signal from days `7..89`;
- when `persistence_window=recent_30d`, novelty baseline uses observed relative signal from days `30..89`.

The classifier exposes `novelty_baseline_signal`, `novelty_baseline_observations`, and `novelty_baseline_window`.

A zero 90-day novelty baseline is not sufficient by itself for `net_new`. The monitor also preserves older available history through 12 months as `historical_positive_seen`, `historical_positive_observations`, and `historical_positive_windows`. Explicit positive demand earlier in the available 12-month evidence blocks `net_new`. This does not introduce a separate reactivation state; the candidate falls through to existing `breakout`, `watch`, `mature`, or other existing states according to evidence.

All zero values above remain relative-source observations. Google Trends index `0` does **not** prove absolute historical search Volume was zero and does not establish an absolute keyword birth date.

## First observation and incremental runs

`first_observed_at` means the earliest timestamp known to this evidence system, not the first search ever made for the keyword.

For incremental ingestion, if an input observation already carries an earlier valid `first_observed_at`, aggregation uses the minimum of that carried value and current observation timestamps. A daily incremental row must not reset first observation history or `age_days`.

`estimated_birth_window` is optional and must be evidence-backed. It must not be synthesized from the first non-zero Google Trends point alone.

## Metric provenance and compatibility

`volume`, `kd`, `cpc`, and `intitle_results` are observed metrics only. Every non-null metric exposed by aggregation has a metric record under `metric_provenance` (and equivalent per-field aliases) containing at least:

`value | source | metric_source | metric_database | country | observed_at`

The top-level numeric fields are convenience aliases derived from those records; they are not independent facts.

`metric_status=complete` is allowed only when the core `volume`, `kd`, and `cpc` records are all present and come from one traceable provider/database/country context. Missing records produce `incomplete`; cross-source, cross-database, or cross-market stitching is not silently promoted to a complete metric set. `metric_compatibility_status` makes compatibility explicit.

Metric absence remains unknown, not zero/easy/new.

## KGR

KGR is calculated only when both real `volume > 0` and real non-negative integer `intitle_results` are present **with provenance records whose market/context is compatible**:

`kgr = intitle_results / volume`

A bare numeric pair without provenance does not qualify. Cross-country inputs do not qualify. If both records use the same metric provider, their metric database must also match. Distinct providers may be used only when the market context is explicitly compatible; the classifier exposes `kgr_compatibility_status`.

If `intitle_results` exists but Volume is unknown, KGR remains unknown. The monitor may label this `low_supply_signal`, but never `KGR pass`.

## Validation

Invalid inputs include negative signal values, negative Volume/CPC, KD outside `0..100`, NaN, Infinity, invalid dates, future `first_observed_at`, blank keyword, and malformed integer SERP counts. Invalid rows retain `validation_errors`.

Exact duplicate observations remain visible for audit but do not inflate aggregation, persistence, or source counts.
