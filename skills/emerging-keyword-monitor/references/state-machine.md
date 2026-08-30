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

## Emerging Radar history context

`demand_history_type` is independent context, not a replacement state: `newly_observed` describes a persistent rise after a low observed baseline, `preexisting` describes sustained demand already present at the first available long-series buckets, and `resurgent` describes a prior positive run, observed quiet gap, and later persistent rise. `preexisting` and `resurgent` block `net_new`; the existing temporal classifier still decides canonical `breakout` from its own comparable baseline, growth, persistence, and freshness evidence.
