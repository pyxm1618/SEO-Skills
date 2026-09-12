---
name: emerging-keyword-monitor
description: Use when discovering or monitoring newly forming search demand, breakout queries, or new search expressions over time, including distinguishing net-new demand from breakout growth and routing confirmed emerging signals downstream.
---

# Emerging Keyword Monitor

Detect and maintain evidence for search demand that is newly observed, accelerating, or changing expression. This skill answers **what demand is forming or changing now**. It does not make the final SEO opportunity decision.

## Boundaries

- May consume `root_id` references from `keyword-root-library`; never mutate `root-library.csv`.
- May hand confirmed temporal candidates to `seo-keyword-selection`; never emit Selection's final opportunity verdicts or alter Selection thresholds.
- Emerging owns temporal evidence/classification fields only. It never fabricates or overwrites Selection-owned `Volume`, `KD`, `CPC`, `KDRoi`, `KGR`, SERP metrics, intent, or human workflow status.
- Google Sheets is an optional delivery mirror, not the Emerging source of truth.

Read before execution:

- `references/data-contracts.md`
- `references/source-policy.md`
- `references/classification-rules.md`
- `references/state-machine.md`
- `references/routing-rules.md`
- `references/thresholds.json`
- `runtime/BROWSER_RUNTIME_CONTRACT.md`

## Four independent state axes

Do not collapse these into one field:

1. **Acquisition state** — `data_acquired`, `valid_no_data`, `failed`, `not_attempted`, `not_applicable`.
2. **Verification state** — `verified`, `verified_no_data`, `pending_evidence`, `not_run`.
3. **Demand classification state** — canonical temporal interpretation.
4. **Workflow/delivery state** — routing plus the shared library's human workflow status.

Consequences:

- `failed` is not `noise`.
- `not_attempted` is not zero demand.
- `valid_no_data` is not a failed request and is not proof of zero real searches.
- Missing observations are not permission to classify a candidate.
- A prior confirmed `mature`, `emerging`, etc. state must not be overwritten merely because the current acquisition failed.
- Human workflow `状态=新发现` means only that the row first entered the human workflow. It is **not** proof of `new_signal`, `net_new`, or newly born demand.

## Production start and canonical pipeline

Start the Emerging run before collecting observations:

```bash
export SEO_RUN_MANIFEST=.seo-run/active.json
python3 runtime/start_seo_run.py --route emerging
```

Canonical aggregation, classification, routing, and receipt generation live in `runtime/emerging_pipeline.py`.

```bash
python3 runtime/emerging_pipeline.py \
  --input observations.json \
  --candidate-ledger candidate-ledger.json \
  --as-of 2026-09-12T23:59:59Z \
  --output-dir .seo-run/emerging/20260912T235959Z
```

The established receipt schema remains `seo-emerging-pipeline/v1`; candidate-ledger and reconciliation fields are backward-compatible additions. When a candidate ledger is supplied, the receipt attests the complete identity sets for all candidates in scope, candidates actually classified, candidates routed, and candidates eligible for delivery.

The invariant is:

`delivery_ids ⊆ route_ids = classified_ids ⊆ candidate_ids`.

A run is invalid if candidate identities disappear between these stages or appear outside the ledger. The domain Radar runner must call the canonical pipeline for aggregation/classification/routing; it must not maintain a second independent classifier/router implementation.

## Candidate ledger and reconciliation

Every discovered, supplemental, carried, excluded, unknown, failed, skipped, classified, routed, and delivered candidate must have a stable `candidate_id` in the run ledger.

A candidate with no observations remains in the ledger with an explicit terminal disposition such as `pending_evidence`, `pending_domain_review`, `excluded_out_of_scope`, `valid_no_data`, or `not_attempted_batch_limit`. It is not silently dropped and it is not fed into classification.

`max_total_candidates` is the hard run-scope cap. It covers current discovery, recursive expansion, supplemental candidates, carry-forward records, and overflow bookkeeping. Retry budgets are separate and explicitly bounded.

## Domain admission

Domain admission is a separate gate before formal temporal classification:

- `in_scope`: enough domain evidence exists to enter formal evidence collection/classification.
- `out_of_scope`: evidence supports exclusion.
- `unknown`: relation is ambiguous and needs review; the candidate remains traceable but cannot enter formal classification/delivery.

Generic lexical overlap alone is insufficient. Generic terms such as `finder`, `search`, `tool`, `guide`, or `generator` cannot establish `in_scope` by themselves. Known homonyms/media intents must be explicitly excluded where the domain context makes them unrelated.

The same domain gate applies to Rising discovery, supplemental sources, and carry-forward records. Carry-forward is never a bypass around current domain qualification.

## Live Google Trends evidence

The Radar production Trends path uses `runtime/collectors/google_trends_collector.py`; the generic Google collector remains available for Autocomplete and unrelated callers. The live Google runtime must use the repository's dedicated isolated **logged-out** Chrome/CDP context; if that context cannot be established, fail closed rather than copying/deleting cookies or using a temporary account.

For Trends Related and Timeline:

- response capture must be bound to the current keyword, market, timeframe, and expected request payload;
- an unrelated successful `widgetdata` response must not satisfy the current request;
- raw response evidence must be persisted before screenshot capture;
- the required screenshot has a bounded timeout and at most one retry after the initial attempt;
- screenshot failure after valid raw data returns `acquisition_status=data_acquired`, `verification_status=pending_evidence`, `delivery_eligible=false`;
- raw data surviving a screenshot failure is not promoted to verified production evidence;
- a verified response with no timeline data is `valid_no_data`, distinct from `payload_not_observed` and browser/transport failure.

