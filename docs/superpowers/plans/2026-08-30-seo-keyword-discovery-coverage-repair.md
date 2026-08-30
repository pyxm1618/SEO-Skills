# SEO Keyword Discovery Coverage Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a verifiable Full Traditional Discovery Coverage Contract without changing Selection decisions, Emerging behavior, or real-source evidence rules.

**Architecture:** Reuse the existing stage validator, evidence binding, Semrush same-origin relay, and Codex hook. Add one focused `runtime/discovery_coverage.py` ledger/validator that computes counts and blockers, requires every configured mandatory acquisition to remain in the ledger, and only promotes branch seeds from observed candidates. Add one `competitor_organic` mode to the existing Semrush relay collector and bind its raw/normalized evidence through the existing receipt system.

**Tech Stack:** Python 3.14 runtime, pytest, JSON stage contracts, Markdown skill documentation, existing Playwright/CDP collectors.

**Spec:** `skills/seo-keyword-discovery/references/coverage-repair-audit-2026-08-30.md` and the user-provided Discovery Coverage Contract.

## Global Constraints

- Default Full Traditional Discovery requires real Google Autocomplete for every required Seed and real Semrush Ideas/Related acquisition for every required Seed and required Branch Seed.
- Google acquisition remains a real browser/CDP Google collector and fails closed on CAPTCHA, unavailable DOM, zero suggestions, network failure, or missing evidence.
- Semrush acquisition remains current authenticated same-origin `https://sem.3ue.com/` relay-only, with a current request descriptor, raw response evidence, normalization, provenance, and no API/provider fallback.
- A mandatory failure remains visible as `BLOCKED`/`NOT_RUN` with a reason; it cannot be removed to make counts pass.
- A Branch Seed must be an existing observed candidate with matching evidence provenance; AI analysis can explain promotion but cannot manufacture the keyword.
- Competitor organic is mandatory only when explicit competitor domains are configured; no domains means `not_configured`, not fake PASS.
- `seo-keyword-selection` thresholds, formulas, opportunity rules, `emerging-keyword-monitor`, `seo-page-keyword-mapping`, and the canonical root library are out of scope.
- No provider framework, workflow engine, long-term database, graph crawler, embedding service, or Emerging Radar logic.
- Preserve unrelated worktree files and stage only task files. Do not modify the user's original checkout, `.gitignore`, historical evidence, secrets, or active runs.

---

### Task 1: Add failing Coverage Contract and branch-ledger tests

**Files:**
- Create: `tests/test_discovery_coverage.py`
- Create: `tests/test_semrush_competitor_discovery.py`

**Interfaces:**
- The tests define the minimal public functions `discovery_coverage.summarize_coverage`, `discovery_coverage.add_required_branch_seed`, and `discovery_coverage.validate_coverage`.
- The tests define `semrush_relay_collector.normalize_competitor_organic` and the `competitor_organic` descriptor mode.

- [ ] **Step 1: Write the failing tests**

Cover these exact behaviors: Full happy path; missing Google; missing Semrush without silent fallback; observed-only branch promotion; cross-candidate provenance rejection; incomplete required branch; duplicate/cycle and configurable branch budget; competitor not configured; configured competitor failure; and Semrush competitor normalization with relay-only identity. Include an assertion that an unsupported official/API/provider source descriptor is rejected by the source-policy boundary.

- [ ] **Step 2: Run the focused tests to verify RED**

Run: `python3 -m pytest tests/test_discovery_coverage.py tests/test_semrush_competitor_discovery.py -q`

Expected: collection/import failures because the new coverage module and competitor mode do not yet exist; no production implementation is written before this RED result.

- [ ] **Step 3: Commit the RED tests**

Run: `git add tests/test_discovery_coverage.py tests/test_semrush_competitor_discovery.py && git commit -m "test: define discovery coverage and competitor contracts"`

### Task 2: Implement the coverage ledger and branch provenance rules

**Files:**
- Create: `runtime/discovery_coverage.py`
- Modify: `runtime/stage_validator.py`
- Modify: `runtime/stage_contracts.json`

**Interfaces:**
- `summarize_coverage(ledger, production=False) -> dict` returns computed counts, `coverage_status`, `blocked_reasons`, and `formal_handoff_allowed` without deleting ledger entries.
- `add_required_branch_seed(ledger, originating_candidate_id, parent_seed, branch_reason, depth=1, branch_seed=None) -> dict` derives the branch keyword from the observed candidate and rejects a missing/mismatched candidate or evidence reference.
- `validate_coverage(ledger, production=False) -> list[str]` returns specific structural, provenance, completeness, or source-verification errors.
- `stage_validator.py` enriches `discovery_coverage` reports with the computed summary and validates coverage in production mode before issuing a PASS receipt.

