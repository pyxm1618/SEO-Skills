---
name: seo-keyword-discovery
description: Use when reusable demand roots must be turned into concrete traditional keyword candidates through real Google Autocomplete, mandatory Google PAA/Related-search checks, current Semrush relay discovery, bounded Discovery Coverage, and verified Google Sheet delivery before keyword selection begins.
---

# SEO Keyword Discovery

Own the former `seo-keyword-selection` Steps 0–4 only: candidate-domain context, root handoff, Seed generation, real keyword expansion, low-risk cleaning, and finite traditional-demand branch coverage. Produce a discovery handoff of concrete keywords only after the Coverage Contract passes and the exact handoff has been written to and read back from Google Sheets; do not make final opportunity decisions.

## Boundaries

- Upstream: `keyword-root-library` supplies roots.
- Before Coverage, the Root/Natural Seeds producer must hand off one production-verified `discovery_input_manifest` containing the exact Seed plan, the complete first-round source-receipt set, a row ledger accounting for every observed row, the resulting Candidate inventory, and complete per-Candidate branch-analysis state. Coverage consumes that receipt; it does not accept a self-reduced replacement ledger.
- Downstream: `seo-keyword-selection` starts at the former Step 5 / Ideas-stage recall.
- This skill does not own Exact qualification, KGR, SERP upgrade, KDRoi, opportunity clustering, mapping, or the human final decision.
- Confirmed `emerging`/`breakout` keywords do **not** come back through this skill; they hand directly to selection.

Read before execution:

- `references/discovery-sop.md`
- `references/data-contracts.md`
- `references/source-acquisition.md`

## Production start

Before the first discovery command, start the run manifest once and keep the
same path in `SEO_RUN_MANIFEST` for the whole run:

```bash
export SEO_RUN_MANIFEST=.seo-run/active.json
python3 runtime/start_seo_run.py --route traditional
```

The launcher creates a new `IN_PROGRESS` manifest and refuses to overwrite an
existing run. Record global discovery results in `stages`; discovery stages
remain global and must not carry `SEO_CANDIDATE_ID`. A normal code-review
session that has not started a production run does not require this manifest.

## Mandatory Google Autocomplete

For every required Seed and every required Branch Seed, use the project Google live collector against a real Google Search page and capture the current visible autocomplete dropdown. A required acquisition is blocked on network failure, CAPTCHA, unavailable/unconfirmed DOM, zero visible suggestions, or missing evidence.

Never substitute AI expansion, Bing, generic WebSearch results, or a third-party suggestion page for mandatory Google Autocomplete evidence.

## Seed generation from universal roots

`scripts/expand_seeds.py` fills the `x` slot of the universal root patterns
with a domain topic to produce Seed hypotheses:

```bash
python3 scripts/expand_seeds.py --domain tarot --topic tarot --format csv
```

Every row is `analysis`. A Seed becomes a candidate only after a live source observes a keyword. The generator deliberately over-produces; unreal demand is removed by real acquisition evidence, not by AI judgement.

## Mandatory People Also Ask + Related Searches check

Every required Seed and every required Branch Seed must attempt one real Google SERP expansion check covering both People Also Ask and Related Searches:

```bash
SEO_GOOGLE_CDP_URL="$CDP_URL" python3 runtime/collectors/google_live_collector.py expansions \
  --seed "angel number meaning" --market US --language en \
  --output .seo-run/evidence/expansions-angel-number-meaning.json
```

Validate the result with the `discovery_expansions` stage contract.

The requirement is **must check, not must find**:

- if either or both blocks contain terms, record `result_status=observed`, preserve all observed rows, and reconcile them through the normal row ledger into the Candidate inventory;
- if the real Google result page loads successfully and neither block is present, record `result_status=not_present`, `expansion_count=0`, and treat that acquisition as a valid PASS;
- if the check was never run, keep it `NOT_RUN` and Full Discovery cannot pass;
- if Google cannot be reliably checked because of CAPTCHA, network failure, unavailable/unconfirmed DOM, or missing evidence, keep it `BLOCKED` and Full Discovery cannot pass.

Do not turn a genuine zero-result page into a blocker, and do not turn an unexecuted check into a fake zero-result PASS.

## Semrush discovery

Default Full Traditional Discovery requires Semrush Ideas/Related for every required Seed and every required Branch Seed. Current acquisition must use the authenticated same-origin `sem.3ue.com` relay collector. Google evidence is retained when Semrush is blocked, but the Full Coverage Contract remains `BLOCKED` and no formal handoff is allowed. An explicitly labelled diagnostic Google-only run is not a Full handoff.

There is no official API, API-key, connector, Ahrefs, or alternative-provider fallback. Historical captures are locator hints only; the current request descriptor, response, schema, and provenance must be re-confirmed in the current authenticated session.

## Competitor organic coverage

Competitor Organic Keywords are a domain/root-cluster coverage source, not a per-Seed requirement. The source is mandatory only when the run explicitly supplies competitor domains. Each configured domain must complete current `sem.3ue.com` relay acquisition; a failure is `BLOCKED`. With no configured domains, record `competitor_sweep=not_configured` rather than inventing a PASS or inventing competitor inputs.

## Demand branch expansion

Branch analysis may promote a keyword only from an already observed candidate. The ledger records the exact existing candidate, parent Seed, source, evidence receipt, analysis reason, and acquisition status. It may not turn an AI-created string into an observed Branch Seed.

A required Branch Seed runs the same three mandatory acquisition checks as a required root Seed:

1. Google Autocomplete;
2. Google People Also Ask + Related Searches check;
3. Semrush Ideas/Related.

