# Decision Rules — Current Defaults

These are operating defaults, not universal SEO laws. The machine-readable source of truth is `thresholds.json`; this document explains the rules. Change thresholds only through calibration, then update `thresholds.json`, this document, and tests together.

## 1. Ideas-stage recall

Recall is deliberately wider than final qualification.

| Recall pool | Rule |
|---|---|
| `main_recall` | Volume ≥ 5,000 and KD ≤ 55 |
| `blue_recall` | otherwise, Volume ≥ 300 and KD < 45 |
| `excluded_recall` | outside both rules |
| `pending_metrics` | Volume or KD unknown |

A term qualifying for both is labeled `main_recall`. `pending_metrics` is a holding state, not a failure: missing Ideas metrics must never be treated as zero or silently excluded.

## 2. Exact Volume pools

Using the current exact/authoritative metric value:

| Pool | Rule |
|---|---|
| `main` | Volume ≥ 9,000 |
| `blue_ocean` | 500 ≤ Volume < 9,000 |
| `below_floor` | Volume < 500 |
| `unknown` | Volume unavailable |

## 3. KD bands

| Band | Rule |
|---|---|
| `do_candidate` | KD < 40 |
| `observe` | 40 ≤ KD ≤ 50 |
| `principle_eliminate` | KD > 50 |
| `unknown` | KD unavailable |

KD 40–50 is not allowed to become a final `do_candidate` through KDRoi or high Volume alone.

## 4. CPC signal

- `positive_ge_0_10`: CPC ≥ $0.10.
- `low_lt_0_10`: CPC < $0.10.
- `unknown`: CPC unavailable.

Low CPC is **not** an automatic elimination. CPC is a monetization/value signal, not a universal demand gate.

## 5. KGR

`KGR = intitle_results / monthly_search_volume`

- `pass_lt_0_25`: KGR < 0.25.
- `not_blue_ocean`: KGR ≥ 0.25.
- `unknown`: numerator or denominator unavailable, or Volume ≤ 0.

A term with KGR ≥ 0.25 does not receive mechanical `do_candidate`; keep it as `observe_kgr` for judgment rather than fabricating a pass.

## 6. KD 40–50 SERP upgrade

A KD 40–50 term may upgrade from `observe` to `do_candidate` only when:

1. KGR passes (<0.25), **and**
2. real top-10 review documents at least **2 verifiable weak positions**.

Otherwise it remains `observe_serp` (or `pending_serp` if SERP review has not supplied a count).

Weak-position examples are defined in `data-contracts.md`. “Inner page” alone is not a weak position.

## 7. KDRoi

`KDRoi = Volume × CPC ÷ KD`

Calculate only when Volume and CPC are observed and KD is observed and > 0. Otherwise KDRoi is unknown.

KDRoi ranks/economically contextualizes candidates. It never overrides KD, KGR, real SERP, intent, or trend.

## 8. Mechanical status order

For the final evaluation stage:

1. documented `exclude_reason` → `excluded_manual`;
2. missing Volume or KD → `pending_metrics`;
3. Volume < 500 → `principle_eliminate_volume`;
4. KD > 50 → `principle_eliminate_kd`;
5. missing KGR inputs → `pending_kgr`;
6. KGR ≥ 0.25 → `observe_kgr`;
7. KD < 40 + KGR pass → `do_candidate`;
8. KD 40–50 + KGR pass + ≥2 weak positions → `do_candidate`;
9. KD 40–50 + KGR pass + missing SERP count → `pending_serp`;
10. KD 40–50 + KGR pass + <2 weak positions → `observe_serp`.

`do_candidate` is still not the human final decision.

## 9. Calibration

After every two completed batches, inspect human-selected keywords' Volume/KD/CPC/KGR distributions. If the same boundary is repeatedly contradicted by successful human choices, revise this file deliberately and update automated tests. Never adjust thresholds ad hoc inside a batch.

## 10. Reliability gates

Before any mechanical status is trusted:

1. impossible numeric inputs or a blank keyword produce `invalid_row`;
2. KD 40–50 SERP promotion uses only the evaluator-derived count from structured `serp_weak_evidence`; a manually supplied count alone is insufficient;
3. `provenance_status=incomplete` is a warning, not automatic elimination, but serious finalists must repair provenance before a human final decision;
4. duplicate rows are preserved and flagged; do not let them inflate cluster density.
