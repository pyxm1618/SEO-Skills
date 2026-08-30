# Discovery Source Acquisition

## Google Autocomplete

Formal Google Autocomplete evidence must come from `runtime/collectors/google_live_collector.py autocomplete` running against a real browser session. Hosted WebSearch may support ordinary research but cannot satisfy this contract.

Example live command:

```bash
SEO_BROWSER_CDP_URL="$CDP_URL" python3 runtime/collectors/google_live_collector.py autocomplete \
  --seed "wedding calculator" --country US --language en \
  --output .seo-run/evidence/autocomplete-wedding-calculator.json
```

If the collector returns `BLOCKED`, do not invent suggestions or replace the source.

## Semrush relay only

Every new/current Semrush acquisition in this repository uses only `https://sem.3ue.com/` through the authenticated same-origin browser session. Full Traditional Discovery uses the relay for Ideas/Related on every required Seed and Branch Seed; an explicitly configured competitor sweep uses the same relay for each competitor domain.

`runtime/collectors/semrush_relay_collector.py` deliberately contains no permanent Semrush endpoint. Supply a request descriptor created from a **current live same-origin network capture**. The descriptor must include request path/method/body, capture time, and evidence reference. The collector refuses cross-origin execution and fails closed on HTTP/RPC or response-schema failure.

The supported descriptor modes are `ideas`, `exact`, and `competitor_organic`. The competitor mode requires `competitor_domain` and returns only the current observed keyword rows and any fields present in the relay response. It does not invent competitor domains or metrics.

Historical knowledge such as prior `/kwogw/v2/webapi`, `ideas.GetKeywords`, or `keywords.GetInfo` observations may be used only to help locate the current request in the UI. Do not copy a historical endpoint into a live descriptor until current traffic proves it still exists and returns the expected schema.

There is no fallback to official Semrush API, API keys/units, official connectors, Ahrefs, alternative providers, or AI estimates.

## Supplementary Google sources

The current Google Collector has a reliable Autocomplete, intitle, SERP, and Trends path, but no dedicated Related Searches/PAA parser. Related/PAA remain optional future supplementary sources and cannot satisfy the Full Google or Semrush coverage requirements in this repair.
