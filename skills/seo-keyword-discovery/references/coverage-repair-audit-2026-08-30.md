# Discovery Coverage Repair — Initial State Audit

Date: 2026-08-30

Repository: `https://github.com/pyxm1618/SEO-Skills`

Source branch: `codex/seo-a-plus-scope-correction`

Locked source SHA: `8b3a226327fe160ddec19a51ac47ba309897ff32`

Repair worktree: `/Users/milushangdi/Downloads/SEO-Skills-keyword-discovery-repair`

Runtime baseline: Python 3.14.3 (`/opt/homebrew/bin/python3`), pytest 9.0.2

Baseline: `python3 -m pytest -q` → `203 passed in 4.89s`

## Scope and source lock

The remote source branch was checked with `git ls-remote` before worktree creation and exactly matched the locked SHA. The current user checkout was two local commits ahead of that SHA and contained an unrelated `.gitignore` modification, so this repair worktree was created directly from the locked commit. The current checkout and `.gitignore` are outside this repair.

The repository has no additional `AGENTS.md` below the repository parent. The reviewed project controls are the Discovery/Selection documents, runtime contracts, collectors, evidence binding, and Codex hook configuration.

## Prompt assumptions versus code facts

### 1. Current formal Discovery completion condition

**Prompt assumption:** Google completeness is currently being treated as formal Discovery completion.

**Actual code:** `runtime/stage_contracts.json` defines `discovery_handoff` with only `batch_id`, `required_seed_count`, `autocomplete_pass_count`, and `status=PASS`, plus equality of the two Google counts. `runtime/codex_stage_hook.py` treats only `discovery_autocomplete` and `discovery_handoff` as traditional shared stages. No coverage ledger or final coverage validator exists.

**Conclusion:** CONFIRMED. A Google-only count can authorize a handoff; source truth and workflow coverage are not separate gates.

### 2. Google mandatory behavior

**Prompt assumption:** Every required Seed must use real Google Autocomplete and fail closed.

**Actual code:** `skills/seo-keyword-discovery/SKILL.md`, `references/discovery-sop.md`, and `runtime/stage_contracts.json` require `google_autocomplete`, at least one suggestion, and the current evidence binding. `runtime/collectors/google_live_collector.py` requires `SEO_BROWSER_CDP_URL`, a Google origin, a visible search input, a visible non-empty dropdown, and screenshot/structured observation artifacts. There is no WebSearch/Bing fallback.

**Conclusion:** CONFIRMED and preserved. The repair must add a separate coverage gate, not weaken this Collector or its evidence binding.

### 3. Semrush `when used`

**Prompt assumption:** The default route can run Google then skip Semrush and still hand off.

**Actual code:** `SKILL.md` and `discovery-sop.md` say Semrush Ideas/Related is used `when used`; the `discovery_handoff` contract has no Semrush requirement; the hook does not include `discovery_semrush_ideas` in the traditional shared stages.

**Conclusion:** CONFIRMED. Default Full Traditional Discovery needs an explicit Semrush requirement. A diagnostic Google-only route, if retained, must not produce formal COMPLETE handoff.

### 4. Competitor organic role and runtime path

**Prompt assumption:** Competitor organic keywords were reduced to an optional supporting source and may have lost a real path.

**Actual code:** `skills/seo-keyword-selection/references/data-contracts.md` mentions competitor organic keywords only as a possible source label. `runtime/collectors/semrush_relay_collector.py` supports only `ideas` and `exact`; `runtime/evidence_binding.py` has no competitor evidence type; no stage contract or hook path records competitor coverage.

**Conclusion:** CONFIRMED. Add one Semrush relay-only `competitor_organic` normalization mode by reusing the existing generic same-origin relay, and make it mandatory only when competitor domains are explicitly configured.

### 5. Branch expansion

**Prompt assumption:** The current Discovery is approximately one layer and lacks controlled demand-branch expansion.

**Actual code:** There is no branch ledger, branch seed API, branch provenance contract, queue, depth/budget guard, or branch-related stage/handoff logic in the repository. The only Discovery runtime files are the two source collectors, stage validator, evidence binding, and hook.

**Conclusion:** CONFIRMED. Add a small ledger/validator with observed-candidate provenance, visited/cycle checks, configurable depth and branch-count safety limits, and mandatory second-round Google + Semrush status for declared required branches. Do not implement a general crawler or BFS engine.

### 6. Google Related / PAA

