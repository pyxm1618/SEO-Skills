# Source and Ingestion Policy

## Supported ingestion model

v1 is source-agnostic at the normalized-data layer. It accepts CSV/JSON produced by manual exports, authenticated user-side workflows, verified relay captures, environment-backed adapters, or external connectors when those sources preserve provenance.

Priority source families include:

1. Google Trends observations/exports;
2. Semrush trend or keyword observations obtained through the project relay contract;
3. competitor sitemap/page-set diffs;
4. demand-source feeds such as query, community, marketplace, or product-release feeds.

Support for an input contract is **not** a claim of live automated collection.

## Semrush project contract

For this project, Semrush acquisition is not source-agnostic at runtime:

- Semrush 查询固定优先走已经跑通的 `sem.3ue.com` 中转；
- **不得改走需要 API units 的官方 Semrush API/connector**；
- 不得因为官方 API units 不足而停止 Semrush 补证；
- 中转会话失效时，只处理登录/会话问题后继续中转；
- 优先复用已验证的同源请求、保存的 capture/result 或当前已登录页面流程；
- 不得每次重新猜 endpoint、参数、分页、字段语义或 session key；
- 一个新的精确 relay 请求只有在实际 HTTP 200 且响应结构符合预期后，才可视为已验证采集契约。

缺少已验证的精确 relay 请求时，保留相关字段 `unknown`，并补最小真实验证；不能退回官方 units-based API/connector，也不能把猜测的 endpoint 当正式流程。

## No embedded authentication

Never commit cookies, API tokens, passwords, Google/Semrush credentials, relay credentials, session IDs, or private connector secrets. Authentication belongs in the already-authorized user-side session or external connector configuration and is not stored in this repository.

## Provenance

Every observation should answer: where did it come from, when was it observed, which market/country does it represent, what window does it cover, and what unit is the signal measured in?

Missing provenance is recorded as incomplete. It does not become verified through inference.

## Source independence

`source_count` counts unique source identities, not rows and not multiple series from the same source. Cross-source evidence may raise confidence, but the monitor does not use a fixed `N-of-M signals = build` rule.

## Immediate-discovery source semantics

A first trusted search-demand observation may be surfaced immediately as `new_signal`. Repeated observations, 7/30-day persistence, and historical baselines strengthen or change classification later; they are not prerequisites for telling the user that a new signal has been observed.

Supply-side/product/community observations may be surfaced immediately as discovery clues, but they do not become confirmed search-demand growth unless a compatible search-demand series supports that claim.

## Google Trends caution

Google Trends values are relative indexes. A historical zero does not prove absolute search Volume was zero, and the first non-zero point does not prove an absolute keyword birth date.

## Semrush caution

Missing Semrush Volume/KD is data absence or lag. It is neither a negative gate nor positive evidence that a keyword is new.
