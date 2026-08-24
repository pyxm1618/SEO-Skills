---
name: emerging-keyword-monitor
description: Use when discovering or monitoring newly forming search demand, breakout queries, or new search expressions over time, including distinguishing net-new demand from breakout growth and routing confirmed emerging signals downstream.
---

# Emerging Keyword Monitor

Detect and maintain evidence for search demand that is newly observed, accelerating, or changing expression. This skill answers **what demand is forming or changing now**; it does not make final SEO opportunity decisions.

## Boundaries

Use this skill for temporal demand discovery and monitoring. It may consume `root_id` references from `keyword-root-library`, but it must never copy or mutate `root-library.csv`.

It may hand confirmed emerging candidates to `seo-keyword-selection`, but it must never emit `do_candidate`, `observe`, or `principle_eliminate` as final SEO decisions and must not modify that skill's thresholds.

Read before execution:

- `references/data-contracts.md` — observation/candidate fields and unknown semantics.
- `references/source-policy.md` — ingestion and provenance rules.
- `references/classification-rules.md` — net-new, breakout, variant, noise, and metric boundaries.
- `references/state-machine.md` — explainable states and transitions.
- `references/routing-rules.md` — downstream handoff rules.
- `references/thresholds.json` — v1 temporal-shape thresholds only.

## Evidence Discipline

`unknown != 0`. Missing values remain unknown; malformed values are invalid. Never invent Volume, KD, CPC, `intitle`, SERP facts, timestamps, first-seen dates, trend values, or growth.

`first_observed_at` means the first observation in the current evidence system. It is not an absolute keyword birth date. Google Trends zero is a relative signal, not proof of zero real searches.

Never add signals with different units or incomparable source contexts. Trends indexes, search volume, mentions, and other units remain separate series.

If a real data source is unavailable, say so and leave the relevant field `unknown`. Do not replace a missing search-demand time series with supply-side page counts, product launches, article frequency, or general web mentions and then call the result confirmed search growth.

## Production Runtime Contract

### Immediate discovery is not confirmation

新词监控的第一目标是**尽可能早地发现并报告新信号**，确认强度是第二层工作。

- 当出现**第一次可信信号**时，必须**立即报告**，不得为了等待更多样本而静默。
- 对来自真实搜索需求来源、且 provenance 完整的第一次正向 observation，允许 canonical `status=new_signal`；它表示“已发现一个真实新信号”，不表示已经确认 `net_new`、`emerging` 或 `breakout`。
- 仅有产品发布、网页增加、社区讨论等供给/讨论线索时，也可以立即放入用户可见的“发现线索”区，但 canonical search-demand classification 仍按证据保持 `unknown` / `insufficient_evidence`，直到取得真实可比搜索需求 observation。
- **7/30 天窗口只用于后续确认** persistence、growth、breakout、mature/noise 等状态，**不是发现等待期**。不得解释成“等 7 天以后再告诉用户”。
- 后续 observation 到来时更新同一 candidate 的证据和状态；不能因为第一次信号尚未确认就丢弃它。

### Semrush relay

本项目需要 Semrush ideas、exact metrics、trend 或历史证据时，固定优先使用已经跑通的 `sem.3ue.com` 登录态中转。**不得改走需要 API units 的官方 Semrush API/connector**，也不得因为官方 API units 不足而停止任务。

中转会话失效时，只处理登录/会话问题后继续中转。优先复用已经验证过的同源请求、保存的 capture/result 或当前已登录页面流程；不得每次重新猜 endpoint、参数、分页或字段语义。对某个新的 Semrush 页面/请求，如果精确 relay contract 尚未验证，只能先做最小真实验证（HTTP 200 + 预期响应结构）后再作为正式采集路径，不能把猜测写成已验证事实。

### User-visible language

**用户可见输出默认使用中文**。内部 canonical 字段、枚举、JSON/CSV schema 和 Python 脚本继续使用英文，避免破坏机器契约；但给用户看的表头、状态名称、解释、日报和结论必须翻译成中文。除非用户明确要求 raw schema，不要把英文 machine fields 当作最终界面直接倾倒给用户。

建议显示映射包括：`new_signal=新信号`、`watch=观察`、`emerging=新兴`、`breakout=爆发`、`mature=成熟`、`noise=噪声`、`insufficient_evidence=证据不足`。机器层仍保存原始 enum。

### Google Sheet workspace

有现成 Google Sheet 或用户要求持续记录时，**Google Sheet 是默认人工可审计工作台**。优先续写既有工作簿/表结构，不擅自引入 Supabase 或其他数据库。Google Sheet **不是执行该 Skill 的硬依赖**；没有可用 Sheet 时仍可完成扫描并输出结构化结果，之后再落表。

推荐的用户可见工作表职责：

- `新词实时池`：每个新 observation/发现线索追加记录，不覆盖历史；
- `新词状态表`：每个 keyword 当前最新 canonical 状态的中文视图；
- `待 Semrush 验证`：需要通过中转补 ideas/exact/trend 的关键词；
- `今日警报`：首次发现、状态升级、明显爆发等需要立即看的变化；
- `运行记录`：扫描时间、来源、成功/失败、数据缺口。

