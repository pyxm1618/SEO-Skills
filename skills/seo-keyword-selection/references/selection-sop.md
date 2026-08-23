# SEO Keyword Selection SOP

This is the canonical workflow. Discovery is intentionally broad; decision stages become progressively stricter.

## 0. Candidate domains

Build a domain pool from interests, experience, observed markets, and prior wins. Do not use Volume/KD/CPC to eliminate domains before demand discovery.

## 1. Root handoff

Obtain roots from `keyword-root-library`. Prefer relevant `verified`/`active` roots; keep new `candidate` roots separate. Do not duplicate the root asset here.

## 2. Domain × root → Seed

Generate natural demand-entry Seeds. A Seed is a demand starting point, not yet an opportunity keyword. Avoid mechanical root permutations that produce unnatural phrases.

## 3. Expand candidates

Prioritize real search signals: Google Autocomplete/Related/PAA, Semrush ideas/related keywords, and competitor organic keywords. AI may expand long-tail forms from those signals, but AI-generated phrases remain candidates until real data exists.

## 4. Low-risk cleaning

Deduplicate. Remove clear brand/navigation terms and obvious semantic drift. Do not remove a term merely because competition “feels high.” Preserve `domain`, `root`, `parent_seed`, and source provenance.

## 5. Ideas-stage wide recall

Use broad recall thresholds from `decision-rules.md`. This stage minimizes false negatives; it is not the final gate. Rows whose Volume/KD are missing remain `pending_metrics`, not rejected. If their source and semantics are credible, route them to exact lookup when the cost is acceptable or park them explicitly for later review.

## 6. Exact metric retrieval

For recall survivors obtain current US Volume, Semrush KD, CPC, intent, competition level, and 12-month trend from a real source. From this point forward, use the exact/current values for decisions.

## 7. Exact pool + KD band

Classify exact Volume into main/blue-ocean/below-floor pools and KD into do-candidate/observe/principle-eliminate bands. KD 40–50 remains observable, not automatically viable.

## 8. CPC + intent review

Treat CPC ≥ $0.10 as a positive commercial signal, not a universal hard gate. Review actual user intent and best fulfillment form: tool, information, resource, commercial page, interactive experience, etc.

## 9. AI intent / SERP hypothesis

Predict likely SERP shape and page form only to prioritize review work. Label this as analysis. Do not use predicted DR, rankings, or competitor strength as facts.

## 10. Compress manual-review pool

Using observed Volume/KD/CPC/intent plus clear exclusions, reduce the set to roughly 15–30 terms for manual KGR work. This is workload control, not sector elimination.

## 11. Observe `intitle`

Search Google using exactly `intitle:"keyword"` and record the visible result count. If a reliable count is unavailable, store `unknown`. Do not substitute Bing, generic result counts, API row counts, or AI estimates.

## 12. Calculate KGR

Calculate KGR from observed inputs. Use the rule in `decision-rules.md`. Missing numerator or denominator means KGR remains unknown.

## 13. Review real SERP top 10

Inspect actual result types and competitive positions: homepages, inner pages, tools, publishers, UGC, small sites, new sites, page quality, intent fit, freshness, and page-level strength where available. Document weak positions rather than merely assigning a vibe.

KD 40–50 may upgrade only under the weak-position rule in `decision-rules.md`.

## 14. Trend validation

Use Semrush 12-month trend first. For finalists, cross-check Google Trends to identify stable, rising, declining, seasonal, or event-driven demand.

## 15. Optional Keyword Planner cross-check

For roughly 5–10 serious finalists, cross-check search volume in Google Ads Keyword Planner when available. This is a late validation layer, not a requirement for thousands of candidates.

## 16. Calculate KDRoi

Calculate KDRoi only from observed Volume/CPC/KD and only when KD > 0. It is a ranking aid, not a gate or final score.

## 17. Final decision table

Maintain at least:

`keyword | domain | root | parent_seed | volume | kd | cpc | metric_source | metric_database | observed_at | metric_stage | provenance_status | intent | trend | intitle_results | kgr | serp_weak_evidence | serp_weak_points | page_form | kdroi | risk | status | duplicate_warning`

Every numeric field must preserve provenance or be a transparent formula.

## 18. Cluster opportunities

Cluster surviving terms back to `domain × root × parent_seed`. The unit of strategic interest is the density and quality of opportunities in a demand family, not the count of isolated keywords.

## 19. Infer product directions

Translate strong demand clusters into possible product/content architectures. Keywords are demand evidence, not products.

## 20. Human final decision

The human selects 1–3 priorities after considering product advantage, build cost, content ability, SEO resources, monetization, data access, time, interest, and whether a materially better result can be built.

## 21. Calibrate thresholds

After every two completed batches, review the medians/distribution of Volume, KD, CPC, and KGR among human-selected terms. If results consistently sit outside current defaults, revise `decision-rules.md` and tests together. Do not silently drift thresholds during a batch.

## Feedback to root library

After each batch, recurring demand patterns missing from the root asset may be proposed back to `keyword-root-library` as candidates with provenance. This workflow never auto-promotes or silently edits the root library.

### Reliability checks before final decision

Before trusting the final decision table, repair all `invalid_row` records, inspect `provenance_status`, and resolve duplicate warnings. For KD 40–50 terms, SERP weak-position counts must be derived from structured evidence tied to real top-10 results; a bare count is not sufficient. These checks do not change the locked Volume/KD/CPC/KGR thresholds.
