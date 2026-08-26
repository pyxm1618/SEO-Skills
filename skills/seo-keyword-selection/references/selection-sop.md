# SEO Keyword Selection SOP

This workflow starts at the former Step 5. Former Steps 0–4 now belong to `seo-keyword-discovery`; their business logic is migrated, not redesigned.

Inputs are either a valid discovery handoff or a confirmed `emerging`/`breakout` `selection_handoff`. Emerging handoffs never rerun Seed, Google Autocomplete, or Semrush Ideas discovery. Reuse compatible fresh evidence and resume from the earliest missing selection contract.

## 5. Ideas-stage wide recall

Use the unchanged broad recall thresholds from `decision-rules.md`. Rows whose Ideas Volume/KD are missing remain `pending_metrics`, not rejected and not final decisions. Route credible `pending_metrics` rows to Stage 6 Exact acquisition or park them explicitly.

## 6. Exact metric retrieval — production hard gate

For each candidate obtain current US Volume, Semrush KD, CPC, intent, competition level, and 12-month trend through the project `sem.3ue.com` relay collector. Preserve:

`metric_source=Semrush | metric_database=us | metric_stage=exact | observed_at | relay_origin | provenance_ref`

Validate the candidate against `runtime/stage_contracts.json` stage `stage6_exact` before Stage 7+ production evaluation.

The existing evaluator may still mechanically process incomplete rows and retain `pending_metrics`; production code must not present those rows as completed candidates. If Exact acquisition still cannot satisfy the contract, mark that candidate `BLOCKED` and continue other evidence-complete candidates.

## 7. Exact pool + KD band

Apply the unchanged exact Volume pools and KD bands. KD 40–50 remains observable, not automatically viable.

## 8. CPC + intent review

Treat CPC ≥ $0.10 as the existing positive commercial signal, not a universal hard gate. Review actual user intent and best fulfillment form.

## 9. AI intent / SERP hypothesis

AI may predict likely SERP shape only to prioritize review work. It is `analysis`, not observed rank, DR, or competitor strength.

## 10. Compress manual-review pool

Using observed Volume/KD/CPC/intent plus clear exclusions, reduce the set to roughly 15–30 terms for manual KGR work. This is workload control, not sector elimination.

## 11. Observe `intitle`

Use the project Google live collector for the exact query `intitle:"keyword"`. Save real visible count, market, timestamp, and evidence. Bing counts, generic Google counts, API row counts, AI estimates, or KD inference are prohibited.

If the count cannot be reliably obtained, the candidate becomes `BLOCKED_KGR` / pending KGR execution state. Do not replace the evaluator's canonical business status with that execution state.

## 12. Calculate KGR

KGR remains calculated by `evaluate_candidates.py` from real `intitle_results` and Volume. Do not hand-fill KGR or add an independent KGR hook. The existing `<0.25` rule is unchanged.

## 13. Review real SERP top 10

Use the project Google live collector to obtain current top-10 rank/url evidence. AI may analyze intent fit, page quality, weakness, freshness, UGC, small-site presence, and similar qualities on top of those observed facts. External facts such as DR must be actually acquired or remain unknown.

KD 40–50 may upgrade only under the existing rule: KGR < 0.25 plus real top 10 plus structured weak evidence plus at least two verifiable weak positions. The evaluator remains authoritative for this mechanical upgrade behavior.

## 14. Trend validation

Semrush 12-month trend is already mandatory in the Stage 6 Exact contract. Serious finalists additionally require a real Google Trends cross-check through the project collector. This is `CONDITIONAL_REQUIRED` only for finalists.

## 15. Optional Keyword Planner cross-check

Google Ads Keyword Planner remains optional. Its absence is not a production-stage failure.

## 16. Calculate KDRoi

Keep the existing formula and evaluator semantics: `Volume × CPC ÷ KD` when required inputs exist and KD > 0. KD = 0 is `not_applicable` for KDRoi in reporting and must not block the workflow. Do not add a collector or independent hook for KDRoi.

## 17. Final decision table

Maintain at least:

`keyword | domain | root | parent_seed | volume | kd | cpc | metric_source | metric_database | observed_at | metric_stage | provenance_status | intent | trend | intitle_results | kgr | serp_weak_evidence | serp_weak_points | page_form | kdroi | risk | status | duplicate_warning`

Also report `complete_count`, `blocked_count`, and blocked reasons. Never silently delete blocked candidates.

## 18. Cluster opportunities

Cluster surviving evidence-complete terms back to `domain × root × parent_seed` using the existing method.

## 19. Infer product directions

Translate strong demand clusters into possible product/content architectures. Keywords remain demand evidence, not products.

## 20. Human final decision

The human selects 1–3 priorities after considering product advantage, build cost, content ability, SEO resources, monetization, data access, time, interest, and whether a materially better result can be built. No hook or evaluator replaces this decision.

## 21. Calibrate thresholds

Keep the existing calibration rule. Never alter thresholds ad hoc during a batch.

## Feedback to root library

Recurring demand patterns may be proposed back to `keyword-root-library`; selection never silently edits the canonical root asset.
