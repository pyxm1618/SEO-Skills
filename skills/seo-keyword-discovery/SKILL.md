---
name: seo-keyword-discovery
description: Use when reusable demand roots must be turned into concrete traditional keyword candidates through real Google Autocomplete, current Semrush relay discovery, and the bounded Discovery Coverage Contract before keyword selection begins.
---

# SEO Keyword Discovery

Own the former `seo-keyword-selection` Steps 0–4 only: candidate-domain context, root handoff, Seed generation, real keyword expansion, low-risk cleaning, and finite traditional-demand branch coverage. Produce a discovery handoff of concrete keywords only after the Coverage Contract passes; do not make final opportunity decisions.

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

## Mandatory Google acquisition

For every required Seed, use the project Google live collector against a real Google Search page and capture the current visible autocomplete dropdown. A required Seed is blocked on network failure, CAPTCHA, unavailable/unconfirmed DOM, zero visible suggestions, or missing evidence.

Never substitute AI expansion, Bing, generic WebSearch results, or a third-party suggestion page for mandatory Google Autocomplete evidence.

## Seed generation from universal roots

`scripts/expand_seeds.py` fills the `x` slot of the universal root patterns
with a domain topic to produce Seed hypotheses:

```bash
python3 scripts/expand_seeds.py --domain tarot --topic tarot --format csv
```

Every row is `analysis`. A Seed becomes a candidate only after the live
collector observes it. The generator deliberately over-produces; unreal demand
is removed by Google returning nothing for it, not by AI judgement.

## People Also Ask and Related Searches

The result page already opened for a query also renders People Also Ask and
Related Searches. Capture both in one page load:

```bash
SEO_GOOGLE_CDP_URL="$CDP_URL" python3 runtime/collectors/google_live_collector.py expansions \
  --seed "angel number meaning" --market US --language en \
  --output .seo-run/evidence/expansions-angel-number-meaning.json
```

Validate with the `discovery_expansions` stage contract. These blocks expose
tool and format demand that autocomplete does not return for the same seed. A
query legitimately carrying only one of the two blocks still passes; a page
exposing neither is `BLOCKED`.

## Semrush discovery

Default Full Traditional Discovery requires Semrush Ideas/Related for every required Seed and every required Branch Seed. Current acquisition must use the authenticated same-origin `sem.3ue.com` relay collector. Google evidence is retained when Semrush is blocked, but the Full Coverage Contract remains `BLOCKED` and no formal handoff is allowed. An explicitly labelled diagnostic Google-only run is not a Full handoff.

There is no official API, API-key, connector, Ahrefs, or alternative-provider fallback. Historical captures are locator hints only; the current request descriptor, response, schema, and provenance must be re-confirmed in the current authenticated session.

## Competitor organic coverage

Competitor Organic Keywords are a domain/root-cluster coverage source, not a per-Seed requirement. The source is mandatory only when the run explicitly supplies competitor domains. Each configured domain must complete current `sem.3ue.com` relay acquisition; a failure is `BLOCKED`. With no configured domains, record `competitor_sweep=not_configured` rather than inventing a PASS or inventing competitor inputs.

## Demand branch expansion

Branch analysis may promote a keyword only from an already observed candidate. The ledger records the exact existing candidate, parent Seed, source, evidence receipt, analysis reason, and acquisition status. It may not turn an AI-created string into an observed Branch Seed. A required Branch Seed must run the same real Google Autocomplete and Semrush route as a required Seed, and the rows that acquisition returns are accounted for in the branch row ledger and delivered with the handoff.

Expansion is by distinct demand branch, not by recursively re-expanding every keyword. The runtime rejects visited/cycle duplicates, derives each Branch Seed's depth from its visited parent chain rather than from a declared value, and enforces configurable depth and branch-count safety limits. Those limits protect execution; they are not SEO opportunity thresholds.

## Discovery Coverage Contract

The final `discovery_coverage` record is the single Full Discovery coverage gate. It retains the complete run ledger and reports at least:

- required Seed count and Google Autocomplete pass count;
- required Semrush count and pass count, including branch counts;
- required Branch Seed count and completed branch count;
- competitor configuration/status and other mandatory-source statuses;
- explicit blocked/unreviewed reasons and `formal_handoff_allowed`.

The ledger must include the verified upstream input manifest, `source_seed` on every observed Candidate, and one analysis record for every authoritative Candidate. The current required Seed list and observed Candidate list must match the manifest's original totals and item identities exactly. The manifest itself is bound to its complete source-receipt set: every row those receipts returned is accounted for as kept, an explicit duplicate, or a rule-coded exclusion, so the Candidate denominator cannot be curated down before signing. A Candidate marked `branch_required=true` in the authoritative analysis must have exactly one Branch record; a `false` decision cannot be used to hide a missing Branch analysis. Every required item remains in the ledger when it is `BLOCKED`, `NOT_RUN`, or `UNKNOWN`; counts may not be shrunk by deleting failures. Full coverage is `PASS` only when every required Seed has Google and Semrush PASS, every required Branch Seed has both PASS, every configured competitor domain passes, and all other mandatory sources have a supported evidence type plus a verified receipt in production. Only then may a `discovery_handoff` be issued and passed to `seo-keyword-selection`.

Historical captured endpoints may help locate the current UI request but are not current evidence. A relay request becomes usable only after current live HTTP/RPC success and response-shape verification.

## Evidence discipline

Preserve `observed`, `calculated`, `analysis`, and `unknown`. Missing, invalid, numeric zero, and `not_applicable` are distinct states. AI may analyze or clean observed candidates but may not manufacture observed keyword suggestions or metrics.

## Completion

A formal `discovery_handoff` exists only when the production validator itself re-verifies the exact `discovery_coverage` receipt, whose report has `coverage_status=PASS` and `formal_handoff_allowed=true`, and when the handoff `keywords` list reconciles exactly against the verified first-round Candidates plus the reconciled Branch candidates. If any mandatory Seed, Branch Seed, configured competitor domain, or other mandatory source fails or remains unreviewed, mark the coverage batch `BLOCKED`; preserve the partial evidence and do not silently shrink the handoff.

Selection still owns Ideas-stage recall onward, including all Volume/KD/CPC/KGR/SERP/KDRoi and final opportunity decisions. This skill does not add Trends novelty, birth windows, Rising/breakout classification, long-term monitoring, a second root library, or a Discovery database.
