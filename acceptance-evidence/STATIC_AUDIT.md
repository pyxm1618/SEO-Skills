# 第一层：静态代码与配置审计 (STATIC_AUDIT)

- **验收目标 SHA**：`d616f0202d1d781f15e10aa13e7ade73a58f8e34`
- **Base SHA**：`335599be974601d0958036849e268347b6cd52d5` (`origin/main`)
- **审计结论**：**PASS**

---

## 1. Git Diff 统计

```text
.codex/hooks.json                                  |  29 ++
 .github/workflows/ci.yml                           |   2 +-
 .gitignore                                         |   1 +
 README.md                                          |  58 ++-
 runtime/TRUST_BOUNDARY.md                          |  51 ++
 runtime/codex_stage_hook.py                        | 479 ++++++++++++++++++
 runtime/collectors/google_live_collector.py        | 360 ++++++++++++++
 runtime/collectors/semrush_relay_collector.py      | 331 +++++++++++++
 runtime/evidence_binding.py                        | 546 +++++++++++++++++++++
 runtime/kgr_evidence_merge.py                      | 114 +++++
 runtime/stage_contracts.json                       |  81 +++
 runtime/stage_validator.py                         | 319 ++++++++++++
 .../references/routing-rules.md                    |  10 +-
 .../references/source-policy.md                    |  21 +-
 skills/seo-keyword-discovery/SKILL.md              |  41 ++
 .../references/data-contracts.md                   |  61 +++
 .../references/discovery-sop.md                    |  53 ++
 .../references/source-acquisition.md               |  25 +
 skills/seo-keyword-selection/SKILL.md              |  63 +--
 .../references/selection-sop.md                    |  72 ++-
 .../references/source-acquisition.md               |  55 +--
 .../scripts/evaluate_candidates.py                 |  34 +-
 .../seo-keyword-selection/tests/test_selection.py  |   8 +-
 .../references/source-acquisition.md               |  31 +-
 .../references/workflow.md                         |  16 +-
 tests/test_a_plus_architecture.py                  |  38 ++
 tests/test_a_plus_confirmed_gaps.py                | 262 ++++++++++
 tests/test_codex_stage_hooks.py                    | 108 ++++
 tests/test_execution_integrity.py                  | 144 ++++++
 tests/test_hook_requirement_integrity.py           | 129 +++++
 tests/test_integrity_boundary_regressions.py       | 177 +++++++
 tests/test_observed_evidence_binding.py            | 432 ++++++++++++++++
 tests/test_post_validation_integrity.py            | 112 +++++
 tests/test_semrush_capture_freshness.py            |  38 ++
 tests/test_semrush_source_policy.py                |  36 ++
 35 files changed, 4158 insertions(+), 179 deletions(-)
```

---

## 2. 核心 12 项静态安全与合规审计

| 序号 | 审计项 | 规范要求 | 静态审计结果 | 判定 |
|---|---|---|---|---|
| 1 | Semrush 官方 API 审计 | 严禁包含官方 Semrush API / API Key / Connector | 检索 `runtime/` 和 `skills/` 无官方 API 调用，所有 SOP 文档均声明禁止降级 | **PASS** |
| 2 | SEO 第三方 Provider Fallback | 严禁回退至 Ahrefs/DataForSEO/Moz/Bing/WebSearch | 检索确认无 Provider fallback 逻辑，文档与代码均做 fail-closed 限制 | **PASS** |
| 3 | Production Mock 路径隔离 | 生产模式下严禁使用 mock/synthetic evidence 签发 | `runtime/evidence_binding.py` 中移除了合成签发 helper，所有 production 签发依赖 OS-level broker | **PASS** |
| 4 | 收据验证 Fail-Closed | 无 broker 或证明损坏时必须拒绝 | `_trusted_broker_path()` 和 `_verify_issuance_proof()` 严格 fail-closed，缺失时抛出 `EvidenceIntegrityError` | **PASS** |
| 5 | Broker 签名密钥隔离 | 签名密钥不得存放在仓库内 | 仓库未包含任何签名私钥/HMAC secret 文件，全部委托独立 broker 二进制 | **PASS** |
| 6 | Workspace Secret 弃用 | `.seo-run/.issuance_secret` 不得作为信任源 | 代码完全移除 `.seo-run/.issuance_secret` 逻辑 | **PASS** |
| 7 | 环境变量 Secret 弃用 | `SEO_ISSUANCE_SECRET` 不得授予签发权 | 代码完全移除 `SEO_ISSUANCE_SECRET` 环境变量信任逻辑 | **PASS** |
| 8 | 候选词收据隔离与全局防穿透 | Candidate-specific 阶段严禁回退 Global receipt | `codex_stage_hook.py` 与 `stage_validator.py` 严格校验 candidate_id 绑定，不匹配直接拒绝 | **PASS** |
| 9 | Emerging 路由可信认证 | Emerging route 必须具备外部可信 attestation | Hook 在 `_verify_route_attestation()` 中强制校验 `emerging_route` attestation | **PASS** |
| 10 | Finalist 决策防伪造 | 严禁 Agent 自由声明 `is_finalist=false` 逃避 Trends | Hook 在 `_verify_finalist_disposition()` 中强制要求外部 `candidate_finalist` attestation | **PASS** |
| 11 | Terminal BLOCKED 可信约束 | 阻断候选词必须持有 `candidate_blocked` attestation | Hook 在 `_verify_terminal_blocked_candidate()` 中强制校验 block attestation 与 canonical stage | **PASS** |
| 12 | Exact 阶段合法早停淘汰 | 必须基于现有 evaluator 规则确定早停，不强制后续阶段 | Hook 在 `_verified_exact_disposition()` 中结合 evaluator 的原则淘汰规则（Volume/KD/Manual）允许早停 | **PASS** |

---

## 3. 冻结业务阈值审计 (Thresholds Audit)

- **文件路径**：`skills/seo-keyword-selection/references/thresholds.json`
- **Git Blob SHA**：`77ad84a7c9523c1254e40228308355e12f022a0f`（与预期 `77ad84a7c9523c1254e40228308355e12f022a0f` 完全一致）
- **SHA-256**：`0496b841e48651cecd47e497960362966c6acf63334be802087dd612393ae97d`
- **内容核验**：
```json
{
  "ideas": {
    "main_volume_min": 5000,
    "main_kd_max_inclusive": 55,
    "blue_volume_min": 300,
    "blue_kd_max_exclusive": 45
  },
  "exact": {
    "main_volume_min": 9000,
    "blue_volume_min": 500,
    "do_kd_max_exclusive": 40,
    "observe_kd_max_inclusive": 50
  },
  "cpc_positive_min": 0.10,
  "kgr_pass_max_exclusive": 0.25,
  "serp_upgrade_weak_points_min": 2,
  "calibration_batches": 2
}
```

- **阈值语义核验**：
  - Ideas main: Volume >= 5000, KD <= 55
  - Ideas blue: Volume >= 300, KD < 45
  - Exact main: Volume >= 9000
  - Exact blue: Volume >= 500
  - do: KD < 40
  - observe: KD <= 50
  - CPC positive: >= 0.10
  - KGR pass: < 0.25
  - SERP upgrade weak points: >= 2
  - calibration: 2 batches

---

## 4. 静态审计结论

静态审计通过（**STATIC AUDIT = PASS**）。所有核心模块设计严密，职责边界清晰，不存在已知的权限穿透或逻辑降级通道。