- [ ] **Step 1: Implement the smallest ledger summary and status checks**

Use explicit `required_seeds`, `required_branch_seeds`, `competitor_sweep`, `other_mandatory_sources`, `max_branch_depth`, and `max_branch_seeds` fields. Count required entries from the ledger itself; require PASS statuses and receipt references for mandatory Google/Semrush acquisitions; preserve all non-PASS records and reasons. Default missing route mode to `full`; any non-full diagnostic record cannot be `formal_handoff_allowed=true`.

- [ ] **Step 2: Implement observed-only branch promotion and safety checks**

Require `originating_candidate_id` to resolve to an observed candidate, require the promoted branch keyword to equal that candidate's normalized keyword, require matching evidence reference/source, reject cycles/duplicates, and enforce configured depth/count limits. Do not create or rewrite candidate strings.

- [ ] **Step 3: Integrate the coverage stage with the validator**

Add a `discovery_coverage` contract and a `discovery_handoff` requirement for `coverage_status=PASS` plus `coverage_receipt_ref`. Make the validator compute the coverage summary, retain the original ledger in blocked reports, and issue a validation receipt only for a PASS coverage record.

- [ ] **Step 4: Run focused coverage tests and full tests**

Run: `python3 -m pytest tests/test_discovery_coverage.py -q` and then `python3 -m pytest -q`.

Expected: all new coverage tests pass and any existing failures are fixed without weakening their assertions.

- [ ] **Step 5: Commit the coverage implementation**

Run: `git add runtime/discovery_coverage.py runtime/stage_validator.py runtime/stage_contracts.json tests/test_discovery_coverage.py && git commit -m "feat: add discovery coverage contract"`

### Task 3: Add competitor organic through the existing Semrush relay

**Files:**
- Modify: `runtime/collectors/semrush_relay_collector.py`
- Modify: `runtime/evidence_binding.py`
- Modify: `tests/test_semrush_competitor_discovery.py`

**Interfaces:**
- `load_request` accepts `mode=competitor_organic` with a non-empty `competitor_domain` and `metric_database=us`.
- `normalize_competitor_organic(data, descriptor, observed_at, raw_evidence_ref=None) -> dict` returns `competitor_domain`, observed keyword `rows`, `metric_source=Semrush`, `metric_stage=competitor_organic`, `relay_origin`, and `provenance_ref`.
- Evidence type `semrush_competitor_organic` uses the existing raw relay/current network capture artifact roles and deterministic replay.

- [ ] **Step 1: Extend the collector minimally**

Add the mode/identity field, parse only the observed competitor keyword response shape, preserve optional returned metrics without estimating missing values, and write `competitor_domain` into raw evidence. Keep the current origin, credentials, capture freshness, response checks, and no-hardcoded-endpoint behavior.

- [ ] **Step 2: Extend evidence binding and stage contract coverage**

Register the new evidence type with the same Semrush collector and raw/capture artifact roles. Replay the competitor normalizer from raw response and require exact normalized equality. Add the `discovery_semrush_competitor_organic` stage contract with the exact relay host/source/stage fields.

- [ ] **Step 3: Run competitor and regression tests**

Run: `python3 -m pytest tests/test_semrush_competitor_discovery.py tests/test_observed_evidence_binding.py tests/test_semrush_source_policy.py -q`.

Expected: competitor normalizer and authenticity tests pass; existing Semrush receipt/source-policy tests remain green.

- [ ] **Step 4: Commit the competitor implementation**

Run: `git add runtime/collectors/semrush_relay_collector.py runtime/evidence_binding.py tests/test_semrush_competitor_discovery.py && git commit -m "feat: add relay-only competitor keyword discovery"`

### Task 4: Enforce coverage before formal handoff and synchronize documentation

**Files:**
- Modify: `runtime/codex_stage_hook.py`
- Modify: `tests/test_codex_stage_hooks.py`
- Modify: `tests/test_hook_requirement_integrity.py`
- Modify: `tests/test_post_validation_integrity.py`
- Modify: `tests/test_scope_correction.py`
- Modify: `tests/test_integrity_boundary_regressions.py`
- Modify: `tests/test_a_plus_architecture.py`
- Modify: `skills/seo-keyword-discovery/SKILL.md`
- Modify: `skills/seo-keyword-discovery/references/discovery-sop.md`
- Modify: `skills/seo-keyword-discovery/references/data-contracts.md`
- Modify: `skills/seo-keyword-discovery/references/source-acquisition.md`
- Modify: `README.md`
- Modify: `runtime/TRUST_BOUNDARY.md`

**Interfaces:**
- Traditional canonical shared stages become `discovery_autocomplete`, `discovery_coverage`, and `discovery_handoff`.
- A protected handoff command requires a verified `discovery_coverage` receipt.
- A production handoff report must point to the exact verified coverage receipt and PASS summary.

