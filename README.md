# SEO Skills

> **一句话：** 一组可复用的 SEO Agent Skills，用来维护需求词根、发现传统与新兴关键词、筛选值得做的关键词，并把确认后的关键词映射到页面。

这个仓库采用 5 个职责分开的 Skill；A+ 只拆清执行职责，不重新设计 SEO 方法。

## 怎么唤醒 Skill

前提：你的 Agent / IDE 已经安装或加载本仓库的 Skills。

**最稳妥的方式：直接在提示词中写出 Skill 名称。**

例如：

```text
使用 seo-keyword-selection，帮我筛选这批候选关键词。
```

支持 Agent Skills 自动匹配的环境，也可以根据各 `SKILL.md` 的 `description` 自动选择；是否支持自动触发取决于宿主环境。需要确定调用哪个 Skill 时，直接点名最可靠。

## 选哪个 Skill

| Skill | 它负责什么 | 最简单的调用方式 |
| --- | --- | --- |
| [`keyword-root-library`](skills/keyword-root-library/SKILL.md) | 找、查、维护可复用的 SEO **需求词根库** | `使用 keyword-root-library，帮我找并整理 [行业] 的需求词根。` |
| [`seo-keyword-discovery`](skills/seo-keyword-discovery/SKILL.md) | 把 domain/root/Seed 通过真实 Google Autocomplete 与允许的真实发现来源扩展为 **concrete candidates** | `使用 seo-keyword-discovery，从这些 roots 和 Seeds 发现候选关键词。` |
| [`emerging-keyword-monitor`](skills/emerging-keyword-monitor/SKILL.md) | 从时间序列证据中发现 **正在形成、加速或出现新表达的搜索需求** | `使用 emerging-keyword-monitor，分析这批趋势数据里有哪些新兴关键词。` |
| [`seo-keyword-selection`](skills/seo-keyword-selection/SKILL.md) | 用真实指标、KGR、SERP 等证据 **筛选值得继续做的 SEO 关键词机会** | `使用 seo-keyword-selection，筛选这批候选关键词，告诉我哪些值得继续做。` |
| [`seo-page-keyword-mapping`](skills/seo-page-keyword-mapping/SKILL.md) | 把已确认的搜索需求 **分配给已知/规划页面**，确定 Primary / Secondary keyword 和页面归属 | `使用 seo-page-keyword-mapping，把这批关键词映射到这些页面。` |

## 两条工作流

传统路线：

```text
keyword-root-library
  -> seo-keyword-discovery
  -> seo-keyword-selection
  -> seo-page-keyword-mapping
```

Emerging 路线：

```text
emerging-keyword-monitor
  -> seo-keyword-selection
  -> seo-page-keyword-mapping
```

Confirmed `emerging` / `breakout` 已经是 concrete keyword，进入 selection 时不得重新跑 Seed -> Google Autocomplete -> Semrush Ideas discovery；已有 fresh compatible evidence 应复用，缺哪个 selection stage 就从最早缺失位置继续。

## 数据与来源原则

- `observed`：只能来自真实 source / collector。
- `calculated`：由程序从真实输入确定性计算。
- `analysis`：允许 AI 做语义、意图、SERP weakness、页面形态等判断，但不能冒充 observed。
- `unknown`：就是没有取得，不能变成 0 或估算值。
- `missing`、`invalid`、numeric `0`、`not_applicable`、`unknown` 必须区分。
- 当前 Semrush acquisition 只允许项目 `sem.3ue.com` authenticated same-origin relay；失败时不切换 official API、Ahrefs 或其他 provider。
- Google Autocomplete、intitle、SERP、Google Trends 必须是当前真实 Google evidence；拿不到就 BLOCKED。

## 仓库结构

```text
skills/
  keyword-root-library/
  seo-keyword-discovery/
  emerging-keyword-monitor/
  seo-keyword-selection/
  seo-page-keyword-mapping/
runtime/
  collectors/
  stage_contracts.json
  stage_validator.py
  codex_stage_hook.py
  kgr_evidence_merge.py
.codex/
  hooks.json
```

唯一 canonical `root-library.csv` 位于 `keyword-root-library` 中，其他 Skill 只通过 handoff / `root_id` 使用它，不复制该资产。

## 开发 / 验证

仅在修改 Skill / runtime 实现时需要：

```bash
python3 -m pytest skills/keyword-root-library/tests/test_root_library.py -q
python3 -m pytest skills/seo-keyword-selection/tests/test_selection.py -q
python3 -m pytest skills/emerging-keyword-monitor/tests -q
python3 -m pytest skills/seo-page-keyword-mapping/tests -q
python3 -m pytest -q
python3 -m compileall -q skills runtime
```
