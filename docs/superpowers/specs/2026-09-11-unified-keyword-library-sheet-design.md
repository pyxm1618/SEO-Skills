# Unified Keyword Library Sheet Design

## Goal

Unify Google Sheet delivery for `seo-keyword-discovery`, `emerging-keyword-monitor`, and `seo-keyword-selection` into the existing spreadsheet `1aOogxb-zlRpkBT_F1KEO3vTIPDNcw5V88o_L_eWyYCM`, worksheet `关键词库`, without changing SEO acquisition, classification, selection, threshold, Root Library, or Mapping business logic.

## Boundaries

This change is delivery/output plumbing only.

Unchanged:
- Discovery Coverage, Google Autocomplete, PAA/Related, Semrush acquisition.
- Emerging classifier, thresholds, routing, state machine, Root Library behavior.
- Selection thresholds, KGR formula, KDRoi formula, SERP decision logic.
- Root Library canonical storage.
- SEO page keyword mapping.

The Sheet remains one-way human-facing output/delivery, never a source of truth.

## Shared writer

Add `runtime/keyword_library_sheet.py` as the sole owner of the unified Sheet schema and field-level upsert behavior.

Responsibilities:
1. Open the configured spreadsheet and `关键词库` worksheet.
2. Read/validate headers.
3. Resolve a stable keyword identity.
4. Locate exactly one stable row.
5. Patch only fields owned by the calling Skill.
6. Preserve all other fields and any non-empty human workflow status.
7. Read back written fields.
8. Preserve `unknown` as literal `unknown`, never blank/0/false.

The real worksheet currently contains only its legacy 27-column header and no data rows, so schema bootstrap is safe. A non-empty incompatible sheet must fail closed rather than rewrite data.

## Stable identity

Stable key:

`normalized_keyword + market + language`

Normalization reuses the repository's existing whitespace-collapse + `casefold()` semantics.

`domain` is context, not part of the long-lived keyword identity.

Market/language resolution order is strict:
1. explicit record value;
2. explicit run/batch value;
3. explicit delivery context/configuration;
4. otherwise BLOCKED.

No code default of `US/en` is allowed because market/language participate in identity.

The stable key is separate from Discovery candidate identity. Multiple Discovery candidates/sources may resolve to one stable row while every candidate/source/provenance record remains independently verified in the Discovery delivery receipt.

## Sheet schema

Visible user columns, in order:
1. `关键词`
2. `月搜索量`
3. `趋势类型`
4. `出生窗口`
5. `KD`
6. `CPC`
7. `KDRoi`
8. `意图`
9. `状态`

`趋势类型` values are limited to `新词 / 上升 / 平稳 / 下降 / unknown` and may only be derived from existing canonical temporal evidence. Traditional Discovery alone never implies keyword age. If evidence cannot support one of those values, write `unknown`.

`出生窗口` comes only from existing `estimated_birth_window`; `first_observed_at` is not an absolute birth date.

`状态` is human workflow state only: `新发现 / 已选 / 已建站 / 放弃`. It is initialized to `新发现` only when a row is first created. Any non-empty existing status is protected from all Skill writes. Selection mechanical states are stored only in hidden technical columns.

Hidden technical columns preserve identity, source/provenance, Emerging lifecycle/history, Selection metrics/evidence, timestamps, and receipt references. Technical columns are hidden in the real worksheet after bootstrap.

## Field ownership

Discovery may patch identity/display keyword, source/source seed, Root context if present, candidate/batch/provenance references, discovery evidence, and creation-time `状态=新发现`. It cannot patch Emerging or Selection fields or overwrite a non-empty status.

Emerging may patch temporal/newness/birth/history fields and Emerging evidence/status fields. It does not own Volume/KD/CPC/KDRoi in the unified library by default and cannot patch Selection-owned metrics or human status.

Selection may patch Volume, KD, CPC, KGR, KDRoi, intitle/SERP weak evidence, mechanical status, metric/provenance fields, and intent only when an existing real canonical/pass-through intent value exists. It cannot patch Emerging temporal fields or human status.

The shared writer rejects fields outside the caller's ownership set.

## Discovery receipt v2

Upgrade to `seo-discovery-sheet-delivery/v2` and update the production validator/tests together.

The v2 receipt preserves fail-closed semantics while changing readback verification from eight-column whole-row equality to stable-row + Discovery-owned field verification.

Verification rules:
- the complete handoff remains bound by `handoff_binding_sha256`;
- all Discovery candidates remain in the handoff/ledger contract;
- each valid candidate keyword-context must resolve to exactly one stable identity row;
- multiple candidates may resolve to the same stable row;
- every candidate's source/source_seed/evidence provenance must remain represented and verifiable in receipt candidate bindings, even when candidates share one stable row;
- missing stable rows BLOCK;
- duplicate stable rows BLOCK;
- unresolved market/language BLOCK;
- mismatched Discovery-owned readback fields/provenance BLOCK;
- extra Emerging/Selection-owned fields on a row do not create mismatch;
- receipt source hash, sheet id, worksheet, binding hash, candidate counts and stable-row counts are validated by production `discovery_handoff` validation.

## Emerging boundary

Emerging continues to treat JSON/CSV as authoritative. Unified Sheet delivery remains an optional mirror/output layer. Sheet export failure must not invalidate or rewrite a Radar run.

## Selection integration

Selection writes to the unified library only after canonical evaluation output is complete. The Sheet does not participate in metric calculation or SEO decisions. Existing KGR/KDRoi/SERP formulas and thresholds are unchanged.

## Environment

Reuse:
- `SEO_KEYWORD_SHEET_ID`
- `SEO_SHEETS_CREDENTIALS`

Add optional:
- `SEO_KEYWORD_LIBRARY_WORKSHEET`, default `关键词库`.
- explicit delivery context inputs/environment for market/language only when records/run metadata do not provide them; absent identity context blocks rather than guessing.

## Tests and acceptance

Tests must first fail against current implementation, then pass after minimal implementation. They cover creation, repeat upsert, cross-Skill same-row update, field isolation in both directions, human status protection, literal `unknown`, same-market dedupe/different-market split, strict identity context, and Discovery receipt v2 fail-closed behavior including many-candidates-to-one-stable-row provenance verification.

Run targeted Root/Discovery/Selection/Emerging tests, full repository tests, and `compileall`.

Live smoke test uses one controlled keyword through Discovery -> Emerging -> Selection on the real `关键词库`, verifies one row only, verifies all owner fields coexist and manual status is preserved, then removes the test row.
