# Source Acquisition

Use real sources; do not fabricate metrics or SERPs.

## Preferred sources

1. connected/official keyword platform API or connector;
2. source export supplied by the user;
3. authenticated browser relay/session when the user already has lawful access and the source UI exposes the data;
4. live search/SERP observation for intent evidence;
5. GSC after launch for query/page ownership calibration.

If a field cannot be observed, leave it `unknown`.

## Discovery vs exact/core verification

Discovery is intentionally wide and may use multiple seeds/markets. Preserve raw provenance. After ownership classification and Core compression, spend expensive metric calls on the small candidate set rather than every discovered row.

## Semrush pattern used by this repository

When an authenticated browser session exposes the same Semrush backend route used by the UI, a caller may use it as an acquisition adapter. Known methods from prior validated work include:

- `ideas.GetKeywords` for discovery;
- `keywords.GetInfo` for keyword/country evidence.

Do not store cookies, relay tokens, `__gmitm` values, credentials, or account identifiers in this repository. Use `credentials: "include"` only inside the user's existing authenticated browser context. Add retry, throttling, checkpoint/resume, and raw JSON preservation.

Endpoint/method behavior is not a permanent contract. If the UI changes, re-discover the active request shape instead of guessing or silently substituting fabricated values.

## SERP evidence

SERP Fast Check may use a normal search query and the top result titles/types. SERP Deep Review should record the actual top URLs, page types, entity intent, and any overlap calculation used for architecture or cannibalization decisions.
