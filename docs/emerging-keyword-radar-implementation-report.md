# Emerging Keyword Radar 增量实施报告

日期：2026-08-30  
分支：`codex/seo-emerging-radar-repair`  
Base：`codex/seo-a-plus-scope-correction`

## 1. 范围与不变边界

本次只扩展 `emerging-keyword-monitor` 及其现有 Google evidence/stage contract 接口，未重写 classifier、router、root library 或其他 Skill。保留了：

- `unknown != 0`、真实来源、provenance、collector receipt 和 fail-closed 语义；
- Semrush 当前 authenticated `https://sem.3ue.com/` relay-only 边界；
- 现有 canonical `signal_type`、`status`、`route` 和 downstream selection ownership；
- `root-library.csv`、`seo-keyword-selection` thresholds、OAuth、Supabase、通用 Workflow Engine 和 Google Sheet 网络写入均未进入本次范围。

## 2. SHA 与 checkpoint

- source/base SHA：`8b3a226327fe160ddec19a51ac47ba309897ff32`
- 初始审计 checkpoint：`8774a7a`，对应 `references/initial-state-audit-2026-08-30.md`
- 设计 checkpoint：`7ea543b`
- 计划 checkpoint：`b3bac8a`
- Related collector checkpoint：`2a70c2d`
- timeframe/isolation checkpoint：`04de282`
- Rising-only BFS checkpoint：`6a525e4`
- birth/history checkpoint：`8e7440c`
- persistence/runner checkpoint：`6ea71c1`
- contract/docs checkpoint：`8799931`
- blocker-evidence checkpoint：`1268231`
- 最终代码 checkpoint（报告提交前）：`db77db3`

报告提交后，远端 branch head 以 push 和 Draft PR 页面显示的 SHA 为准；该报告中的“最终代码 checkpoint”指最后一个非报告代码提交，避免报告内容形成自引用 SHA。

## 3. 实施内容

执行链路：

```text
domain / explicit anchors / read-only root hints
        -> Google Trends Related/Rising
        -> domain relation gate + dedupe
        -> Rising-only BFS (depth / per-anchor / global caps)
        -> optional Autocomplete / Semrush supplemental pool (never recursive)
        -> independent 5y | 12m | 90d timeline series
        -> observation validation + provenance replay
        -> 5y-only birth/history inference
        -> existing temporal classifier
        -> existing router / selection handoff only
        -> .seo-run JSON database + CSV
```

关键实现：

- `runtime/collectors/google_live_collector.py` 增加 Related/Rising parser、parameterized timeline、actual resolution、serial throttle、Google auth-cookie rejection，以及 blocker 页面证据保存。
- `runtime/evidence_binding.py`、`runtime/stage_validator.py`、`runtime/stage_contracts.json` 增加 `google_trends_related`、`trends_related`、`trends_timeline` 和 `emerging_radar_run` contract。
- `skills/emerging-keyword-monitor/scripts/radar_discovery.py` 以 Trends `relation_type=rising` 作为唯一默认递归边；Top 只作 anchor evidence，Google `Breakout` 只保存 `google_rising_label`。
- `birth_history.py` 只消费一条长期 comparable series，输出 bucket/month 粒度的 birth window、resolution、confidence、reason、evidence series 和 `demand_history_type`。
- `aggregate_signals.py` 保持 timeframe 在 series key 中独立，记录 source URL、requested timeframe、actual resolution、series 和 evidence refs；不做跨 timeframe arithmetic 或拼接。
- `classify_emergence.py` 对 `preexisting`、`resurgent` 增加 `net_new` guard；Google `Breakout` 不会直接生成 canonical `breakout`。
- `update_emerging_database.py` 保留 earliest `first_observed_at`、previous status/evidence、status history 和 unknown；`run_emerging_radar.py` 提供 domain-level thin orchestration、stage validation、route handoff 和 `.seo-run` artifacts。

## 4. Birth/history 规则

