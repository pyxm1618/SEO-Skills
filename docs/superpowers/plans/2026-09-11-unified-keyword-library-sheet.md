# Unified Keyword Library Sheet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Safely deliver Discovery, Emerging, and Selection data into one long-lived `关键词库` row per normalized keyword/market/language while preserving existing production contracts and business logic.

**Architecture:** A shared `runtime/keyword_library_sheet.py` owns schema, stable identity, field ownership, field-level upsert, and readback. Skill-specific exporters/adapters translate canonical outputs into owner patches. Discovery delivery is upgraded to receipt v2 with candidate-level provenance bindings that may map multiple candidates to one stable row.

**Tech Stack:** Python 3.12, pytest, gspread-compatible worksheet interface, existing runtime validators.

**Spec:** `docs/superpowers/specs/2026-09-11-unified-keyword-library-sheet-design.md`

## Global Constraints

- Delivery/output plumbing only; do not change acquisition, thresholds, formulas, classifiers, Root Library, or Mapping.
- Stable identity is `normalized_keyword + market + language`.
- Market/language resolution is record -> run/batch -> explicit delivery context -> BLOCKED; never guess US/en.
- `unknown` remains literal `unknown`; never blank/0/false.
- Human status is only `新发现 / 已选 / 已建站 / 放弃`, initialized only on row creation and never overwritten by a Skill.
- Discovery remains fail-closed and mandatory; Emerging remains optional mirror; Selection writes only after canonical evaluation.

---

### Task 1: Shared writer contract and tests

**Files:**
- Create: `runtime/keyword_library_sheet.py`
- Create: `tests/test_keyword_library_sheet.py`

**Interfaces:**
- Produces `resolve_identity(record, context=None) -> KeywordIdentity`.
- Produces `upsert_records(client, owner, records, context=None) -> dict`.
- Produces constants for visible/technical headers and owner field sets.

- [ ] Write failing tests for strict market/language context, new-row status initialization, repeat dedupe, different-market split, field-level preservation, manual status protection, and literal unknown.
- [ ] Run `python3 -m pytest tests/test_keyword_library_sheet.py -q` and confirm failure because shared writer does not exist.
- [ ] Implement the minimal writer needed for those tests, including safe empty-sheet/legacy-header bootstrap and fail-closed incompatible non-empty schema behavior.
- [ ] Re-run the test file until green.

### Task 2: Discovery adapter and receipt v2

**Files:**
- Modify: `skills/seo-keyword-discovery/scripts/export_to_sheet.py`
- Modify: `runtime/discovery_sheet_delivery.py`
- Modify: `skills/seo-keyword-discovery/tests/test_discovery_sheet_delivery.py`
- Modify: `tests/test_discovery_sheet_handoff_gate.py`

**Interfaces:**
- Discovery exporter translates handoff candidates to Discovery-owned patches.
- Receipt schema becomes `seo-discovery-sheet-delivery/v2`.
- Receipt records both `candidate_count` and `stable_row_count`, plus candidate bindings to stable keys and source/provenance.

- [ ] Rewrite/add tests first for default worksheet `关键词库`, strict identity context, same-keyword repeated Discovery upsert, multiple candidates resolving to one stable row without losing candidate provenance, missing/duplicate stable rows, Discovery-owned mismatch, and tolerance of other-owner fields.
- [ ] Run the Discovery Sheet tests and confirm red against v1 exporter.
- [ ] Adapt exporter to shared writer and implement stable-row readback verification.
- [ ] Upgrade receipt builder and production verifier to v2 together.
- [ ] Run Discovery targeted tests and gate tests until green.

### Task 3: Emerging adapter

**Files:**
- Modify: `skills/emerging-keyword-monitor/scripts/export_to_sheet.py`
- Modify: `skills/emerging-keyword-monitor/tests/test_export_to_sheet.py`

**Interfaces:**
- Emerging exporter builds only Emerging-owned patches and calls the shared writer.
- CLI failure remains non-authoritative mirror failure only.

- [ ] Add failing tests proving temporal fields patch the existing stable row, Selection metrics survive Emerging writes, trend type is evidence-derived/unknown rather than Discovery-age inference, and missing identity context blocks the export action without mutating Radar outputs.
- [ ] Run Emerging exporter tests and confirm red.
- [ ] Replace independent whole-row schema/upsert logic with the shared writer adapter.
- [ ] Re-run Emerging tests until green.

### Task 4: Selection delivery adapter

**Files:**
- Modify: `skills/seo-keyword-selection/scripts/evaluate_candidates.py`
- Modify: `skills/seo-keyword-selection/tests/test_selection.py`

**Interfaces:**
- After canonical rows are normalized, optional Sheet delivery patches Selection-owned fields using shared writer.
- Metric calculation functions remain unchanged.

- [ ] Add failing tests for Volume/KD/CPC/KDRoi/KGR/mechanical status patching, Emerging-field preservation, human-status preservation, unknown metrics, and intent-only-when-present behavior.
- [ ] Confirm tests fail before implementation.
- [ ] Add the smallest post-evaluation delivery path/CLI options without changing normalize/calculation behavior.
- [ ] Re-run Selection tests until green.

### Task 5: Documentation and contracts

**Files:**
- Modify: `README.md`
- Modify: `skills/seo-keyword-discovery/SKILL.md`
- Modify: `skills/seo-keyword-discovery/references/data-contracts.md`
- Modify: `skills/emerging-keyword-monitor/SKILL.md`
- Modify: `skills/emerging-keyword-monitor/references/data-contracts.md`
- Modify: `skills/seo-keyword-selection/SKILL.md`
- Modify: `skills/seo-keyword-selection/references/data-contracts.md`

- [ ] Update only delivery/output documentation: unified worksheet, field ownership, strict identity context, Discovery receipt v2, Emerging optional semantics, Selection post-evaluation output, and Root/Mapping exclusion.
- [ ] Confirm docs do not state any changed SEO decision rule.

### Task 6: Regression and live acceptance

- [ ] Run `python3 -m pytest skills/keyword-root-library/tests/test_root_library.py -q`.
- [ ] Run Discovery tests including `skills/seo-keyword-discovery/tests` and repository Discovery gate tests.
- [ ] Run `python3 -m pytest skills/seo-keyword-selection/tests/test_selection.py -q`.
- [ ] Run `python3 -m pytest skills/emerging-keyword-monitor/tests -q`.
- [ ] Run `python3 -m pytest -q`.
- [ ] Run `python3 -m compileall -q skills runtime`.
- [ ] On real spreadsheet `1aOogxb-zlRpkBT_F1KEO3vTIPDNcw5V88o_L_eWyYCM`, worksheet `关键词库`, bootstrap the approved schema because the sheet has no data rows.
- [ ] Run controlled Discovery -> Emerging -> Selection writes for one unique test keyword, set manual status to `已选` between writes, read back exactly one stable row, verify all three owners' fields coexist and status remains `已选`.
- [ ] Delete the test row and verify no smoke-test residue remains.
- [ ] Review diff against this plan and scope constraints, then create the PR.
