# Classification Rules

## Signal types

### `net_new`

Use only when comparable historical observations **before the currently selected persistence window** show no sustained positive relative signal **and** the available 12-month evidence contains no reliable earlier positive-demand evidence.

The novelty check must not include the same recent observations that establish persistence. If older history shows positive demand and the query rises again after a quiet period, it must not be labeled `net_new`; v1 may classify it as `breakout` when the growth evidence supports that state, otherwise `watch`.

The label means **newly observed within the available evidence window**, not an absolute search-demand birth date. A zero relative-source novelty baseline does not prove absolute historical search Volume was zero.

### `breakout`

Requires a positive historical growth baseline plus persistent recent signal materially above that baseline. A keyword with an established baseline must not be relabeled `net_new` merely because growth is large.

### `emerging_variant`

Requires a real temporal signal plus an explicit semantic relationship to an existing expression. Supported subtypes:

- `new_expression`
- `typo`
- `modifier_shift`

The semantic relationship may be analyst/model interpretation, but the temporal metrics and timestamps must be observed/calculated from real evidence.

## Persistence, baseline, and growth

Temporal thresholds in `thresholds.json` are v1 shape rules for consistent classification. They are not product-launch or SEO-selection gates and should be recalibrated only after real replay samples.

Persistence is evaluated from the shortest supported recent evidence window that satisfies `min_recent_observations_confirmed`. The classifier prefers `recent_7d`; when that window is too sparse, it may fall back to `recent_30d`. If neither window has enough observations, the candidate remains unconfirmed. This is sampling-density logic, not a special case for any named source or weekly cadence.

Recent and baseline windows are mutually exclusive:

- `recent_7d` uses days `0..6`; its 90-day baseline starts at day `7`;
- `recent_30d` uses days `0..29`; its 90-day baseline starts at day `30`.

The same observation must never enter both the selected recent window and its growth/novelty baseline.

Growth is calculated only inside one comparable series. A positive recent signal with an observed zero growth baseline does not produce infinite growth; `growth_rate` stays unknown and the zero-baseline condition is represented explicitly.

## Freshness

Each series exposes at least:

- `latest_observation_age_days`
- `distinct_observation_days`
- `coverage_ratio`
- `max_observation_gap_days`

`temporal.max_latest_observation_age_days_confirmed` is a **v1 calibratable heuristic**, not a permanent truth and not an SEO-selection threshold. When the selected series is older than this limit, prior persistence may remain useful evidence but the classifier returns `watch` rather than confirming `emerging` or `breakout`.

Missing freshness metadata remains unknown; it is not treated as stale or fresh by invention.

## Source-bound trend status

`trend_status` belongs to a source/series. A `lasted`/ended status from one source cannot globally veto a separate fresh verified series. If the primary series is ended or stale and another verified, fresh, active series carries valid temporal evidence, classification may use that independent series and records it in `classification_primary_series`.

If the selected/only usable series reports `lasted`, the candidate remains `watch` unless new independent evidence supersedes it.

## Noise

Do not classify a one-day spike as noise merely because only one observation exists. With too little follow-up evidence, use `new_signal` or `watch`.

`noise` requires observed decay after a spike plus low persistence and no confirmed durable/repeatable search task. Event-driven queries may still be durable when a law, policy, exam, standard, product, or technology creates recurring search jobs.

`durable_search_intent` and `repeatable_page_or_product_fit` are analysis fields; unknown does not equal false.

## Anchor events

`anchor_event`, `anchor_event_date`, and `anchor_event_source` are contextual evidence. They are never mandatory for `emerging` or `breakout`.

## Metrics, provenance, and KGR

`volume`, `kd`, `cpc`, and `intitle_results` may remain as top-level compatibility fields, but each observed value must trace to its own `metric_provenance` record. Cross-market or cross-database values are not silently promoted to one complete metric set.

KGR is calculated only when real `volume > 0` and real non-negative integer `intitle_results` both have traceable, market-compatible provenance. Merely having two numeric values is insufficient. If provenance/context is missing or incompatible, KGR remains unknown.

The monitor may retain raw supply-side facts such as `serp_dedicated_pages`, `serp_ugc_pages`, and `serp_intent_mismatch`; v1 does not combine them into a `serp_vacuity_score`.

EMD status is weak auxiliary context only. It cannot create an emerging classification or fast-track decision.
