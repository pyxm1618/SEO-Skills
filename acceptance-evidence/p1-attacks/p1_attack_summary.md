# P1 Integrity Attack Matrix (P1-A to P1-Q) Execution Report

- **TARGET_SHA**: `d00957e4fd7df1f4e135471e50427448c04ef01b`
- **Execution Date**: 2026-08-27
- **Total Attacks**: 17
- **Passed**: 17
- **Failed**: 0
- **Overall Verdict**: **ALL PASS (17/17)**

## 逐项攻击结果与证据

| 攻击编号 | 攻击目标与手段 | 预期结果 | 实际执行结果 | 状态 |
|---|---|---|---|---|
| **P1-A** | 手写 observed 数据（volume, kd, cpc 等字段完整）但无 receipt 进行 production 验证 | Production Validator 必须返回 BLOCKED (code=2) | 返回 code=2，status=BLOCKED，错误为 `evidence:evidence receipt is required` | **PASS** |
| **P1-B** | 手写来源字段但无有效 receipt 输入 evaluate_candidates | provenance_status 绝不能为 verified | `provenance_status` 严格判定为 `unverified` | **PASS** |
| **P1-C** | 篡改 normalized 中的 Volume/KD/CPC（未更新 receipt） | Validator 拒绝并报 hash / binding mismatch | 返回 code=2，捕获 `differs from collector-bound normalized evidence` | **PASS** |
| **P1-D** | 篡改 raw response 内容破坏 semantic 绑定 | Validator 语义回放检验失败 | 返回 code=2，捕获 `Semrush raw evidence missing fields` | **PASS** |
| **P1-E** | 验证通过后篡改底层 normalized 文件再次执行下游命令 | PreToolUse Hook 动态重验底层 evidence 失败并 DENY | 初始验证 ALLOW (code=0)，篡改底层文件后 Hook 拦截 DENY (code=2, `underlying evidence invalid`) | **PASS** |
| **P1-F** | Manifest 中伪造 bare PASS（无 validation receipt） | PreToolUse Hook 必须 DENY (code=2) | Hook 返回 code=2，拦截 `PASS lacks validation receipt` | **PASS** |
| **P1-G** | Manifest 中标记 bare COMPLETE（无 completion_requirements） | Stop Hook 必须 DENY (code=2) | Hook 返回 code=2，拦截 `COMPLETE lacks explicit completion_requirements` | **PASS** |
| **P1-H** | 外部 Python 脚本直接调用 `evidence_binding.write_observed_output` 铸造 receipt | 抛出 `EvidenceIntegrityError` 拒绝直接调用 | 抛出 `EvidenceIntegrityError: production evidence receipts may only be minted by direct CLI execution` | **PASS** |
| **P1-I** | import Collector 并在内存中 monkeypatch 试图通过 `collector.main()` 铸造 receipt | 调用栈与 `__main__` 不匹配被拒绝 | 返回 code=2，拦截 `production evidence receipts may only be minted by direct CLI execution` | **PASS** |
| **P1-J** | Semrush 缺少 `current_network_capture` 或 artifact role 声明不符 | 抛出 `EvidenceIntegrityError` 拒绝缺失 role | 抛出 `EvidenceIntegrityError: collector artifact roles mismatch` | **PASS** |
| **P1-K** | 修改 raw response 中的数值并重新计算 raw hash（绕过纯 hash 检查） | Deterministic replay 与 normalized 不一致被拦截 | 返回 code=2，拦截 `Semrush normalized evidence differs from deterministic raw-response replay` | **PASS** |
| **P1-L** | Receipt 中的 `current_network_capture` 与 raw 中的 `capture_evidence_ref` 指向不同文件 | 捕获 capture binding mismatch 并失败 | 返回 code=2，拦截 `Semrush raw evidence is not bound to the receipt network capture` | **PASS** |
| **P1-M** | Google structured observation 中的 `intitle_results` 与 normalized 不一致 | Structured observation 与 normalized 冲突拦截 | 返回 code=2，拦截 `Google normalized intitle_results differs from structured observation` | **PASS** |
| **P1-N** | 篡改 Trends normalized series 使其与 raw temporal payload 重放不一致 | Trends temporal replay 冲突拦截 | 返回 code=2，拦截 `Google Trends normalized series differs from temporal payload replay` | **PASS** |
| **P1-O** | 真实 Stage6 未 PASS 时在命令前注入 `SEO_STAGE_REQUIRE=fake_stage` | Marker 被忽略，强制按推断 stage `stage6_exact` 拦截 | 返回 code=2，拦截 `SEO stage gate denied stage6_exact; status=BLOCKED` | **PASS** |
| **P1-P** | completion_requirements 声明伪造的 `fake_stage` | Stop Hook 检查 canonical stage 失败并 DENY | 返回 code=2，拦截 `uses unknown/non-canonical stage: fake_stage` | **PASS** |
| **P1-Q** | Traditional / Emerging 路线缺少最低 Stage（如 Traditional 缺 `discovery_autocomplete` 或 `stage6_exact`） | Stop Hook 校验路线最低 Stage 失败并 DENY | 返回 code=2，校验 `ROUTE_MINIMUM_STAGES` 拦截 | **PASS** |
