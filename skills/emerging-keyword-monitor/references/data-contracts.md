# Data Contracts and Unknown Semantics

## Data-state rule

Every value is one of: **observed**, **calculated**, **analysis**, or **unknown**. Missing data remains `null`/unknown. A malformed supplied value is **invalid**, never converted to unknown or zero.

## Observation-level schema

Preserve when available:

`keyword | observed_at | source | source_type | source_url | root_id | signal_value | signal_unit | country | time_window | metric_source | metric_database | first_observed_at | anchor_event | anchor_event_date | anchor_event_source | provenance_status`

Required provenance dimensions for a complete observation are:

`source | source_type | source_url | observed_at | country | time_window | signal_unit`

If any are missing, `provenance_status=incomplete`. The row may still be structurally valid; incomplete provenance must never be silently upgraded to verified evidence.

## Candidate schema

Aggregation/classification may preserve:

`keyword | root_id | signal_type | variant_subtype | demand_history_type | first_observed_at | estimated_birth_window | birth_window_start | birth_window_end | birth_source_resolution | birth_confidence | birth_reason | birth_evidence_series | resurgence_window | long_history_positive_seen | long_history_positive_observations | long_history_positive_windows | age_days | baseline_signal | novelty_baseline_signal | novelty_baseline_window | novelty_baseline_observations | historical_positive_seen | historical_positive_observations | historical_positive_windows | recent_signal | growth_rate | acceleration | persistence | persistence_window | persistence_observations | source_count | source_evidence | classification_primary_series | latest_observation_age_days | freshness_status | anchor_event | anchor_event_date | volume | kd | cpc | intitle_results | metric_provenance | metric_compatibility_status | kgr_compatibility_status | serp_dedicated_pages | serp_ugc_pages | serp_intent_mismatch | emd_status | status | confidence | observed_at`

Fields are optional unless a rule explicitly requires them. Unknown fields stay unknown.

## Comparable-series key

Signals are comparable only inside the same:

`source × source_type × country × signal_unit × metric_database × time_window`

The aggregator computes each series independently. It never adds Google Trends indexes to Semrush Volume, social/community mentions, sitemap counts, or any other incompatible unit.

Source-reported aggregation windows are part of comparability. For example, a Google Trends `Past 24h` search-count observation and a `Past 48h` search-count observation are different measurement windows, not two persistence observations, even if captured at the same time for the same query.

A deterministic primary series exposes the current classification-compatible series: recent `7d`/`30d`/`90d` windows rank ahead of medium `12m`, which ranks ahead of long `5y` and unknown windows. All series remain in `source_evidence`; the long series is still independently selected for history/birth inference. Classification may select a different verified fresh series when the selected primary is explicitly ended or stale; that choice is exposed as `classification_primary_series`.

## Time windows and persistence evidence

When observations exist, the aggregator computes per-series windows including:

- `recent_7d` = days `0..6`
- `recent_30d` = days `0..29`
- `baseline_90d_7d` = days `7..89`
- `baseline_90d_30d` = days `30..89`
- matching 12-month historical windows beginning after the selected recent window

For persistence, comparable series may also expose:

- `persistence_7d`
- `persistence_30d`
- `recent_7d_observations`
- `recent_30d_observations`
- `positive_7d_observations`
- `positive_30d_observations`

The classifier prefers the shortest recent window that satisfies the configured minimum observation depth. It uses 7-day evidence when sufficient and may fall back to 30-day evidence when the 7-day sample is too sparse. The matching baseline changes with that selection, so recent and baseline observations are mutually exclusive. Missing observations are never synthesized to satisfy a threshold.

A missing window remains unknown. Missing days are not filled with zero.

### Google timeframe-local normalization

Google Trends `5y`, `12m`, `90d`, `30d`, and `7d` indexes have separate normalization contexts. Each observation retains its `time_window`, source URL, requested timeframe, actual bucket resolution, and evidence reference. The comparable-series key keeps these windows separate, so a `5y` value cannot be compared with a `90d` value and points from different windows are never concatenated. Birth/history inference consumes only one long (`5y`) series. The medium window describes shape; recent windows describe persistence and acceleration.