- [ ] **Step 1: Add failing hook tests for missing/blocked coverage**

Assert that Google PASS + Semrush BLOCKED, required branch BLOCKED, configured competitor BLOCKED, missing coverage receipt, and mismatched coverage receipt all deny formal handoff/COMPLETE; assert that `not_configured` competitor coverage does not block the route when no domains are supplied.

- [ ] **Step 2: Run the new hook tests to verify RED**

Run: `python3 -m pytest tests/test_discovery_coverage.py tests/test_codex_stage_hooks.py tests/test_hook_requirement_integrity.py -q`

Expected: new handoff assertions fail against the old autocomplete-only hook.

- [ ] **Step 3: Implement the hook gate**

Add canonical coverage handling, verify the current coverage receipt/report/evidence, require it in the traditional route, and bind `discovery_handoff` to the coverage receipt. Keep Emerging route attestation, candidate-specific Selection lifecycle checks, and existing Stop/PreToolUse semantics unchanged.

- [ ] **Step 4: Update the Discovery and architecture docs**

Describe Full Traditional Discovery as Google + Semrush per required Seed, optional configured competitor sweep, observed-only branch expansion, one final Coverage Contract, blocked-evidence preservation, and explicit non-goals. State that Related/PAA remain absent supplementary collectors in this repair and Selection remains unchanged.

- [ ] **Step 5: Run focused hook/docs tests and commit**

Run: `python3 -m pytest tests/test_discovery_coverage.py tests/test_semrush_competitor_discovery.py tests/test_codex_stage_hooks.py tests/test_hook_requirement_integrity.py tests/test_post_validation_integrity.py tests/test_scope_correction.py tests/test_integrity_boundary_regressions.py tests/test_a_plus_architecture.py -q`

Commit: `git add runtime/codex_stage_hook.py tests skills/seo-keyword-discovery README.md runtime/TRUST_BOUNDARY.md && git commit -m "fix: gate discovery handoff on full coverage"`

### Task 5: Full verification and live acceptance attempt

**Files:**
- No new implementation files; inspect only generated test/acceptance artifacts under a fresh ignored `.seo-run` run directory.

- [ ] **Step 1: Run required repository verification**

Run: `python3 -m pytest -q`, `python3 -m compileall -q skills runtime`, and `git diff --check`.

- [ ] **Step 2: Inspect final diff and immutable Selection boundary**

Confirm only task files changed, `thresholds.json` bytes are unchanged, no provider/API/fallback token or Emerging logic was introduced, and the repair worktree has no unrelated modifications.

- [ ] **Step 3: Attempt real Google Autocomplete**

Use the existing visible browser/CDP route and current Google UI for a small real Seed. Record PASS only if the current dropdown and evidence receipt are actually produced; record BLOCKED for missing CDP, CAPTCHA, unavailable DOM, or other external blocker.

- [ ] **Step 4: Attempt current Semrush Ideas/Related and competitor relay**

Use only current authenticated `sem.3ue.com` UI/session captures and request descriptors. If the session or current capture is unavailable, record BLOCKED and preserve any Google evidence. Do not use fixture/API/provider fallback. Competitor remains `not_configured` unless a real, traceable competitor domain is already configured.

- [ ] **Step 5: Attempt branch expansion with a real observed candidate**

Only if Google/Semrush produce a current observed candidate, promote that exact keyword and run the second round through the same real collectors. Otherwise record BLOCKED/DEFERRED with the missing prerequisite; never mint a branch keyword.

- [ ] **Step 6: Commit final verification evidence and report**

Run `git status --short --branch`, `git log --oneline --decorate -8`, and record exact counts, live statuses, and remaining blockers in the final report. Do not call mocks or fixtures Live PASS.

### Task 6: Publish the isolated repair for independent review

**Files:**
- No source changes; Git remote/PR metadata only.

- [ ] **Step 1: Verify final source and branch ancestry**

Confirm repair branch remains based on `8b3a226327fe160ddec19a51ac47ba309897ff32` and does not modify `main` or `codex/seo-a-plus-scope-correction`.

- [ ] **Step 2: Push the repair branch**

Run: `git push -u origin codex/seo-keyword-discovery-coverage-repair`.

- [ ] **Step 3: Create a Draft PR against the source branch**

Use the repository forge tooling with title `Repair: strengthen traditional keyword discovery coverage`; base must be `codex/seo-a-plus-scope-correction`, head must be `codex/seo-keyword-discovery-coverage-repair`, and the body must include source lock, audit verdict, coverage contract, Semrush route, competitor/branch behavior, tests, live statuses, limitations, and non-goals.

- [ ] **Step 4: Stop without merge or deployment**

Leave the repair worktree and branch available for independent review. Do not merge, deploy, force-push, or modify the source branch.
