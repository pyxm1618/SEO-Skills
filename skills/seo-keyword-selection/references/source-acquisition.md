# Real-Data Acquisition Protocol

The workflow is source-agnostic, but metric fields must come from real observations. Prefer the shortest available path that preserves provenance.

## Source order

1. Reuse a current user-provided/exported dataset when it already contains the required observed fields.
2. Use a connected/current keyword-research source when available.
3. Use an already-configured authenticated user-side workflow or relay when the user has one; never request cookies, session tokens, passwords, or API secrets in chat.
4. Otherwise ask for/export only the missing fields rather than restarting the research.

## Semrush roles

- **Ideas/related-keyword output** is a discovery + wide-recall input.
- **Exact keyword lookup** is the authoritative stage for current Volume/KD/CPC/intent/trend used downstream.
- Null/missing CPC or other metrics mean `unknown`, not zero.
- Preserve database/market (normally `us` for this workflow), generation time, and source batch where available.

The specific Semrush interface may change. Use the currently working official connector/API, user-provided export, or an already-authorized user-side workflow. Do not hard-code credentials into the Skill.

## Google observations

- `intitle:"keyword"` numerator must be manually/reliably observed from Google; no substitute count is accepted.
- Real SERP review must inspect the actual current top results. If live SERP evidence cannot be obtained, store `unknown`/`pending` rather than pretending the review happened.
- Google Trends and Keyword Planner are late-stage cross-checks; they do not replace the main metric source or KGR/SERP evidence.

## Resume rule

If a batch already has exact Volume/KD/CPC but lacks `intitle`, resume at KGR collection. If CPC is missing, retrieve CPC only. Never force the user to rerun completed stages without a concrete data-quality reason.

## Provenance metadata for saved batches

When saving/exporting a metric batch, include batch-level metadata whenever possible so rows do not lose traceability:

```json
{
  "metric_source": "Semrush",
  "metric_stage": "exact",
  "database": "us",
  "generated_at": "2026-08-22T07:59:51Z",
  "rows": []
}
```

Do not infer `metric_source` or `metric_stage` merely from the evaluator CLI stage. The CLI stage says how to evaluate the input; it does not prove where the metrics came from. Older files missing provenance may still be mechanically evaluated, but must remain `provenance_status=incomplete` until their source is documented.