## Freshness and coverage

Each comparable series exposes, when calculable:

- `latest_observation_age_days`
- `distinct_observation_days`
- `coverage_ratio`
- `max_observation_gap_days`

`coverage_ratio` is descriptive coverage of distinct observed days within the last 30 calendar days; missing days are not imputed as zero. These fields allow stale-but-persistent history to be distinguished from genuinely current signal.

## Growth baseline versus novelty/history evidence

`baseline_signal` is selected together with the active recent window and remains the baseline used for growth, breakout, and mature-state calculations.

`net_new` uses history ending before the selected persistence window:

- with `recent_7d`, the near-term novelty baseline starts at day `7`;
- with `recent_30d`, it starts at day `30`.

The series also retains 12-month positive-history evidence through `historical_positive_seen`, `historical_positive_observations`, and `historical_positive_windows` (plus per-window variants). A positive observation in that available earlier history prevents a `net_new` label even if the nearer 90-day baseline is quiet.

These remain relative source observations. A zero novelty baseline does **not** prove absolute historical search Volume was zero and does not establish an absolute keyword birth date.

## First observation and incremental replay

`first_observed_at` is the earliest known timestamp carried by the available evidence, not the first search ever made for the keyword.

For incremental runs, if an input observation/candidate carries a prior `first_observed_at`, aggregation takes the minimum of that carried timestamp and current observation timestamps. A daily incremental input therefore must not reset the first-seen date or `age_days`.

`estimated_birth_window` is optional and must be evidence-backed. It must not be synthesized from the first non-zero Google Trends point alone.

Birth/history analysis also preserves `birth_window_start`, `birth_window_end`, `birth_source_resolution`, `birth_confidence`, `birth_reason`, and `birth_evidence_series`. Weekly/monthly source buckets are reported at bucket/month precision rather than fabricated day precision. `demand_history_type` is `newly_observed`, `preexisting`, `resurgent`, or `unknown`; a sustained positive series beginning at the first available bucket is `preexisting`/`before_available_history`. A quiet gap followed by a later persistent rise is `resurgent`. An isolated spike is not a high-confidence birth.

## Metric provenance and compatibility

`volume`, `kd`, `cpc`, and `intitle_results` are observed metrics only. Their absence is unknown, not zero/easy/new.

Each non-missing metric is accompanied by its own `metric_provenance` record containing at least:

`value | source | metric_source | metric_database | country | observed_at`

Top-level metric fields are retained for downstream compatibility, but they are derived from those traceable metric records.

`metric_compatibility_status` applies to the **core keyword metric set** `volume + kd + cpc`. Those three values may be treated as one complete set only when their `metric_source`, `metric_database`, and `country` are compatible. For example, Semrush US Volume/KD/CPC may form one compatible set; Semrush Volume/KD combined with Google Ads CPC must not be silently promoted to `complete`.

`metric_status=complete` requires `volume`, `kd`, and `cpc` to be present with compatible core-metric provenance. A numerically complete but cross-provider, cross-database, or cross-market set is not complete.

## KGR

KGR has a separate compatibility contract because its numerator and denominator normally come from different providers.

`kgr_compatibility_status` applies only to `volume + intitle_results`. It requires traceable provenance plus compatible `metric_database` and `country`; it deliberately does **not** require the same `metric_source`.

Therefore a normal pairing such as Semrush US Volume + Google US `intitle` is compatible, while US Volume + UK `intitle` is not.

KGR is calculated only when both real `volume > 0` and real non-negative integer `intitle_results` have traceable, compatible provenance:

`kgr = intitle_results / volume`

If Volume is unknown, provenance is absent, or the two metric records are market/database-incompatible, KGR remains unknown. The presence of `intitle_results` alone may be retained as supply-side evidence but never as a KGR pass.

## Validation

Invalid inputs include negative signal values, negative Volume/CPC, KD outside `0..100`, NaN, Infinity, invalid dates, future `first_observed_at`, blank keyword, and malformed integer SERP counts. Invalid rows retain `validation_errors`.

Exact duplicate observations remain visible for audit but do not inflate aggregation, persistence, or source counts.
