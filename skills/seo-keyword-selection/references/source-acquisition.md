# Real-Data Acquisition Protocol

Production evidence for this workflow comes from project collectors. Hosted WebSearch may support ordinary research but cannot become formal Google/Semrush evidence.

## Reuse before reacquisition

Reuse fresh compatible evidence that already satisfies the relevant selection contract. This is especially important for confirmed emerging/breakout handoffs: acquire only the earliest missing contract and never rerun discovery merely to normalize the route.

## Semrush Exact source policy

Every new/current Semrush acquisition must use only the current authenticated same-origin session at `https://sem.3ue.com/` via `runtime/collectors/semrush_relay_collector.py`.

There is no production path for:

- official Semrush API or API keys/units;
- official connector fallback;
- Ahrefs or another provider standing in for Semrush;
- AI estimates.

The relay collector does not hard-code a historical endpoint. A current same-origin network capture supplies the request descriptor, and live HTTP/RPC success plus expected response shape must be verified before the result can be production evidence. Historical `/kwogw/v2/webapi`, `ideas.GetKeywords`, or `keywords.GetInfo` captures are locator hints only until re-observed live.

Stage 6 Exact requires current US Volume, KD, CPC, intent, competition level, and 12-month trend plus complete provenance. Missing required Exact evidence blocks that candidate from Stage 7+ production evaluation but does not alter the evaluator's mechanical `pending_metrics` behavior.

## Google project collectors

Use `runtime/collectors/google_live_collector.py` for formal Google evidence:

- `intitle` mode for real visible `intitle:"keyword"` counts;
- optional `serp` mode for current real top-10 rank/url evidence;
- `trends` mode for finalist Google Trends cross-check.

If a collector fails, keep the evidence missing and mark the affected execution scope blocked. Do not substitute Bing, generic result counts, APIs, WebSearch output, or AI estimates.

## Resume rule

If compatible Exact evidence already exists but `intitle` is missing, resume at KGR collection. If only a required Exact field is missing, reacquire/repair the Exact evidence rather than restarting discovery. Never force completed stages to rerun without a concrete freshness or compatibility reason.

## Provenance

Preserve enough information to answer where the fact came from, which market it represents, when it was observed, and which project collector/evidence artifact produced it. Evaluator CLI stage names never prove acquisition provenance by themselves.
