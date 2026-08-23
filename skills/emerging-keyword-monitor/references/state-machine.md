# Explainable State Machine

Allowed states:

| state | meaning |
|---|---|
| `new_signal` | A real recent signal exists, but follow-up depth is too small to establish persistence. |
| `watch` | Repeated evidence exists but does not yet satisfy a specific emerging/mature/noise pattern. |
| `emerging` | Persistent `net_new` or `emerging_variant` evidence is established. |
| `breakout` | A positive historical baseline exists and recent persistent demand materially exceeds it. |
| `mature` | Demand has a long positive baseline without material recent acceleration. |
| `noise` | A spike has been observed to decay with low persistence and no confirmed repeatable search task. |
| `insufficient_evidence` | Comparable/verifiable temporal evidence is missing, provenance is insufficient, or inputs are invalid. |

## Transition evidence

Classification outputs:

- `status_reason`
- `evidence_used`
- `unknown_fields`
- `confidence`
- `previous_status`
- `state_changed`
- `classification_errors`

These fields make state changes inspectable rather than score-only decisions.

## Confidence

Confidence is discrete and explainable. Persistence and multiple independently verified sources can strengthen confidence. No composite Emerging Score is used.

Anchor events can be recorded in `evidence_used` but are not transition gates.
