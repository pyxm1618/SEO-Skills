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

## Google People Also Ask and Related Searches

Every required Seed and every required Branch Seed must run `runtime/collectors/google_live_collector.py expansions` against a real Google Search result page. The collector attempts both visible People Also Ask questions and Related Searches in the same acquisition.

Example live command:

```bash
SEO_GOOGLE_CDP_URL="$CDP_URL" python3 runtime/collectors/google_live_collector.py expansions \
  --seed "wedding calculator" --market US --language en \
  --output .seo-run/evidence/expansions-wedding-calculator.json
```

Validate the output with `discovery_expansions`.

The acquisition is mandatory to **attempt**, but Google is not required to return expansion rows:

- one or both blocks observed: `result_status=observed`, `expansion_count>0`, PASS when evidence validates;
- real page checked successfully but neither block present: `result_status=not_present`, `expansion_count=0`, PASS;
- acquisition never run: `NOT_RUN`, which blocks Full Discovery;
- CAPTCHA, network failure, unavailable/unconfirmed DOM, or missing evidence: `BLOCKED`, which blocks Full Discovery.

Observed PAA/Related rows are normal Discovery source rows. First-round rows must be frozen in `source_receipts` and reconciled through `candidate_inventory.row_ledger`; Branch rows are reconciled through `branch_row_ledger`. They may become Candidates, explicit duplicates, or supported low-risk exclusions. A valid zero-result acquisition contributes no rows but still proves the mandatory check was performed.

`google_serp_expansions` does not replace Google Autocomplete or Semrush Ideas/Related. All three mandatory Seed-level acquisitions are independently accounted for by the Full Coverage gate.

## Semrush relay only

Every new/current Semrush acquisition in this repository uses only `https://sem.3ue.com/` through the authenticated same-origin browser session. Full Traditional Discovery uses the relay for Ideas/Related on every required Seed and Branch Seed; an explicitly configured competitor sweep uses the same relay for each competitor domain.

`runtime/collectors/semrush_relay_collector.py` deliberately contains no permanent Semrush endpoint. Supply a request descriptor created from a **current live same-origin network capture**. The descriptor must include request path/method/body, capture time, and evidence reference. The collector refuses cross-origin execution and fails closed on HTTP/RPC or response-schema failure.

The supported descriptor modes are `ideas`, `exact`, and `competitor_organic`. The competitor mode requires `competitor_domain` and returns only the current observed keyword rows and any fields present in the relay response. It does not invent competitor domains or metrics.

Historical knowledge such as prior `/kwogw/v2/webapi`, `ideas.GetKeywords`, or `keywords.GetInfo` observations may be used only to help locate the current request in the UI. Do not copy a historical endpoint into a live descriptor until current traffic proves it still exists and returns the expected schema.

There is no fallback to official Semrush API, API keys/units, official connectors, Ahrefs, alternative providers, or AI estimates.
