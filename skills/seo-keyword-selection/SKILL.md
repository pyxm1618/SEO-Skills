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
- `references/source-acquisition.md` — real-data acquisition and Semrush relay rules.

## Evidence Discipline

Every field is **observed**, **calculated**, **analysis**, or **unknown**. Never invent or estimate Volume, KD, CPC, `intitle` counts, rankings, DR, or SERP facts. `unknown` is not zero.

AI intent/SERP pre-analysis is hypothesis only. Predicted competition must never substitute for real SERP review.

## Production Runtime Contract

For Semrush ideas, related keywords, exact Volume/KD/CPC/intent/trend, or competitor organic evidence, use the verified `sem.3ue.com` logged-in relay first. **不得改走需要 API units 的官方 Semrush API/connector**，也不得因官方 API units 不足停止任务。中转会话失效时只修复登录/会话后继续；精确请求、复用和验证规则见 `references/source-acquisition.md`。

**用户可见输出默认使用中文**。内部 canonical 字段、枚举、JSON/CSV schema 与 evaluator 字段继续使用英文；除非用户要求 raw schema，最终表头、状态、解释和结论都显示中文。

有现成 Google Sheet 或需要跨批次人工补数/审核时，**Google Sheet 是默认人工可审计工作台**；优先续写既有工作簿，不擅自引入其他数据库。Google Sheet **不是执行该 Skill 的硬依赖**，也不改变 provenance、thresholds 或 evaluator 逻辑。unknown 不得为落表方便填成 0。

## Deterministic Evaluation

Use the evaluator instead of manually recomputing thresholds or formulas:

```bash
python scripts/evaluate_candidates.py --input ideas.json --stage ideas --format csv
python scripts/evaluate_candidates.py --input exact.json --stage exact --format csv
python scripts/evaluate_candidates.py --input final.csv --stage final --format csv
```

It computes only mechanical fields; it does not inspect Google or decide product-market fit.

## Human / Real-World Gates

- Google `intitle:"keyword"` count must be actually observed; otherwise KGR stays unknown.
- KD 40–50 requires real SERP review and at least two documented weak positions before `do_candidate`.
- Whether the team can build a materially better page/product remains a human decision.

## Completion

Preserve the final decision table and cluster survivors back to `domain × root × parent_seed`. Feed genuinely new recurring demand patterns back to `keyword-root-library`; never silently mutate it.

After changing this skill, run `pytest -q`.
