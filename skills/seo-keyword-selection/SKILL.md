---
name: seo-keyword-selection
description: Use when concrete keyword candidates need evidence-based screening, qualification, opportunity clustering, or human decision support.
---

# SEO Keyword Selection

Run the existing evidence-based selection method from concrete candidates onward. Resume from the earliest unfinished contract and reuse compatible fresh evidence.

## Boundaries

This skill starts at the former Step 5 / Ideas-stage wide recall. Seed generation, Google Autocomplete discovery, Semrush Ideas/Related discovery, and low-risk discovery cleaning belong to `seo-keyword-discovery`.

Inputs are either a verified `seo-keyword-discovery` handoff or a confirmed Emerging `selection_handoff`. Confirmed `emerging`/`breakout` keywords do not return through Seed/Autocomplete/Ideas discovery.

This skill does not own Root generation, Emerging classification/state transitions, or page mapping. The existing evaluator and `references/thresholds.json` remain the calculation/threshold source of truth.

Read:

- `references/selection-sop.md`
- `references/data-contracts.md`
- `references/decision-rules.md`
- `references/thresholds.json`
- `references/source-acquisition.md`
- `runtime/BROWSER_RUNTIME_CONTRACT.md` — shared headful-background Chrome/CDP lifecycle and `NEEDS_HUMAN` contract for all formal Google collection.

## Production execution

Use one active manifest and one literal `SEO_CANDIDATE_ID` for each candidate. Stage 6 Exact must pass before later production evaluation. KGR requires project-collected Google `intitle:"keyword"` evidence. SERP review remains optional; missing SERP does not block a candidate, and KD 40–50 remains `observe_serp` unless verified weak-position evidence supports upgrade. Serious finalists require the existing Google Trends cross-check.

Whenever this skill invokes the shared Google live collector, follow `runtime/BROWSER_RUNTIME_CONTRACT.md`: use the dedicated Google profile/CDP endpoint, keep Chrome headful but background, reuse the worker page, preserve unresolved blocker tabs, and treat `NEEDS_HUMAN` as a stop signal rather than skipping ahead. Do not substitute headless or direct HTTP acquisition to avoid the browser contract.

Current Semrush acquisition remains the authenticated same-origin `sem.3ue.com` path only. Do not add provider fallbacks.

Do not change `pending_metrics`, KGR, SERP, KDRoi, or mechanical-status logic merely to satisfy delivery.

## Unified keyword library

Formal final Selection must field-level upsert its canonical final rows to `SEO关键词库 / 关键词库` through `runtime/keyword_library_sheet.py` and pass readback verification. The standalone evaluator keeps `--sheet-output` opt-in for tests/diagnostics, but normal production Skill execution must perform delivery itself; the user is not expected to remember that flag.

Stable identity is `normalized_keyword + market + language`. Identity context resolves record → run/batch → explicit delivery context → otherwise `BLOCKED`; never default to `US/en`.

Selection owns its metric/calculation fields and hidden `selection_mechanical_status`. It must preserve Discovery provenance, Emerging temporal fields, and the human `状态`. Human status is only `新发现 / 已选 / 已建站 / 放弃`; a new row may initialize `新发现`, but mechanical results never become human decisions.

## Completion

Preserve all blocked reasons and optional-SERP absence truthfully. `do_candidate` is not an automatic final choice.

A formal final Selection is complete only when required evidence/evaluation is complete **and** every final stable row has been successfully written to and read back from the unified keyword library. If Sheet delivery is skipped or fails, keep the evidence/calculations but report the workflow as incompletely delivered.
