# Classification Rules

## Signal types

### `net_new`

Use only when comparable historical observations exist, the historical relative signal shows no sustained positive baseline, and recent signal becomes persistent. The label means **newly observed within the evidence window**, not an absolute search-demand birth date.

### `breakout`

Requires a positive historical baseline plus persistent recent signal materially above that baseline. A keyword with an established baseline must not be relabeled `net_new` merely because growth is large.

### `emerging_variant`

Requires a real temporal signal plus an explicit semantic relationship to an existing expression. Supported subtypes:

- `new_expression`
- `typo`
- `modifier_shift`

The semantic relationship may be analyst/model interpretation, but the temporal metrics and timestamps must be observed/calculated from real evidence.

## Persistence and growth

Temporal thresholds in `thresholds.json` are v1 shape rules for consistent classification. They are not product-launch or SEO-selection gates and should be recalibrated only after real replay samples.

Growth is calculated only inside one comparable series. A positive recent signal with an observed zero baseline does not produce infinite growth; `growth_rate` stays unknown and the zero-baseline condition is represented explicitly.

## Noise

Do not classify a one-day spike as noise merely because only one observation exists. With too little follow-up evidence, use `new_signal` or `watch`.

`noise` requires observed decay after a spike plus low persistence and no confirmed durable/repeatable search task. Event-driven queries may still be durable when a law, policy, exam, standard, product, or technology creates recurring search jobs.

`durable_search_intent` and `repeatable_page_or_product_fit` are analysis fields; unknown does not equal false.

## Anchor events

`anchor_event`, `anchor_event_date`, and `anchor_event_source` are contextual evidence. They are never mandatory for `emerging` or `breakout`.

## Supply-side facts

The monitor may retain raw `intitle_results`, `serp_dedicated_pages`, `serp_ugc_pages`, and `serp_intent_mismatch`. v1 does not combine them into a `serp_vacuity_score`.

EMD status is weak auxiliary context only. It cannot create an emerging classification or fast-track decision.
