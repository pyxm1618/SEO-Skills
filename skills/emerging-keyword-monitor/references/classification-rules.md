# Classification Rules

## Signal types

### `net_new`

Use only when comparable historical observations before the currently selected persistence window show no sustained positive relative signal, recent signal becomes persistent, **and the available older history contains no reliable prior positive-demand evidence**.

The novelty check must not include the same recent observations that establish persistence. A keyword that had explicit positive demand earlier in the available 12-month evidence cannot be called `net_new` merely because the latest 90-day baseline went quiet.

The label means **newly observed within the evidence window**, not an absolute search-demand birth date. A zero Google Trends or other relative-source baseline does not prove absolute historical search Volume was zero.

### `breakout`

Requires a positive non-overlapping historical growth baseline plus persistent fresh recent signal materially above that baseline. A keyword with an established baseline must not be relabeled `net_new` merely because growth is large.

### `emerging_variant`

Requires a real temporal signal plus an explicit semantic relationship to an existing expression. Supported subtypes:

- `new_expression`
- `typo`
- `modifier_shift`

The semantic relationship may be analyst/model interpretation, but temporal metrics and timestamps must come from real evidence.

## Persistence, growth, and freshness

Temporal thresholds in `thresholds.json` are v1 shape rules for consistent classification. They are not product-launch or SEO-selection gates and should be recalibrated only after real replay samples.

Persistence is evaluated from the shortest supported recent evidence window that satisfies `min_recent_observations_confirmed`. The classifier prefers `recent_7d`; when that window is too sparse, it may fall back to `recent_30d`. If neither window has enough observations, the candidate remains unconfirmed. This is sampling-density logic, not a special case for any named source or weekly cadence.

The growth baseline must match the selected recent window and must not overlap it:

- `recent_7d` → baseline days `7..89`;
- `recent_30d` → baseline days `30..89`.

The aggregator preserves per-window persistence, baseline, growth, and observation counts so classification can select one coherent series/window without fabricating observations.

Freshness is a separate confirmation requirement. v1 uses `freshness.max_latest_observation_age_days_confirmed=7` as a calibratable temporal heuristic. A series whose latest observation is older than that limit, or whose freshness is unknown, cannot remain confirmed `emerging`/`breakout` solely because older observations have high persistence. It remains `watch` until fresh evidence arrives.

`distinct_observation_days`, `coverage_ratio`, and `max_observation_gap_days` are retained for diagnosis. v1 does not combine them into a complexity score.

A positive recent signal with an observed zero growth baseline does not produce infinite growth; `growth_rate` stays unknown and the zero-baseline condition is represented explicitly.

## Cross-source evidence and `trend_status`

`trend_status` belongs to its source/comparable series. `lasted` on one source is not a keyword-wide veto.

Classification may prefer an independently verified, fresh, non-ended series with enough recent observation depth. An ended source can lower confidence in that source or leave the candidate at `watch`, but it must not suppress another independent verified series that still supports fresh `emerging`/`breakout` evidence.

If the selected/remaining viable evidence is ended, or no alternative fresh verified series qualifies, `lasted` may result in `watch`.

## Older positive history

For the selected recent window, the monitor inspects available comparable history through 12 months and exposes:

- `historical_positive_seen`
- `historical_positive_observations`
- `historical_positive_windows`

Explicit older positive history blocks `net_new`. This version does not add a new `reactivation` state; such cases fall through to existing states such as `breakout`, `watch`, or `mature` according to the remaining evidence.

## Noise

Do not classify a one-day spike as noise merely because only one observation exists. With too little follow-up evidence, use `new_signal` or `watch`.

`noise` requires observed decay after a spike plus low persistence and no confirmed durable/repeatable search task. Event-driven queries may still be durable when a law, policy, exam, standard, product, or technology creates recurring search jobs.

`durable_search_intent` and `repeatable_page_or_product_fit` are analysis fields; unknown does not equal false.

## Anchor events

`anchor_event`, `anchor_event_date`, and `anchor_event_source` are contextual evidence. They are never mandatory for `emerging` or `breakout`.

## Supply-side facts

The monitor may retain raw `intitle_results`, `serp_dedicated_pages`, `serp_ugc_pages`, and `serp_intent_mismatch`. v1 does not combine them into a `serp_vacuity_score`.

KGR requires compatible Volume/intitle provenance; two bare numbers are not enough.

EMD status is weak auxiliary context only. It cannot create an emerging classification or fast-track decision.
