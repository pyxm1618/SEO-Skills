# SEO Skills

> **一句话：** 一组可复用的 SEO Agent Skills，用来维护需求词根、发现正在形成的新搜索需求、筛选值得做的关键词，并把确认后的关键词映射到页面。

这个仓库不是一个“大而全”的 Skill，而是 4 个职责分开的 Skill。

## 怎么唤醒 Skill

前提：你的 Agent / IDE 已经安装或加载了本仓库的 Skills。

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
| [`emerging-keyword-monitor`](skills/emerging-keyword-monitor/SKILL.md) | 从时间序列证据中发现 **正在形成、加速或出现新表达的搜索需求** | `使用 emerging-keyword-monitor，分析这批趋势数据里有哪些新兴关键词。` |
| [`seo-keyword-selection`](skills/seo-keyword-selection/SKILL.md) | 用真实指标、KGR、SERP 等证据 **筛选值得继续做的 SEO 关键词机会** | `使用 seo-keyword-selection，筛选这批候选关键词，告诉我哪些值得继续做。` |
| [`seo-page-keyword-mapping`](skills/seo-page-keyword-mapping/SKILL.md) | 把已确认的搜索需求 **分配给已知/规划页面**，确定 Primary / Secondary keyword 和页面归属 | `使用 seo-page-keyword-mapping，把这批关键词映射到这些页面。` |

## 常见工作流

```text
keyword-root-library ───────────┐
                               ├─> seo-keyword-selection ─> seo-page-keyword-mapping
emerging-keyword-monitor ──────┘
```

- `keyword-root-library` 提供可复用的需求词根。
- `emerging-keyword-monitor` 是发现“现在正在形成什么需求”的另一条输入，不是每次都必须经过。
- `seo-keyword-selection` 负责最终的关键词机会筛选。
- `seo-page-keyword-mapping` 在页面集合已经明确后，负责关键词与 URL / 页面架构的归属。

## 共同原则

- 不把缺失数据当成 `0`。
- 不编造 Volume、KD、CPC、`intitle`、SERP、趋势或排名等真实世界数据。
- 每个 Skill 只负责自己的职责边界；详细规则以各自的 `SKILL.md` 为准。

## 仓库结构

```text
skills/
  keyword-root-library/
  emerging-keyword-monitor/
  seo-keyword-selection/
  seo-page-keyword-mapping/
```

每个 Skill 都包含自己的 `SKILL.md`、references、scripts 和 tests。唯一的 canonical `root-library.csv` 位于 `keyword-root-library` 中，其他 Skill 只通过 handoff / `root_id` 使用它，不复制该资产。

## 开发 / 验证

仅在修改 Skill 实现时需要：

```bash
python3 -m pytest -q
```
