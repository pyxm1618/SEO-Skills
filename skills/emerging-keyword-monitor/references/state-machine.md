# Explainable State Machine

The classifier state machine describes temporal demand only. It does **not** describe source acquisition health, verification health, or human workflow progress.

## Canonical classifier states

| state | meaning |
|---|---|
| `new_signal` | A real recent signal exists, but follow-up depth is too small to establish persistence. |
| `watch` | Repeated evidence exists but does not yet satisfy a specific emerging/mature/noise pattern. |
| `emerging` | Persistent `net_new` or `emerging_variant` evidence is established. |
| `breakout` | A positive historical baseline exists and recent persistent demand materially exceeds it. |
| `mature` | Demand has a long positive baseline without material recent acceleration. |
| `noise` | A spike has been observed to decay with low persistence and no confirmed repeatable search task. |
| `insufficient_evidence` | Comparable/verifiable temporal evidence is insufficient for a stronger temporal classification. |

`mature` means established demand. It does not mean “flat” or “平稳”.

## Acquisition and verification are not classifier transitions

Current source state is tracked separately:

- `data_acquired`
- `valid_no_data`
- `failed`
- `not_attempted`
- `not_applicable`

Verification is also separate:

- `verified`
- `verified_no_data`
- `pending_evidence`
- `not_run`

Therefore:

- screenshot timeout after raw data does not transition a candidate to `noise` or `insufficient_evidence`;
- a circuit-open skip does not create a temporal verdict;
- `valid_no_data` is not a negative classifier state;
- domain `unknown/out_of_scope` is not a classifier state;
- a current acquisition failure does not overwrite a prior confirmed classifier state.

## Transition evidence

Confirmed classification outputs remain inspectable through:

- `status_reason`
- `evidence_used`
- `unknown_fields`
- `confidence`
- `previous_status`
- `state_changed`
- `classification_errors`

`previous_status` is prior confirmed lifecycle context for the same `(domain, keyword)`. It is not reset merely because current Rising discovery did not rediscover the keyword.

## Cross-run observation lifecycle

The monitoring database derives a separate `observation_state` only from confirmed classifier history:

| confirmed classifier status | observation_state | default next-run behavior |
|---|---|---|
| `new_signal`, `watch`, `insufficient_evidence` | `watching` | carry forward and seek fresh temporal evidence |
| `emerging`, `breakout` | `graduated` | retain history and stop default carry-forward after downstream handoff |
| `mature`, `noise` | `retired` | retain history and stop default carry-forward |

Current acquisition health is stored separately as `last_run_acquisition_status` / `last_run_acquisition_reason`.

On acquisition failure:

1. keep `last_confirmed_status`, `last_confirmed_source_evidence`, and `last_confirmed_at` unchanged;
2. increment bounded acquisition-failure bookkeeping only for actual acquisition failures;
3. retry on the configured schedule;
4. after the bounded retry budget, pause for review rather than auto-classifying as `noise`, `out_of_scope`, or deleting the record.

Unknown/unrecognized classifier states are not retirement verdicts.

## Carry-forward

Carry-forward is lifecycle continuation, not a new discovery event.

A carried record:

- is re-qualified through the current domain gate;
- does not create a synthetic Google Rising event;
- cannot bypass current batch/retry limits, `next_review_at`, or `paused_review`;
- preserves the historical parent/domain evidence used for re-qualification and never substitutes the keyword itself as parent proof;
- remains `unknown` for review when that domain evidence is missing;
- retains prior confirmed state when current evidence acquisition fails.

If current discovery rediscovers the same keyword, current discovery context wins and historical fields only fill missing values.

## Demand-history context

`demand_history_type` is independent history context:

- `newly_observed`
- `preexisting`
- `resurgent`
- `unknown`

`preexisting` with `birth_reason=before_available_history` means demand is already present at the beginning of the available long series. Human-facing wording is “早于可观测窗口”.

`preexisting` and `resurgent` block a `net_new` interpretation; canonical breakout still depends on the classifier's baseline, growth, persistence, and freshness rules.

## Confidence

Confidence is discrete and explainable. Persistence and independently verified evidence can strengthen confidence. No composite Emerging Score is used.

Anchor events may be recorded in evidence but are not transition gates.
