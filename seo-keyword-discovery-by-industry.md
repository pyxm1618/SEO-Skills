# SEO Keyword Discovery：按行业整理

整理日期：2026-08-31  
当前可核验行业：Wedding / 婚礼婚庆  
父级 Seed：`wedding calculator`  
市场：US / en

## 证据与范围

- Google Autocomplete：10 条可见下拉建议，观察时间 `2026-08-29T00:58:54.481909+00:00`。
- Semrush Ideas：30 条结果，观察时间 `2026-08-28T04:08:53.990294+00:00`，数据库 `us`，来源为当前验收证据中的 `https://sem.3ue.com/` relay。
- 已有 discovery 验收报告状态：`discovery_autocomplete=PASS`、`discovery_semrush_ideas=PASS`、`discovery_handoff=PASS`。
- 这是工作区已有的历史实测证据整理，不代表已在 2026-08-31 重新采集；也不代表下游 selection、KGR、SERP 或最终机会判断已经完成。

## 行业结果

以下 30 行全部属于“婚礼婚庆”行业；“行业细分”是分析标签，不是删除或淘汰规则。Volume/KD 为 Semrush Ideas 字段；`unknown` 表示该字段未返回，不能当作 0。

### 婚礼酒水 / 饮品

| 关键词 | Volume | KD |
|---|---:|---:|
| wedding alcohol calculator | 2,400 | 12 |
| wedding drink calculator | 1,600 | 10 |
| liquor calculator wedding | 1,300 | 20 |
| liquor wedding calculator | 1,300 | 10 |
| alcohol calculator wedding | 1,000 | 24 |
| wedding liquor calculator | 1,000 | 23 |
| wedding beverage calculator | 590 | 16 |
| wedding booze calculator | 390 | 13 |
| alcohol calculator for wedding | 320 | 10 |
| alcohol wedding calculator | 320 | 10 |
| drink calculator for wedding | 320 | 7 |
| wedding reception alcohol calculator | 260 | 10 |
| beverage calculator for wedding | 170 | unknown |
| liquor calculator for wedding reception | 170 | 4 |
| liquor calculator for wedding | 140 | 10 |

小计：15 条；逐行 Volume 合计 11,280（不是去重后的总搜索量）。

### 婚礼礼金 / 礼物

| 关键词 | Volume | KD |
|---|---:|---:|
| cash wedding gift calculator | 1,300 | 33 |
| wedding money gift calculator | 720 | 37 |
| wedding gift cash calculator | 390 | 39 |
| wedding gift calculator | 320 | 9 |
| wedding cash gift calculator | 210 | 32 |

小计：5 条；逐行 Volume 合计 2,940。

### 婚礼预算 / 费用 / 贷款

| 关键词 | Volume | KD |
|---|---:|---:|
| wedding budget calculator | 1,300 | 32 |
| wedding cost calculator | 720 | 18 |
| wedding loan calculator | 480 | 44 |
| wedding price calculator | 320 | 15 |

小计：4 条；逐行 Volume 合计 2,820。

### 婚礼蛋糕 / 花艺 / 礼服

| 关键词 | Volume | KD |
|---|---:|---:|
| wedding cake calculator | 320 | 7 |
| wedding dress alterations calculator | 170 | 0 |
| wedding floral budget calculator | 170 | 0 |
| wedding flower budget calculator | 170 | 8 |

小计：4 条；逐行 Volume 合计 830。

### 婚礼日期 / 核心工具

| 关键词 | Volume | KD |
|---|---:|---:|
| wedding calculator | 320 | 22 |
| wedding date numerology calculator | 320 | 31 |

小计：2 条；逐行 Volume 合计 640。

## Google Autocomplete 原始发现

以下词来自真实 Google 当前可见下拉的历史证据；它们没有 Semrush Volume/KD，因此不补填指标。

| 分组 | Google 建议词 |
|---|---|
| 核心工具 | wedding calculator |
| 酒水 / 饮品 | wedding calculator alcohol |
| 预算 / 费用 | wedding calculator budget；wedding calculator cost |
| 礼金 / 礼物 | wedding calculator gift |
| 日期 | wedding calculator date |
| 规划资源 | wedding calculator spreadsheet |
| 地域修饰词 | wedding calculator israel；wedding calculator india；wedding calculator uk |

## 完整性台账

| 状态 | 数量 | 说明 |
|---|---:|---|
| observed / 已观测 | 30 条 Semrush Ideas + 10 条 Google 建议 | 全部在报告中保留 |
| calculated / 已整理 | 5 个婚礼细分组 | 仅用于归类展示 |
| unknown / 字段缺失 | 1 个 KD | `beverage calculator for wedding` 的 KD 未返回 |
| observed zero / 真实 0 | 2 个 KD | `wedding dress alterations calculator`、`wedding floral budget calculator` |
| confirmed reject / delete | 0 | 本次未删除、未排除任何关键词 |
| deferred / 待下游 | 全部机会判断 | 需要另行执行 selection、KGR、SERP 等步骤 |

## 原始证据

- Google observation：`.seo-run/acceptance/evidence/autocomplete-wedding-calculator.json`
- Google screenshot：`.seo-run/acceptance/evidence/autocomplete-wedding-calculator.png`
- Semrush normalized result：`.seo-run/acceptance/normalized/semrush-ideas-wedding-calculator.json`
- Discovery reports：`.seo-run/acceptance/reports/discovery_autocomplete.report.json`、`.seo-run/acceptance/reports/discovery_semrush_ideas.report.json`、`.seo-run/acceptance/reports/discovery_handoff.report.json`
