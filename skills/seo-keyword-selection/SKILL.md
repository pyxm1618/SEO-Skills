---
name: seo-keyword-selection
description: Use when concrete keyword candidates need evidence-based screening, qualification, opportunity clustering, or human decision support.
---

# SEO Keyword Selection

Run the SEO opportunity-selection method from concrete candidates onward. Resume from the earliest unfinished contract and do not redo compatible fresh evidence.

## Boundaries

This skill starts at the former Step 5 / Ideas-stage wide recall. Seed generation, Google Autocomplete discovery, Semrush Ideas/Related discovery, and low-risk discovery cleaning belong to `seo-keyword-discovery`.

Inputs may come from:

- a valid `seo-keyword-discovery` handoff; or
- confirmed `emerging`/`breakout` `selection_handoff` directly from `emerging-keyword-monitor`.

Confirmed emerging keywords never route back through Seed/Autocomplete/Ideas discovery. Reuse compatible fresh evidence and acquire only the earliest missing selection contract.

Read before execution:

- `references/selection-sop.md`
- `references/data-contracts.md`
- `references/decision-rules.md`
- `references/thresholds.json` — unchanged source of truth.
- `references/source-acquisition.md`

## Production candidate start

The `traditional` run must already have its active manifest and completed
global discovery stages. Add a concrete candidate with a canonical keyword,
then use the same literal candidate ID in the manifest, validator argument,
and protected command environment:

```bash
export SEO_RUN_MANIFEST=.seo-run/active.json
export SEO_CANDIDATE_ID=cand_wedding_cost_calculator
python3 -c 'import json, os; from pathlib import Path; p=Path(os.environ["SEO_RUN_MANIFEST"]); m=json.loads(p.read_text()); m.setdefault("candidates", {})[os.environ["SEO_CANDIDATE_ID"]]={"keyword":"wedding cost calculator"}; p.write_text(json.dumps(m, ensure_ascii=False, indent=2)+"\n")'
python3 runtime/stage_validator.py \
  --stage stage6_exact --candidate-id "$SEO_CANDIDATE_ID" --production \
  --input .seo-run/evidence/exact-wedding-cost-calculator.json \
  --report .seo-run/validation/cand-wedding-cost-calculator-exact.json
```

The production validator derives `candidate_keyword` from exactly one
complete row and writes it to the report and receipt. Record that receipt's
`validation_receipt_ref` under the same candidate's `stage6_exact` record;
repeat the identity-bound pattern for `intitle_observation`, `kgr_intitle`,
optional `serp_review`, and conditional `finalist_trend`. Use the same literal
`SEO_CANDIDATE_ID=<id>` prefix for protected collector/evaluator commands.
Missing markers, duplicate or missing complete rows, receipt mounting under a
different candidate, and keyword mismatches fail closed. Shared discovery
receipts stay global and cannot contain candidate identity.

## Execution integrity

The existing evaluator remains the calculator/classifier. Do not change its treatment of `pending_metrics`, KGR, SERP weak evidence, or KDRoi merely to enforce production completeness.

Production decisions are separately gated:

- Stage 6 Exact must pass the machine-readable `stage6_exact` contract before Stage 7+ production evaluation for that candidate.
- KGR requires project-collected real Google `intitle:"keyword"` evidence; KGR itself remains calculated by the evaluator.
- SERP review is optional. Missing or unavailable SERP does not block the candidate or batch; KD 40–50 remains `observe_serp`. Upgrade requires a candidate-bound receipt, matching Top-10 rank/URL, KGR pass, and at least two weak positions.
- Serious finalists require real Google Trends cross-check. Keyword Planner remains optional.

New/current Semrush acquisition is only through the authenticated same-origin `sem.3ue.com` collector. No official API or alternative-provider fallback is permitted.

## Unified keyword library delivery

The shared human-facing delivery surface is the existing spreadsheet `SEO关键词库`, worksheet `关键词库`. Selection writes through `runtime/keyword_library_sheet.py` after the canonical final evaluator output exists; it does not calculate metrics inside the Sheet layer.

Selection owns only its delivery fields such as Volume, KD, CPC, KDRoi, Intent, KGR/intitle/SERP evidence, metric provenance, and the hidden `selection_mechanical_status`. It must not overwrite Discovery provenance, Emerging temporal fields, or the human workflow column `状态`.

Stable row identity is `normalized_keyword + market + language`. `market` and `language` must be resolved from an explicit record value, then an explicit run/batch value, then an explicitly configured delivery context; if still absent, delivery is `BLOCKED`. There is no silent `US/en` fallback.

The human workflow column remains exactly `新发现 / 已选 / 已建站 / 放弃`. Only creation of a previously absent stable row may initialize `状态=新发现`. `do_candidate`, `observe_*`, `principle_eliminate_*`, `excluded_manual`, and every other mechanical Selection result stay in the hidden mechanical-status field and never promote or reject the human workflow automatically.

The standalone evaluator CLI keeps `--sheet-output` opt-in so unit tests, diagnostics, and local calculation can run without credentials. That CLI convenience is **not** the production completion rule. When this Skill is executing a formal final Selection workflow, it must perform the unified Sheet upsert and successful readback itself as part of completion; the user must not be required to remember an extra flag. A formal final Selection whose canonical output exists but whose unified Sheet delivery failed, was skipped, or could not resolve stable identity is incomplete delivery.

## Evidence discipline

Keep the existing `observed`, `calculated`, `analysis`, `unknown` meanings. Missing, invalid, numeric zero, and `not_applicable` remain distinct. Never manufacture Volume, KD, CPC, `intitle`, rank/url, DR, or trend observations.

## Completion

Blocked required stages retain their reason; complete candidates may continue. Optional SERP may be omitted or recorded as `serp_review.status=BLOCKED` with a real reason without terminally blocking the candidate. A finished batch exposes complete/blocked counts and preserves the human decision; `do_candidate` is not an automatic final choice.

For a **formal final Selection**, completion additionally requires the canonical final rows to be successfully upserted into `SEO关键词库 / 关键词库` under the correct stable identities and read back successfully. If that delivery does not succeed, Selection may retain all evidence and calculated outputs, but it must not report the formal final workflow as completely delivered.