内部 canonical 字段可保留在机器文件、隐藏列或稳定映射中；用户可见表头默认中文。不要因为落表方便而把 `unknown` 改成 0。

## Workflow

Validate observations:

```bash
python scripts/validate_observations.py --input observations.json --format json
```

Aggregate only comparable time series:

```bash
python scripts/aggregate_signals.py --input observations.json --format json
```

Classify temporal evidence:

```bash
python scripts/classify_emergence.py --input candidates.json --format json
```

Route without making final SEO decisions:

```bash
python scripts/route_candidates.py --input classified.json --format json
```

When running interactively without normalized files, apply the same contracts conceptually. Do not loosen the state machine or routing rules just because evidence was gathered conversationally or from web research.

## Canonical Runtime Contract

Use canonical enums exactly in structured output. Do not invent aliases such as `candidate`, `strong candidate`, `reject`, `possible emerging`, or mixed labels such as `typo / modifier shift` in canonical fields.

`signal_type` must be exactly one of `net_new`, `breakout`, `emerging_variant`, or `unknown`.

`variant_subtype` must be exactly one of `new_expression`, `typo`, `modifier_shift`, or `unknown`.

`status` must be exactly one of `new_signal`, `watch`, `emerging`, `breakout`, `mature`, `noise`, or `insufficient_evidence`.

`route` must be exactly one of `selection_handoff`, `root_candidate_handoff`, `new_root_watchlist`, `monitor_only`, or `no_handoff`.

Human-readable commentary may describe strength or hypotheses, but it must not replace or redefine these canonical fields.

## Confirmed Classification vs Hypothesis

A hypothesis is not a confirmed classification.

If a query looks like it may be accelerating because product launches, new pages, community discussion, or category formation are increasing, but comparable temporal search-demand evidence is missing, record a hypothesis such as `possible_breakout` in commentary/evidence and keep `signal_type=unknown` unless another signal type is actually evidenced.

If comparable historical baseline plus persistent recent growth is not available, the skill must not emit `signal_type=breakout`.

If the evidence required by `classification-rules.md` is not established, the skill must not emit `status=emerging` or `status=breakout` merely because the term looks promising, commercially interesting, fresh, widely discussed, or under-supplied.

Use `new_signal`, `watch`, or `insufficient_evidence` according to the evidence actually available. In particular, supply-side freshness alone cannot confirm temporal search-demand growth.

`emerging_variant` requires both a semantic relationship to an existing expression and real temporal evidence for the new expression. A plausible wording shift without temporal evidence remains `signal_type=unknown` with a variant hypothesis in commentary.

## Types and States

Signal types: `net_new`, `breakout`, `emerging_variant`. Variant subtypes: `new_expression`, `typo`, `modifier_shift`.

States: `new_signal`, `watch`, `emerging`, `breakout`, `mature`, `noise`, `insufficient_evidence`.

Every classification returns a reason, evidence used, remaining unknown fields, confidence, and explicit state-change metadata when a previous state is supplied. Anchor events may strengthen interpretation but are never mandatory.

## Routing Discipline

Only `status in {emerging, breakout}` may produce `selection_handoff`, and only when the candidate maps to an existing valid root as required by `routing-rules.md`.

`new_signal` and `watch` must remain `monitor_only` when an existing root is known. They are not sent to `seo-keyword-selection` just because further keyword research would be useful.

`root_candidate_handoff` requires both confirmed `status in {emerging, breakout}` and a reviewable `root_candidate_hypothesis`. Otherwise retain the item in `new_root_watchlist`.

`mature`, `noise`, and `insufficient_evidence` produce `no_handoff` unless the routing rules explicitly preserve an unresolved root watch case.

Do not recommend a downstream route in prose that contradicts the canonical `route` field.

## Interactive Output

Internal structured records expose at least:

`keyword | signal_type | variant_subtype | status | first_observed_at | growth_rate | persistence | source_count | volume | kd | cpc | intitle_results | metric_status | metric_compatibility_status | kgr_compatibility_status | kgr | root_relation | route`

Use `unknown` when a field is not supported by real evidence. Do not omit an unknown field merely to make the candidate look more complete.

用户可见层默认把这些字段和枚举翻译为中文，并按“即时发现 / 已确认新兴或爆发 / 观察 / 证据不足”组织结果。不要创建一个替代 canonical state 的 informal `candidate` bucket。

## Data Sources

v1 supports clean CSV/JSON ingestion contracts for Google Trends exports, Semrush trend/keyword exports, competitor sitemap diffs, demand-source feeds, manual exports, API responses, or external connectors. For this project, Semrush acquisition follows the verified `sem.3ue.com` relay rule above rather than the official units-based API/connector. These contracts do **not** claim that any third-party source is being scraped or monitored automatically.