CAPTCHA, unusual-traffic, verification challenges, or an unresolved browser blocker produce `NEEDS_HUMAN` and exit code 3. `NEEDS_HUMAN` is top-level control flow: stop dependent collection immediately, preserve the blocker/browser state, and require human resolution. Do not switch to headless or direct HTTP to bypass it.

Systemic failures use a bounded circuit breaker. After the configured consecutive-failure limit, later work is ledgered as `not_attempted / collection_circuit_open` instead of continuing a broken batch.

## Evidence discipline

`unknown != 0`.

Never invent Volume, KD, CPC, KDRoi, KGR, `intitle`, SERP facts, timestamps, first-seen dates, trend values, growth, or missing windows.

`first_observed_at` is the first observation in the current evidence system. It is not an absolute keyword birth date.

Google Trends indexes from a different timeframe are independently normalized. `5y`, `12m`, `90d`, `30d`, and `7d` are separate series and must not be concatenated or directly compared arithmetically. Use the long series for history/birth inference, medium series for temporal shape, and recent series for persistence/acceleration.

Google Related/Rising `Breakout` is only observed source metadata and is stored as `google_rising_label`. A source-side Breakout label must not emit `signal_type=breakout` by itself and must not emit `status=emerging` or `status=breakout` by itself. A preliminary source observation may be recorded as a hypothesis such as `possible_breakout`, but hypotheses are not canonical classifications.

If a real search-demand source is unavailable, keep the field unknown. Supply-side page counts, launches, media mentions, articles, or community discussion cannot substitute for missing temporal search-demand evidence.

## Canonical runtime enums

`signal_type` must be one of `net_new`, `breakout`, `emerging_variant`, or `unknown`.

`demand_history_type` must be one of `newly_observed`, `preexisting`, `resurgent`, or `unknown`.

`variant_subtype` must be one of `new_expression`, `typo`, `modifier_shift`, or `unknown`.

`status` must be one of `new_signal`, `watch`, `emerging`, `breakout`, `mature`, `noise`, or `insufficient_evidence`.

`route` must be one of `selection_handoff`, `root_candidate_handoff`, `new_root_watchlist`, `monitor_only`, or `no_handoff`.

Do not invent aliases such as `candidate`, `strong candidate`, `reject`, or `possible emerging` in canonical fields.

A history whose first available buckets already contain sustained demand is `preexisting` with `birth_reason=before_available_history`. In human-facing output this means **“早于可观测窗口”**; it does not mean the system knows the true birth date.

`mature` means established/preexisting demand under the classifier. It must never be displayed as `平稳` unless a future independent rule explicitly proves stability. A safe human-facing label is **“成熟需求”**.

## Historical persistence across runs

`update_emerging_database.py` separates current acquisition health from the last confirmed temporal state.

For a confirmed classification, persist `last_confirmed_status`, `last_confirmed_source_evidence`, and `last_confirmed_at`.

For every run, separately persist `last_run_acquisition_status`, `last_run_acquisition_reason`, and `acquisition_failure_count`.

A current acquisition failure cannot erase or downgrade a prior confirmed status/evidence. Failed acquisition retries are bounded; after the retry budget they move to paused review, not automatically to `noise`, `out_of_scope`, or deletion. Domain `not_applicable`/review states are not counted as browser acquisition failures.

Carry-forward remains lifecycle continuation. It is re-qualified through the domain gate and must not be labelled as a fresh Google Rising discovery unless the current run actually observed it there. Historical `previous_status` and `first_observed_at` must survive the observation/classification round trip.

## Routing discipline

Only `status in {emerging, breakout}` may produce `selection_handoff`.

`new_signal` and `watch` must remain `monitor_only` unless a root-candidate rule explicitly sends them to `new_root_watchlist`; they cannot be promoted to Selection.

`root_candidate_handoff` requires both confirmed temporal evidence and a reviewable root-candidate hypothesis. `mature`, `noise`, and `insufficient_evidence` do not route to Selection automatically.

## Optional shared keyword-library mirror

The authoritative Emerging outputs are local JSON/CSV, canonical classifier/router output, evidence, and receipts. Google Sheets is only a human-facing mirror.

```bash
python scripts/export_to_sheet.py --database .seo-run/emerging-keywords.json --dry-run
python scripts/export_to_sheet.py --database .seo-run/emerging-keywords.json \
  --sheet-id SHEET_ID --credentials ~/.config/seo-sheets/service-account.json \
  --market US --language en
```

Rules:

- `BLOCKED` run => **zero production Sheet reads/writes**.
- Delivery list is not the monitoring database. Only explicit `delivery_eligible=true` records from the current run may be delivered when eligibility metadata is present.
- Unknown/out-of-scope records remain in audit/review artifacts, not silently deleted.
- Emerging must not overwrite Selection-owned metrics or human workflow status.
- Missing commercial metrics remain `unknown`; never fill them from unrelated sources.

Human-facing trend projection is intentionally narrow:

- `net_new` / `newly_observed` → `新词`
- canonical `breakout` → `上升`
- canonical `mature` may display `成熟需求`
- everything else remains `unknown` unless a supported canonical mapping exists

Never infer `上升 / 下降 / 平稳` from the sign of a raw growth number in the delivery layer.

## Interactive output

For every candidate expose enough information to distinguish source health from temporal interpretation. At minimum include:

`keyword | candidate_id | domain_relation | acquisition_status | verification_status | signal_type | status | first_observed_at | estimated_birth_window | growth_rate | persistence | route | delivery_eligible`

Selection metrics such as `volume | kd | cpc | kdroi | kgr` may be shown only when real Selection-owned evidence exists; otherwise use `unknown`.

Separate confirmed `emerging`/`breakout`, monitoring states, domain review, and evidence failures. Do not collapse them into one informal `candidate` bucket.
