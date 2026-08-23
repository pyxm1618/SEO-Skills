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

Return a compact pool containing:

```text
root | scope | demand_category | primary_intent | status | evidence_level | evidence_ref | why_relevant
```

Separate domain-specific roots, relevant universal roots, and unverified candidates. Do not generate Seeds until the caller moves to Seed expansion.

The downstream keyword-selection workflow owns Seed generation, expansion, metrics, KGR, SERP validation, opportunity clustering, and product decisions. This skill owns only the root asset and its evidence lifecycle.