Rows returned by any of those sources are accounted for in the branch row ledger and delivered with the handoff. A valid zero-result PAA/Related check still counts as completed and contributes no rows.

Expansion is by distinct demand branch, not by recursively re-expanding every keyword. The runtime rejects visited/cycle duplicates, derives each Branch Seed's depth from its visited parent chain rather than from a declared value, and enforces configurable depth and branch-count safety limits. Those limits protect execution; they are not SEO opportunity thresholds.

## Row ledger and low-risk cleaning

Every row returned by every bound first-round source receipt must have an explicit destination: `kept`, `dedupe_of`, or `excluded`. Branch acquisition rows are reconciled the same way. No observed row may silently disappear.

Discovery exclusions are limited to low-risk cleaning such as clear brand/navigation intent, semantic drift, or non-target language/market. Do not remove a keyword here because Volume is low, KD is high, CPC is low, competition looks difficult, or the AI judges the opportunity unattractive. Those decisions belong downstream.

## Discovery Coverage Contract

The final `discovery_coverage` record is the single Full Discovery coverage gate. It retains the complete run ledger and reports at least:

- required Seed count and Google Autocomplete pass count;
- required PAA/Related-check count and pass count, including Branch Seeds;
- required Semrush count and pass count, including Branch Seeds;
- required Branch Seed count and completed branch count;
- competitor configuration/status and other mandatory-source statuses;
- explicit blocked/unreviewed reasons and `formal_handoff_allowed`.

The ledger must include the verified upstream input manifest, `source_seed` on every observed Candidate, and one analysis record for every authoritative Candidate. The current required Seed list and observed Candidate list must match the manifest's original totals and item identities exactly. The manifest itself is bound to its complete source-receipt set: every row those receipts returned is accounted for as kept, an explicit duplicate, or a rule-coded exclusion, so the Candidate denominator cannot be curated down before signing. A Candidate marked `branch_required=true` in the authoritative analysis must have exactly one Branch record; a `false` decision cannot be used to hide a missing Branch analysis. Every required item remains in the ledger when it is `BLOCKED`, `NOT_RUN`, or `UNKNOWN`; counts may not be shrunk by deleting failures.

Full coverage is `PASS` only when every required Seed and Branch Seed has Google Autocomplete PASS, Google PAA/Related check PASS (including legitimate `not_present` zero-result checks), and Semrush PASS; every configured competitor domain must also pass, and all other mandatory sources must have supported production evidence. Only then may the final handoff workflow begin.

Historical captured endpoints may help locate the current UI request but are not current evidence. A relay request becomes usable only after current live HTTP/RPC success and response-shape verification.

## Mandatory Google Sheet delivery

The complete handoff keyword set must be delivered to Google Sheets. JSON remains the machine-authoritative handoff; Google Sheets is the mandatory human-facing delivery surface, not a replacement for the JSON evidence ledger.

Use the same Google Spreadsheet already used by the SEO keyword system and a separate worksheet tab named `keyword_discovery`. The exporter uses a Google service-account credential file, so the executing AI does not need its own Google connector. Configure the environment once:

```bash
export SEO_KEYWORD_SHEET_ID="<existing spreadsheet id>"
export SEO_SHEETS_CREDENTIALS="<service-account json path>"
```

After Coverage PASS, create the handoff JSON and deliver it before production handoff validation:

```bash
python3 skills/seo-keyword-discovery/scripts/export_to_sheet.py \
  --handoff .seo-run/discovery-handoff.json
```

The exporter upserts the current batch into `keyword_discovery`, reads the worksheet back, and requires the exact current-batch Candidate set and exact row contents to match the handoff. A partial write, missing row, extra row, duplicate Candidate, or differing row is `BLOCKED`.

On successful readback the exporter writes a `seo-discovery-sheet-delivery/v1` receipt bound to the exact handoff and current exporter source, then adds `sheet_delivery_receipt_ref` to the handoff JSON. Production `discovery_handoff` validation re-verifies that receipt. Therefore a handoff that was never written to Google Sheets, was only partially written, or was changed after delivery cannot receive a production PASS receipt.

No final CSV is required. If a CSV is generated for convenience it is supplemental only; the required outputs are the machine handoff/evidence artifacts plus verified Google Sheet delivery.

## Evidence discipline

Preserve `observed`, `calculated`, `analysis`, and `unknown`. Missing, invalid, numeric zero, and `not_applicable` are distinct states. AI may analyze or clean observed candidates but may not manufacture observed keyword suggestions or metrics.

## Completion

A formal `discovery_handoff` exists only after this sequence succeeds:

1. production `discovery_coverage` re-verifies the frozen inputs and returns `coverage_status=PASS` with `formal_handoff_allowed=true`;
2. the handoff `keywords` list reconciles exactly against the verified first-round Candidates plus reconciled Branch candidates;
3. the exact handoff is written to the `keyword_discovery` Google Sheet tab and read back exactly;
4. the exporter binds that delivery to `sheet_delivery_receipt_ref`;
5. production `discovery_handoff` validation re-verifies both the Coverage receipt and the Sheet-delivery receipt.

If any mandatory Seed, Branch Seed, configured competitor domain, mandatory acquisition, or Sheet delivery fails or remains unreviewed, preserve the partial evidence, keep the batch non-complete, and do not silently shrink the handoff.

Selection still owns Ideas-stage recall onward, including all Volume/KD/CPC/KGR/SERP/KDRoi and final opportunity decisions. This skill does not add Trends novelty, birth windows, Rising/breakout classification, long-term monitoring, a second root library, or a Discovery database.
