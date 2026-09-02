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

## Google People Also Ask and Related Searches

The current Google live collector **does** include a dedicated `expansions` mode. It opens a real Google Search result page for the Seed and captures visible People Also Ask questions and Related Searches from that page.

Example live command:

```bash
SEO_GOOGLE_CDP_URL="$CDP_URL" python3 runtime/collectors/google_live_collector.py expansions \
  --seed "wedding calculator" --market US --language en \
  --output .seo-run/evidence/expansions-wedding-calculator.json
```

The result is validated with the `discovery_expansions` stage contract. A page exposing either People Also Ask or Related Searches can satisfy that stage; when neither block is observed, the `expansions` collection itself returns `BLOCKED`.

This describes the **current implementation only**. At present, `discovery_coverage.py` does not list `google_serp_expansions` as one of the mandatory Full Discovery coverage evidence types, so this source does not replace mandatory Google Autocomplete or Semrush Ideas/Related and is not currently a machine-enforced Full Coverage requirement. Any change to make this acquisition mandatory must be implemented consistently in the Coverage Contract, source-receipt accounting, handoff reconciliation, and tests rather than by documentation alone.
