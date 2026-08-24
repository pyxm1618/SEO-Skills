---
name: keyword-root-library
description: Use when building, querying, auditing, or updating a reusable SEO keyword-root library before seed-keyword expansion, including roots from domain research, competitor organic keywords, SERPs, keyword tools, published root lists, or monetized sites.
---

# Keyword Root Library

Maintain a durable library of **demand roots** for downstream SEO discovery. A root is a reusable demand family; it is not limited to tool suffixes.

## Boundaries

Use this skill only for root discovery and root-asset maintenance. Do not score final keywords, run Volume/KD/CPC/KGR opportunity selection, or decide which product/site to build.

Read `references/root-taxonomy.md` before changing lifecycle, evidence, enums, or schema. Canonical asset: `references/root-library.csv`.

## Query First

Before proposing roots for a domain, query the library:

```bash
python scripts/query_roots.py --domain travel --limit 50
python scripts/query_roots.py --category calculate --status verified
python scripts/query_roots.py --text "meaning"
```

Prefer `verified` and `active`; keep `candidate` roots separated as hypotheses. Add roots only for uncovered demand.

## Coverage and Compounding

Treat the library as a bootstrap asset, not a complete universe. Before deliberately expanding it, inspect coverage:

```bash
python scripts/audit_coverage.py --format json
```

After a real downstream keyword-research batch, mine recurring patterns that are not already represented:

```bash
python scripts/mine_root_candidates.py --input path/to/keyword-batch.json --min-count 5 --limit 100
```

The miner is review-only: it never mutates the library, auto-adds roots, or assigns lifecycle status. Review candidates before changing the CSV. Coverage warnings are research priorities, not proof of opportunity.

## Discovery Sources

Roots may come from:

1. published root lists;
2. repeated user jobs inside a domain;
3. competitor site → organic keywords → recurring patterns;
4. keyword → focused site → sibling traffic keywords;
5. credible monetized-site/acquisition evidence;
6. recurring patterns discovered in downstream keyword-research batches.

Preserve provenance. Do not promote isolated keywords, brands/navigation terms, random nouns, or unsupported AI phrases.

## Evidence Rules

Follow `references/root-taxonomy.md` exactly:

- AI/internal inference alone stays `candidate/L0`.
- Published lists establish provenance, not verified demand.
- `verified` requires `L2` or `L3` real keyword/SERP/site/monetization evidence.
- Every `L1+` row requires `evidence_ref`.
- Root validation never substitutes for downstream keyword validation.
- Unknown evidence remains unknown.

Semrush-backed evidence is indexed in `references/semrush-interest-scan-2026-08-22.md`.

## Production Runtime Contract

### Semrush relay

当 root discovery、competitor organic keywords、keyword-tool evidence 或 root promotion 需要 Semrush 时，本项目固定优先使用已经跑通的 `sem.3ue.com` 登录态中转。**不得改走需要 API units 的官方 Semrush API/connector**，也不得因为官方 API units 不足而放弃补证或把 Semrush 字段直接判为不可获得。

中转会话失效时，只处理登录/会话问题后继续中转。优先复用已经验证过的同源请求、保存的 capture/result 或当前已登录页面流程；不得每次重新猜 endpoint、参数、分页、字段语义或 session key。新的精确 relay 请求只有在真实 HTTP 200 且响应结构符合预期后，才能作为正式采集契约。

已经存在可追溯的 Semrush 批次或用户提供的真实数据时先复用，不为同一事实重复抓取。任何缺失值仍保持 unknown，不能因为中转暂时不可用而推断需求不存在。

### User-visible language

**用户可见输出默认使用中文**。内部 canonical 字段、枚举、CSV schema 和 Python 脚本继续使用英文，以保持机器兼容；但给用户看的表头、状态、证据说明、审计结果和 handoff 默认翻译为中文。除非用户明确要求 raw schema，不要把英文 machine fields 直接作为最终界面。

用户可见 handoff 建议显示为：`词根 | 范围 | 需求类别 | 主要意图 | 状态 | 证据等级 | 证据引用 | 相关原因`。内部仍保存 `root | scope | demand_category | primary_intent | status | evidence_level | evidence_ref | why_relevant`。

### Google Sheet workspace

有现成 Google Sheet、用户要求持续维护，或需要跨批次人工审核时，**Google Sheet 是默认人工可审计工作台**。优先续写既有工作簿/表结构，不擅自引入 Supabase 或其他数据库。Google Sheet **不是执行该 Skill 的硬依赖**；没有可用 Sheet 时仍可查询、审计和输出结果。

`references/root-library.csv` 始终是 canonical root asset。Google Sheet 只能作为人工工作视图、审计视图或待审核候选池，不能绕过 `Mutation Contract` 直接成为词根库事实来源。任何从 Sheet 确认写回词根库的变更仍必须经过 taxonomy、证据、去重和 validator。

推荐用户可见工作表职责：`词根库视图`、`待审核词根`、`待 Semrush 验证`、`运行记录`。用户可见表头默认中文；内部 canonical 字段可通过稳定映射、隐藏列或导出文件保留。

## Deduplication

Normalize and search `root`, `aliases`, and `canonical_pattern` before adding. Never store the same term as both alias and canonical root. Split roots only when demand behavior differs materially.

## Mutation Contract

Preserve taxonomy, examples, lifecycle, evidence, provenance, dates, and caveats. Merge provenance with ` | `; deprecate rather than delete historical roots.

After every mutation run:

```bash
python scripts/validate_root_library.py
pytest -q
```

Do not treat the update as complete unless both pass.

## Downstream Handoff

Internal handoff fields:

```text
root | scope | demand_category | primary_intent | status | evidence_level | evidence_ref | why_relevant
```

Separate domain-specific roots, relevant universal roots, and unverified candidates. Do not generate Seeds until the caller moves to Seed expansion.

The downstream keyword-selection workflow owns Seed generation, expansion, metrics, KGR, SERP validation, opportunity clustering, and product decisions. This skill owns only the root asset and its evidence lifecycle.
