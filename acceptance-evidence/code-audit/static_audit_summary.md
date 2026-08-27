# Static Code Audit Report

- **TARGET_SHA**: `d00957e4fd7df1f4e135471e50427448c04ef01b`
- **Audit Date**: 2026-08-27
- **Auditor**: Independent Final Acceptance Engineer

## 17 项核心机制静态审计结果

| # | 审计项目 | 目标要求 | 代码实现位置与机制说明 | 审计结论 |
|---|---|---|---|---|
| 1 | Receipt Schema 版本 | 当前必须为 v2 | `runtime/evidence_binding.py:17`: `SCHEMA = "seo-observed-evidence/v2"` | **PASS** |
| 2 | Receipt Writer 直接调用限制 | 普通 helper 不能直接调用 | `runtime/evidence_binding.py:87-98`: `_assert_real_collector_caller` 检查栈帧 | **PASS** |
| 3 | Receipt Writer CLI 调用路径要求 | 要求真实 Collector CLI (`__main__`) 执行路径 | `runtime/evidence_binding.py:93`: `caller_path != expected or caller_module != "__main__"` 抛出 `EvidenceIntegrityError` | **PASS** |
| 4 | Semrush Artifact Roles 完整性 | 必须包含 `relay_raw_response` 与 `current_network_capture` | `runtime/evidence_binding.py:36-37`: `REQUIRED_ARTIFACT_ROLES["semrush_ideas"]` / `["semrush_exact"]` | **PASS** |
| 5 | Google Autocomplete/Intitle/SERP Roles | 必须包含 `screenshot` 与 `structured_observation` | `runtime/evidence_binding.py:38-40`: `{"screenshot", "structured_observation"}` | **PASS** |
| 6 | Google Trends Roles | 必须包含 `temporal_payload` 与 `screenshot` | `runtime/evidence_binding.py:41`: `{"temporal_payload", "screenshot"}` | **PASS** |
| 7 | Semrush Deterministic Replay | 必须根据 raw response 重新 normalize | `runtime/evidence_binding.py:203-207`: 动态加载 collector 并调用 `collector._normalize(raw["response"], ...)` | **PASS** |
| 8 | Semrush Replay Mismatch 防御 | normalized 与 raw replay 不一致必须失败 | `runtime/evidence_binding.py:210-211`: `if replayed != _without_receipt(normalized): raise EvidenceIntegrityError` | **PASS** |
| 9 | Google Structured Mismatch 防御 | structured observation 与 normalized 不一致必须失败 | `runtime/evidence_binding.py:254-274`: 逐字段比对 query, intitle_results, suggestions, results 等 | **PASS** |
| 10 | Trends Temporal Replay 防御 | Trends timeline 必须从 temporal payload 重放 | `runtime/evidence_binding.py:224-228`: 动态执行 `collector.parse_trends_timeline(raw.get("payload"))` 并核对 series | **PASS** |
| 11 | Stage Validator Production Mode | production mode 强制验证 evidence chain 与 receipt | `runtime/stage_validator.py:110-124`: `_validate_production_binding` 触发 binding 验证 | **PASS** |
| 12 | Hook 每次 Downstream 重新核查 Evidence | downstream 前重新核查底层 evidence | `runtime/codex_stage_hook.py:189-192`: `_verify_validation_receipt` 调用 `_verify_current_evidence(report, stage)` 动态重验底层文件 | **PASS** |
| 13 | Protected Command Marker 优先级 | 自动推断 Stage 不能被 `SEO_STAGE_REQUIRE` marker 覆盖 | `runtime/codex_stage_hook.py:111-116`: `return protected_stage or explicit_stage, candidate_id`，marker 仅在无 protected 匹配时生效 | **PASS** |
| 14 | Fake Completion Stage 防御 | completion requirement 不能使用非 canonical stage | `runtime/codex_stage_hook.py:213-214`: `if stage not in CANONICAL_STAGES: return False, ...` | **PASS** |
| 15 | Traditional Route 最低 Stage 校验 | Traditional COMPLETE 必须包含 `discovery_autocomplete` 与 `stage6_exact` | `runtime/codex_stage_hook.py:46`: `frozenset({"discovery_autocomplete", "stage6_exact"})` | **PASS** |
| 16 | Emerging Route 最低 Stage 校验 | Emerging COMPLETE 必须包含 `stage6_exact` | `runtime/codex_stage_hook.py:47`: `frozenset({"stage6_exact"})` | **PASS** |
| 17 | Bare PASS / Bare COMPLETE 防御 | bare PASS / bare COMPLETE 必须被拒绝 | `runtime/codex_stage_hook.py:155, 198-199`: 缺少 receipt 或 completion_requirements 时直接 DENY | **PASS** |
