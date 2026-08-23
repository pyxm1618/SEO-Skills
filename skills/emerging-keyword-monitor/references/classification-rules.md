# Classification Rules

## Signal types

### `net_new`

Use only when comparable historical observations **before the currently selected persistence window** show no sustained positive relative signal and recent signal becomes persistent. The novelty check must not include the same recent observations that are being used to establish persistence.

The label means **newly observed within the evidence window**, not an absolute search-demand birth date. A zero relative-source novelty baseline does not prove absolute historical search Volume was zero.

### `breakout`

Requires a positive historical growth baseline plus persistent recent signal materially above that baseline. A keyword with an established baseline must not be relabeled `net_new` merely because growth is large.

### `emerging_variant`

Requires a real temporal signal plus an explicit semantic relationship to an existing expression. Supported subtypes:

- `new_expression`
- `typo`
- `modifier_shift`

The semantic relationship may be analyst/model interpretation, but the temporal metrics and timestamps must be observed/calculated from real evidence.

## Persistence and growth

Temporal thresholds in `thresholds.json` are v1 shape rules for consistent classification. They are not product-launch or SEO-selection gates and should be recalibrated only after real replay samples.

Persistence is evaluated from the shortest supported recent evidence window that satisfies `min_recent_observations_confirmed`. The classifier prefers `recent_7d`; when that window is too sparse, it may fall back to `recent_30d`. If neither window has enough observations, the candidate remains unconfirmed. This is sampling-density logic, not a special case for any named source or weekly cadence.

The aggregator preserves per-window persistence and observation counts so the classifier can make that choice without fabricating missing observations. A sparse 7-day window must not erase valid 30-day persistence evidence.

Growth is calculated only inside one comparable series. `baseline_signal` is the growth baseline used for breakout/mature calculations. `net_new` uses the separate `novelty_baseline_signal`, selected so its history ends before the chosen persistence window. A positive recent signal with an observed zero growth baseline does not produce infinite growth; `growth_rate` stays unknown and the zero-baseline condition is represented explicitly.

## Noise

Do not classify a one-day spike as noise merely because only one observation exists. With too little follow-up evidence, use `new_signal` or `watch`.

`noise` requires observed decay after a spike plus low persistence and no confirmed durable/repeatable search task. Event-driven queries may still be durable when a law, policy, exam, standard, product, or technology creates recurring search jobs.

`durable_search_intent` and `repeatable_page_or_product_fit` are analysis fields; unknown does not equal false.

## Anchor events

`anchor_event`, `anchor_event_date`, and `anchor_event_source` are contextual evidence. They are never mandatory for `emerging` or `breakout`.

## Supply-side facts

The monitor may retain raw `intitle_results`, `serp_dedicated_pages`, `serp_ugc_pages`, and `serp_intent_mismatch`. v1 does not combine them into a `serp_vacuity_score`.

EMD status is weak auxiliary context only. It cannot create an emerging classification or fast-track decision.
