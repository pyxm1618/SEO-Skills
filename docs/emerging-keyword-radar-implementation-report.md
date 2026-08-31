# Emerging Keyword Radar Review-Fix Implementation Report

> 历史快照：本文记录 PR #24 在 2026-08-30 的 repair SHA 与当时 Google 429 blocker，保留其
> `LIVE RELATED ACCEPTANCE BLOCKED` 原始结论，不代表当前 main 的发布状态。后续真实阶段三
> 验收已经完成；当前状态以 `HANDOFF.md`、`runtime/TRUST_BOUNDARY.md` 和
> `acceptance-evidence/terminal/stage3-live-*.md` 为准。

日期：2026-08-30
分支：`codex/seo-emerging-radar-repair`
Base：`codex/seo-a-plus-scope-correction`
Draft PR：[pyxm1618/SEO-Skills#24](https://github.com/pyxm1618/SEO-Skills/pull/24)

## 1. 范围与不变边界

本次按 PR #24 审核意见做增量修复，只扩展 `emerging-keyword-monitor` 及现有 Google evidence/stage contract 接口。没有重写现有 classifier、router、root library 或其他 Skill。

保留的边界：

- `unknown != 0`、真实来源、provenance、collector receipt 和 fail-closed 语义；
- Semrush 当前 authenticated `https://sem.3ue.com/` relay-only 边界；
- 现有 canonical `signal_type`、`status`、`route` 和 downstream selection ownership；
- 不引入 OAuth、Supabase、通用 Workflow Engine、Google Sheet 网络写入、API provider、Ahrefs 或 fallback provider。

## 2. 审核缺口闭合情况

| 审核项 | 实施结果 |
| --- | --- |
| Timeline canonical fields | `trends_timeline` 现在同时输出 canonical `market`、`observed_at`、`raw_evidence_ref`、`screenshot_ref`，并保留旧 Google aliases 供兼容 replay；stage validator 可直接校验。 |
| Comparable timeframe | `5y`、`12m`、`90d`、`30d`、`7d` 保持独立 series 和 provenance；没有跨 timeframe 拼接或算术。`5y` 只支持 history/birth，当前 classification 优先使用 `7d`、`30d`、`90d`，再到 `12m`。 |
| Google Breakout | 原始 Rising label 保存在 `google_rising_label`，不会直接产生 canonical `breakout`；canonical 结果仍由 temporal classifier 独立判断。 |
| Unicode evidence identity | Google evidence filename 和 runner artifact slug 都加入 UTF-8 identity hash；中文或其他 Unicode-only anchor 不会退化为同一个 `item` 文件，也不会覆盖不同 timeframe。 |
| Emerging completion stage | `emerging` route 的 canonical required stage 为 `emerging_radar_run`。runner 会写出 final summary、运行 stage validator，并在 PASS 时登记 validation receipt。 |
| Previous status history | status history 使用 previous record 的 `last_seen_at`，不再用当前 run 的 `discovered_at` 重写历史时间。 |
| Semrush supplemental | CLI 增加 repeatable `--semrush-request PATH`，只接受当前 authenticated Ideas descriptor，按 captured seed 映射；未匹配 anchor 可缺省，实际 relay/schema failure 仍 BLOCKED。Semrush 不递归 BFS。 |
| Rising BFS | Trends `relation_type=rising` 是默认唯一递归边；Autocomplete 和 Semrush 只作为 supplemental discovery evidence。 |
| Google isolation | Google live collector 优先使用独立 `SEO_GOOGLE_CDP_URL` browser/profile；否则仅在能安全创建 clean context 时使用一般 CDP。检测到 Google auth cookie 或无法隔离时 fail-closed。 |
| Related slow load | Related response 增加有界 payload wait，避免页面仍在加载时被过早判定；超时仍 BLOCKED。 |

## 3. SHA 与 checkpoint

- source/base SHA：`8b3a226327fe160ddec19a51ac47ba309897ff32`
- 审核快照前的 PR head：`9f0e7a1d90fbe1c0158c5c8fa1afd67bfad1b93a`
- review-fix code checkpoint：`1fee9b31675a6ed7490a6ba947ddb5205f8514cb`
- final collector wait/isolation follow-up checkpoint：`1bbf4e42e3c12cc6cda687aa132d2499f05b9f59`
- 最终 live replay 使用的 repair SHA：`1bbf4e42e3c12cc6cda687aa132d2499f05b9f59`

最终 live Timeline receipt 记录的 `google_live_collector` source SHA256 为：
`0ac68b53b818b7bbcf31a6b8e2d19a5bd501aeb55188f55a91379e19d3144692`，已与 repair SHA checkout 中的 collector 文件核对一致。

## 4. 文件变更

### 新增

- `docs/emerging-keyword-radar-implementation-report.md`
- `docs/superpowers/plans/2026-08-30-emerging-keyword-radar.md`
- `docs/superpowers/specs/2026-08-30-emerging-keyword-radar-design.md`
- `skills/emerging-keyword-monitor/references/initial-state-audit-2026-08-30.md`
- `skills/emerging-keyword-monitor/scripts/birth_history.py`
- `skills/emerging-keyword-monitor/scripts/radar_discovery.py`
- `skills/emerging-keyword-monitor/scripts/run_emerging_radar.py`
- `skills/emerging-keyword-monitor/scripts/update_emerging_database.py`
- `skills/emerging-keyword-monitor/tests/test_birth_history.py`
- `skills/emerging-keyword-monitor/tests/test_emerging_database.py`
- `skills/emerging-keyword-monitor/tests/test_radar_contracts.py`
- `skills/emerging-keyword-monitor/tests/test_radar_discovery.py`
- `tests/test_emerging_radar_google_safety.py`
- `tests/test_emerging_radar_related.py`

### 修改

- `runtime/TRUST_BOUNDARY.md`
- `runtime/codex_stage_hook.py`
- `runtime/collectors/google_live_collector.py`
- `runtime/evidence_binding.py`
- `runtime/stage_contracts.json`
- `runtime/stage_validator.py`
- `skills/emerging-keyword-monitor/SKILL.md`
- `skills/emerging-keyword-monitor/references/classification-rules.md`
- `skills/emerging-keyword-monitor/references/data-contracts.md`
- `skills/emerging-keyword-monitor/references/routing-rules.md`
- `skills/emerging-keyword-monitor/references/source-policy.md`
- `skills/emerging-keyword-monitor/references/state-machine.md`
- `skills/emerging-keyword-monitor/references/thresholds.json`
- `skills/emerging-keyword-monitor/scripts/aggregate_signals.py`
- `skills/emerging-keyword-monitor/scripts/classify_emergence.py`
- `skills/emerging-keyword-monitor/scripts/route_candidates.py`
- `skills/emerging-keyword-monitor/tests/test_emerging_monitor.py`
- `tests/test_hook_requirement_integrity.py`
- `tests/test_integrity_boundary_regressions.py`
- `tests/test_scope_correction.py`

工作树中已有的 `.gitignore` 修改属于无关环境变更，未暂存、未提交、未回退。

## 5. 自动化验证

- targeted：`python3 -m pytest -q skills/emerging-keyword-monitor/tests tests/test_live_acceptance_p1_repairs.py tests/test_observed_evidence_binding.py tests/test_execution_integrity.py` → `108 passed`。
- review-fix collector focused：`python3 -m pytest -q tests/test_emerging_radar_google_safety.py tests/test_emerging_radar_related.py` → `11 passed`。
- full repository：`python3 -m pytest -q` → `241 passed`。
- compile：`python3 -m compileall -q runtime skills` → exit `0`。
- whitespace：`git diff --check` 和 base-to-head `git diff --check` → exit `0`。
- `emerging_radar_run` PASS summary 的 production contract、receipt registration、PASS-with-blocker rejection、BLOCKED envelope 均有回归覆盖。

## 6. Final summary 与 Stage Contract

runner 最终写入：

- `output_artifacts.run_summary`
- `output_artifacts.database`
- `output_artifacts.csv`
- `output_artifacts.evidence_dir`
- `output_artifacts.emerging_radar_run_validation`
- `stages.emerging_radar_run`

`PASS` 必须没有 blockers，并且 stage record 必须包含 validation receipt。`BLOCKED` 必须保留至少一个结构化 blocker。summary validator 失败时不会继续宣称 PASS。

## 7. Final-SHA live evidence

运行使用独立的 Google Chrome process 和全新临时 `--user-data-dir`，只设置 `SEO_GOOGLE_CDP_URL` 连接 dedicated CDP，没有导入、复制或删除用户 Google cookies。截图中的 Google 页面显示“登录”入口。没有使用 Google authenticated user context、临时 Google 小号、API、代理轮换或 provider fallback。

### Timeline：PASS

- normalized output：`.seo-run/emerging-radar-live-20260830-reviewfix-final/002-wedding-planner-trends-timeline.json`
- raw payload：`.seo-run/emerging-radar-live-20260830-reviewfix-final/evidence/trends-wedding-planner-us-today-5-y-5c7f57450664.json`
- screenshot：`.seo-run/emerging-radar-live-20260830-reviewfix-final/evidence/trends-wedding-planner-us-today-5-y-5c7f57450664.png`
- collector receipt：`.seo-run/emerging-radar-live-20260830-reviewfix-final/002-wedding-planner-trends-timeline.receipt.json`
- stage validation：`.seo-run/emerging-radar-live-20260830-reviewfix-final/002-wedding-planner-trends-timeline.validation.json`
- validation receipt：`.seo-run/emerging-radar-live-20260830-reviewfix-final/002-wedding-planner-trends-timeline.validation.receipt.json`
- observed requested timeframe：`today 5-y`
- observed resolution：`weekly`
- collector stage validation：`PASS`

### Related：最终 SHA 下被外部限流 BLOCKED

最终 SHA 下用 `wedding planner` 和 `wedding venue` 做了有限次、独立 profile 的 Related 尝试。Google 实际返回页面正文：`429. That’s an error. We're sorry, but you have sent too many requests to us recently. Please try again later.` 因此没有合法 normalized Related output 或 receipt。

可审计 blocker artifacts：

- `.seo-run/emerging-radar-live-20260830-reviewfix-final/evidence/trends-related-wedding-planner-us-today-12-m-5cbc0590f8c5-blocked.json`
- `.seo-run/emerging-radar-live-20260830-reviewfix-final/evidence/trends-related-wedding-planner-us-today-12-m-5cbc0590f8c5-blocked.png`
- `.seo-run/emerging-radar-live-20260830-reviewfix-final-related-venue/evidence/trends-related-wedding-venue-us-today-12-m-fac5e3153d70-blocked.json`
- `.seo-run/emerging-radar-live-20260830-reviewfix-final-related-venue/evidence/trends-related-wedding-venue-us-today-12-m-fac5e3153d70-blocked.png`

collector 对该外部状态 fail-closed，没有创建伪造 candidate、timeline、route 或 Related receipt。该项不能报告为 live PASS；待 Google 限流解除后，应从 repair SHA 重新采集 Related 并验证 `trends_related` production receipt。

### Semrush

本次没有新的 authenticated Semrush descriptor，因此没有执行新的 Semrush live 请求，也没有虚报 Semrush E2E。CLI 能力已通过 descriptor validation/unit tests 覆盖，relay-only 和 same-origin 约束保持不变。

## Final verdict

`CODE REPAIR PASS / LIVE RELATED ACCEPTANCE BLOCKED`

审核指出的代码、contract、provenance、timeframe separation、history guard、Unicode identity、BFS policy、persistence、route handoff、completion-stage registration 和隔离边界已完成并通过自动化验证。Final-SHA Timeline live evidence 已 PASS；Final-SHA Related live evidence 仍被 Google 429 阻塞，因此不宣称完整 live E2E PASS。

PR 保持 Draft，不 merge、不 deploy，等待独立审核或 Google 限流解除后的 Related replay。
