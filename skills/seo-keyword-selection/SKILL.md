---
name: seo-keyword-selection
description: Use when the user needs to choose SEO keyword opportunities, continue a keyword-research batch, evaluate a keyword dataset with real metrics, or decide which demand clusters deserve SERP validation or product consideration.
---

# SEO Keyword Selection

Run a reproducible SEO opportunity-selection workflow from demand roots to evidence-backed opportunity clusters. Resume from the earliest unfinished stage; do not redo verified work merely because the workflow starts midstream.

## Boundaries

This skill owns Seed generation, keyword expansion, metric screening, KGR/SERP validation, opportunity clustering, and decision support. It does **not** maintain the root library.

When roots are needed, use the installed `keyword-root-library` skill or accept a root handoff from the caller. Never copy or bundle `root-library.csv` here.

Read before execution:

- `references/selection-sop.md` — canonical end-to-end workflow.
- `references/data-contracts.md` — fields, provenance, unknown handling, and handoffs.
- `references/decision-rules.md` — current formulas and SERP upgrade rules.
- `references/thresholds.json` — machine-readable threshold source of truth.
- `references/source-acquisition.md` — how to obtain real keyword data without inventing or exposing secrets.

## Evidence Discipline

Every field is one of four kinds:

1. **observed** — returned by a real source or manually observed;
2. **calculated** — deterministic formula from observed inputs;
3. **analysis** — model/human interpretation, explicitly labeled;
4. **unknown** — missing and left missing.

Never invent or estimate Volume, KD, CPC, `intitle` counts, rankings, DR, or SERP facts. `unknown` is not zero.

AI intent/SERP pre-analysis is a hypothesis layer only. It may remove obvious brand/navigation or semantic-drift terms when evidence is clear, but predicted competition must never substitute for real SERP review.

## Production Runtime Contract

### Semrush relay

本项目获取 Semrush ideas、related keywords、exact Volume/KD/CPC/intent/trend 或 competitor organic keyword evidence 时，固定优先使用已经跑通的 `sem.3ue.com` 登录态中转。**不得改走需要 API units 的官方 Semrush API/connector**，也不得因为官方 API units 不足而停止当前批次。

中转会话失效时，只处理登录/会话问题后继续中转。优先复用已经验证过的同源请求、保存的 capture/result 或当前已登录页面流程；不得每次重新猜 endpoint、参数、分页、字段语义或 session key。新的精确 relay 请求必须先经真实 HTTP 200 + 预期响应结构验证，才能作为正式数据路径。

已经有当前 batch 的真实 Semrush 数据时直接复用，并从最早未完成阶段继续；不要为了“重新跑完整流程”重复消耗中转或覆盖更可信的已观察数据。

### User-visible language

**用户可见输出默认使用中文**。内部 canonical 字段、枚举、JSON/CSV schema、evaluator 输入输出字段继续使用英文；给用户看的表头、状态、风险、解释和最终结论默认翻译为中文。除非用户明确要求 raw schema，不要把英文 machine fields 当作最终展示。

例如用户可见最终表可以显示：`关键词 | 行业 | 词根 | 父级种子 | 搜索量 | KD | CPC | 搜索意图 | 趋势 | intitle结果数 | KGR | SERP弱点证据 | 页面形式 | 风险 | 状态`；内部仍保留 canonical 字段和 provenance。

### Google Sheet workspace

有现成 Google Sheet、用户要求持续记录，或批次需要人工补 Semrush/KGR/SERP 时，**Google Sheet 是默认人工可审计工作台**。优先续写既有工作簿/表结构，不擅自引入 Supabase 或其他数据库。Google Sheet **不是执行该 Skill 的硬依赖**；没有可用 Sheet 时仍可完成筛选并输出结构化结果。

推荐用户可见工作表职责：

- `关键词候选池`：保留 domain/root/parent_seed 与来源；
- `待 Semrush 验证`：需要通过中转补 ideas/exact/trend 的词；
- `KGR-SERP 待人工`：等待真实 Google `intitle` 或 Top10 审核；
- `最终关键词池`：已完成当前筛选阶段的结果；
- `运行记录`：批次、时间、来源、缺口和异常。

Sheet 只是生产工作台，不改变 `references/thresholds.json`、`decision-rules.md` 或 evaluator 的 canonical 逻辑。用户可见表头默认中文，内部字段通过稳定映射、隐藏列或导出文件保留。任何 unknown 继续保持 unknown，不能为了表格完整而填 0。

## Deterministic Evaluation

Use the evaluator instead of manually recomputing thresholds or formulas:

```bash
python scripts/evaluate_candidates.py --input ideas.json --stage ideas --format csv
python scripts/evaluate_candidates.py --input exact.json --stage exact --format csv
python scripts/evaluate_candidates.py --input final.csv --stage final --format csv
```

It supports CSV, a JSON array, or JSON objects containing `rows` or `keywords`. It computes only mechanical fields; it does not inspect Google or decide product-market fit.

## Human / Real-World Gates

- Google `intitle:"keyword"` result count must be actually observed. If unavailable, leave KGR unknown.
- KD 40–50 requires real SERP review and at least two documented weak positions before it may become a `do_candidate`.
- The final question — whether the team can build a materially better page/product than current results — remains a human decision.

## Completion

A finished batch must preserve the final decision table and cluster surviving opportunity keywords back to `domain × root × parent_seed`. Feed genuinely new recurring demand patterns back to `keyword-root-library`; do not silently mutate that library from this skill.

After changing this skill, run:

```bash
pytest -q
```
