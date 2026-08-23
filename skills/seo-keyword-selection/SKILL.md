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
