# Real-Data Acquisition Protocol

Metric fields must come from real observations. Prefer the shortest available path that preserves provenance and reuses already-verified work.

## Source order

1. Reuse a current user-provided/exported dataset when it already contains the required observed fields.
2. Reuse already-saved, traceable captures/results from the current project when they answer the same field and market.
3. For Semrush, use the project relay contract below.
4. For non-Semrush sources, use a connected/current source or an already-authorized user-side workflow when available; never request cookies, session tokens, passwords, or API secrets in chat.
5. Otherwise obtain only the missing fields rather than restarting the research.

## Semrush project contract

For this project, Semrush is fixed to the already-working logged-in relay path:

- Semrush 查询固定优先走已经跑通的 `sem.3ue.com` 中转；
- **不得改走需要 API units 的官方 Semrush API/connector**；
- 不得因为官方 API units 不足而停止当前 keyword batch；
- 中转会话失效时，只处理登录/会话问题后继续中转；
- 优先复用已验证的同源请求、保存的 capture/result 或当前已登录页面流程；
- 不得每次重新猜 endpoint、参数、分页、字段语义或 session key；
- 新的精确 relay 请求只有在真实 HTTP 200 且响应结构符合预期后，才可升级为正式采集契约。

如果某个 Semrush 页面/功能尚无已验证的精确 relay 请求，先做最小真实验证并保留未取得字段为 `unknown`。禁止因为中转契约暂缺就退回官方 units-based API/connector，或把猜测 endpoint 当成正式流程。

## Semrush roles

- **Ideas/related-keyword output** is a discovery + wide-recall input.
- **Exact keyword lookup** is the authoritative stage for current Volume/KD/CPC/intent/trend used downstream.
- Null/missing CPC or other metrics mean `unknown`, not zero.
- Preserve database/market (normally `us` for this workflow), generation time, source batch, and relay/capture provenance where available.

The Semrush web interface may change, but the runtime policy above does not: continue through the verified `sem.3ue.com` relay/session path and repair only the minimum missing request contract if necessary. Do not hard-code credentials into the Skill.

## Google observations

- `intitle:"keyword"` numerator must be manually/reliably observed from Google; no substitute count is accepted.
- Real SERP review must inspect the actual current top results. If live SERP evidence cannot be obtained, store `unknown`/`pending` rather than pretending the review happened.
- Google Trends and Keyword Planner are late-stage cross-checks; they do not replace the main metric source or KGR/SERP evidence.

## Resume rule

If a batch already has exact Volume/KD/CPC but lacks `intitle`, resume at KGR collection. If CPC is missing, retrieve CPC only. Never force the user to rerun completed stages without a concrete data-quality reason.

## Google Sheet working state

When a Google Sheet is already being used for the keyword batch, treat it as the default human-auditable working state for missing-data queues and review status. Preserve stable mappings between the Chinese visible columns and canonical machine fields. Google Sheet is a working surface, not a replacement for metric provenance, decision thresholds, or the deterministic evaluator.

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