**Prompt assumption:** Related/PAA may be available as real supplementary sources.

**Actual code:** `google_live_collector.py` supports only `autocomplete`, `intitle`, `serp`, and `trends`. There is no Related/PAA parser or stage contract.

**Conclusion:** NOT CONFIRMED as an existing capability. They remain documented as optional future/supplementary sources and are not expanded in this repair.

### 7. Existing old Step 0–4 ownership

**Prompt assumption:** Former Selection Steps 0–4 are now Discovery-owned.

**Actual code:** `seo-keyword-selection/SKILL.md` and `references/selection-sop.md` explicitly state that former Steps 0–4 belong to Discovery, while Selection starts at former Step 5. No pre-split executable Step 0–4 implementation remains in Selection.

**Conclusion:** The ownership split is already correct. Documentation will clarify the frozen business flow without moving or redesigning Selection.

### 8. Selection decision logic

**Prompt assumption:** Selection thresholds and opportunity decisions must remain unchanged.

**Actual code:** Selection thresholds are byte-frozen by `tests/test_execution_integrity.py`; `evaluate_candidates.py` owns the existing Ideas/Exact/KGR/SERP/KDRoi calculations. No Selection source change is required.

**Conclusion:** PRESERVE. The repair will not alter thresholds, evaluator formulas, clustering, or human decision semantics.

### 9. Evidence and provider policy

**Prompt assumption:** Google must remain real-browser evidence and Semrush must remain current authenticated same-origin relay-only.

**Actual code:** `evidence_binding.py`, `stage_validator.py`, `semrush_relay_collector.py`, source-policy tests, and `runtime/TRUST_BOUNDARY.md` enforce collector identity, raw/normalized replay, artifact hashes, current capture freshness, `sem.3ue.com`, and no provider/API fallback.

**Conclusion:** PRESERVE and extend only the existing Semrush relay/evidence pattern to the competitor mode. No new provider abstraction or fallback is allowed.

### 10. Handoff and Hook protection

**Prompt assumption:** The final handoff and Stop/PreToolUse hooks must enforce the new coverage result.

**Actual code:** `stage_validator.py` issues receipts for production stage reports; `codex_stage_hook.py` validates current evidence and canonical candidate lifecycle. Its protected `stage_validator.py --stage discovery_handoff` rule currently requires only `discovery_autocomplete`, and its traditional route list omits Semrush and any coverage record.

**Conclusion:** CONFIRMED gap. Add `discovery_coverage` as a canonical shared stage, require it before handoff/COMPLETE, and bind the handoff payload to the verified coverage validation receipt.

### 11. Runtime/orchestration boundary

**Prompt assumption:** Existing Collector/Stage Contract/Validator/Hook architecture should be reused.

**Actual code:** There is no application workflow engine or long-term Discovery database in this source tree. The smallest complete implementation is a pure run ledger/coverage validator plus Collector/evidence/stage/hook integration. It will not invent persistence or orchestration infrastructure.

**Conclusion:** CONFIRMED. The ledger is an auditable run artifact, not a new database or generic workflow framework.

### 12. Documents and tests

**Prompt assumption:** The Discovery docs currently describe a Google-only/when-used route and need synchronization.

**Actual code:** `SKILL.md`, `discovery-sop.md`, and `data-contracts.md` describe required Google but optional Semrush and only Google-count handoff. README describes the same general boundary and source policy but has no Coverage Contract.

**Conclusion:** CONFIRMED. Update the affected Discovery docs, README architecture/workflow text, stage contract documentation, and add focused tests while preserving existing regression tests.

## Initial audit verdict

The repair is warranted, but it is bounded:

1. Keep the current real Google Autocomplete contract and evidence binding.
2. Make Semrush Ideas/Related required for the default Full Traditional route; preserve partial Google evidence when Semrush is blocked.
3. Add one final `discovery_coverage` ledger/validator with explicit counts, blockers, branch records, and competitor state.
4. Add a Semrush relay-only competitor organic mode using current request descriptors; no endpoint or provider fallback.
5. Add observed-candidate-only branch promotion with simple configurable safety limits; no recursive keyword crawler.
6. Require verified coverage before a formal `discovery_handoff` and traditional COMPLETE.
7. Leave `keyword-root-library`, Selection thresholds/decisions, Emerging Monitor, Mapping, and the existing A+ evidence boundary unchanged.

Live source outcomes will be reported separately from deterministic contract tests. No fixture or mock result will be called Live PASS.