- 低/零 observed baseline 后出现多点持续脱离低基线：`newly_observed`，窗口只覆盖实际形成点和 follow-up。
- 第一批可用 bucket 已经持续有明显需求：`preexisting` + `birth_reason=before_available_history`，不把第一 bucket 当生日。
- 历史正向 run + 实际 quiet gap + 后续持续上升：`resurgent`；旧 run 从第一 bucket 开始时 birth window 保持 unknown，存在可验证低基线时才报告历史 birth window。
- 单次 spike 不产生高置信度 birth。
- weekly/monthly source 不输出伪造日级生日；daily source 才允许日级标签。

## 5. 文件清单

新增：

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

修改：

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

## 6. 自动化验证

- 初始 clean baseline：`203 passed`。
- Task 4 focused temporal/history regression：`50 passed`。
- Task 5 persistence/routing regression：`41 passed`。
- Task 6 contract/hook/evidence regression：`35 passed`。
- 最终 repository suite：`231 passed in 4.90s`。
- 最终 targeted suite：`100 passed`。
- 最终 `python3 -m compileall -q runtime skills`：exit `0`。
- 最终 `git diff --check`：exit `0`。
- `emerging_radar_run` blocked-run envelope 通过 `runtime/stage_validator.py` contract validation：`status=PASS`，其内部运行状态仍正确保持 `BLOCKED`。

## 7. Real Google E2E evidence

运行方式：启动独立的 Google Chrome process 和临时 `--user-data-dir`，只设置 `SEO_GOOGLE_CDP_URL` 连接该 dedicated CDP；没有导入、复制或删除用户 Google cookies。截图中的 Google 页面显示登录入口，证明该 context 未使用用户登录状态。

最终 rerun：

- summary：`.seo-run/emerging-radar-live-20260830-rerun/run-summary.json`
- blocker raw evidence：`.seo-run/emerging-radar-live-20260830-rerun/evidence/trends-related-chatgpt-blocked.json`
- blocker screenshot：`.seo-run/emerging-radar-live-20260830-rerun/evidence/trends-related-chatgpt-blocked.png`
- observed external response：Google `429`，页面正文为 “You've sent too many requests to us recently”。
- runner result：`status=BLOCKED`、exit `2`、`candidate_counts` 全部为 `0`；没有生成伪造候选、timeline 或 route。

此前一次真实 Related 请求还生成了可验证的空 Related payload：

- `.seo-run/emerging-radar-live-20260830/evidence/trends-related-wedding-planner.json`
- `.seo-run/emerging-radar-live-20260830/evidence/trends-related-wedding-planner.png`
- `.seo-run/emerging-radar-live-20260830/002-wedding-planner-trends_related.validation.json`
- stage validation 为 `PASS`、`complete_count=1`、`related_queries=[]`；空 Rising 不是伪造候选。

本次 E2E 没有请求新的 Semrush 数据，因此没有虚报 authenticated relay E2E。Semrush collector 和 same-origin relay-only policy 未改写；没有 API、API key、Ahrefs 或 fallback provider。

## 8. Environment blockers 与风险

- Google 429 是外部请求限流，已取得真实页面 blocker JSON/screenshot，且 collector/runner fail-closed。它阻止本次 live run 继续到 timeline，但不暴露 valid source data 会被错误接受的代码缺陷。
- shared `browse` daemon 的 Playwright Chromium cache 缺失；实际 E2E 使用系统 Google Chrome 的新独立 profile 完成了真实 Google 到达和 blocker 证据采集。
- 没有 staging、production、PR merge 或 deployment 证据；本次请求不包含这些动作。
- P0：0。P1：0。外部 Google 限流为环境 blocker，不折算为代码 PASS。

## Final verdict

`PASS WITH ACCEPTED ENVIRONMENT BLOCKER`

代码、contract、provenance、隔离、timeframe-local normalization、history guard、BFS cap、persistence、route handoff 和全量自动化验证已完成；独立审核仍需以远端 Draft PR diff、测试、live evidence 和本报告交叉验收。不得 merge。
