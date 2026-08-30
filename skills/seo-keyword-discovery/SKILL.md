---
name: seo-keyword-discovery
description: Use when reusable demand roots must be turned into concrete traditional keyword candidates through real Google Autocomplete, current Semrush relay discovery, and the bounded Discovery Coverage Contract before keyword selection begins.
---

# SEO Keyword Discovery

Own the former `seo-keyword-selection` Steps 0–4 only: candidate-domain context, root handoff, Seed generation, real keyword expansion, low-risk cleaning, and finite traditional-demand branch coverage. Produce a discovery handoff of concrete keywords only after the Coverage Contract passes; do not make final opportunity decisions.

## Boundaries

- Upstream: `keyword-root-library` supplies roots.
- Before Coverage, the Root/Natural Seeds producer must hand off one production-verified `discovery_input_manifest` containing the exact Seed plan, original Candidate inventory, and complete per-Candidate branch-analysis state. Coverage consumes that receipt; it does not accept a self-reduced replacement ledger.
- Downstream: `seo-keyword-selection` starts at the former Step 5 / Ideas-stage recall.
- This skill does not own Exact qualification, KGR, SERP upgrade, KDRoi, opportunity clustering, mapping, or the human final decision.
- Confirmed `emerging`/`breakout` keywords do **not** come back through this skill; they hand directly to selection.

Read before execution:

- `references/discovery-sop.md`
- `references/data-contracts.md`
- `references/source-acquisition.md`

## Mandatory Google acquisition

For every required Seed, use the project Google live collector against a real Google Search page and capture the current visible autocomplete dropdown. A required Seed is blocked on network failure, CAPTCHA, unavailable/unconfirmed DOM, zero visible suggestions, or missing evidence.

Never substitute AI expansion, Bing, generic WebSearch results, or a third-party suggestion page for mandatory Google Autocomplete evidence.

## Semrush discovery

Default Full Traditional Discovery requires Semrush Ideas/Related for every required Seed and every required Branch Seed. Current acquisition must use the authenticated same-origin `sem.3ue.com` relay collector. Google evidence is retained when Semrush is blocked, but the Full Coverage Contract remains `BLOCKED` and no formal handoff is allowed. An explicitly labelled diagnostic Google-only run is not a Full handoff.

There is no official API, API-key, connector, Ahrefs, or alternative-provider fallback. Historical captures are locator hints only; the current request descriptor, response, schema, and provenance must be re-confirmed in the current authenticated session.

## Competitor organic coverage

Competitor Organic Keywords are a domain/root-cluster coverage source, not a per-Seed requirement. The source is mandatory only when the run explicitly supplies competitor domains. Each configured domain must complete current `sem.3ue.com` relay acquisition; a failure is `BLOCKED`. With no configured domains, record `competitor_sweep=not_configured` rather than inventing a PASS or inventing competitor inputs.

## Demand branch expansion

Branch analysis may promote a keyword only from an already observed candidate. The ledger records the exact existing candidate, parent Seed, source, evidence receipt, analysis reason, and acquisition status. It may not turn an AI-created string into an observed Branch Seed. A required Branch Seed must run the same real Google Autocomplete and Semrush route as a required Seed.

Expansion is by distinct demand branch, not by recursively re-expanding every keyword. The runtime rejects visited/cycle duplicates and enforces configurable depth and branch-count safety limits. Those limits protect execution; they are not SEO opportunity thresholds.

## Discovery Coverage Contract

The final `discovery_coverage` record is the single Full Discovery coverage gate. It retains the complete run ledger and reports at least:

- required Seed count and Google Autocomplete pass count;
- required Semrush count and pass count, including branch counts;
- required Branch Seed count and completed branch count;
- competitor configuration/status and other mandatory-source statuses;
- explicit blocked/unreviewed reasons and `formal_handoff_allowed`.

The ledger must include the verified upstream input manifest, `source_seed` on every observed Candidate, and one analysis record for every authoritative Candidate. The current required Seed list and observed Candidate list must match the manifest's original totals and item identities exactly. A Candidate marked `branch_required=true` in the authoritative analysis must have exactly one Branch record; a `false` decision cannot be used to hide a missing Branch analysis. Every required item remains in the ledger when it is `BLOCKED`, `NOT_RUN`, or `UNKNOWN`; counts may not be shrunk by deleting failures. Full coverage is `PASS` only when every required Seed has Google and Semrush PASS, every required Branch Seed has both PASS, every configured competitor domain passes, and all other mandatory sources have a supported evidence type plus a verified receipt in production. Only then may a `discovery_handoff` be issued and passed to `seo-keyword-selection`.

Historical captured endpoints may help locate the current UI request but are not current evidence. A relay request becomes usable only after current live HTTP/RPC success and response-shape verification.

## Evidence discipline

Preserve `observed`, `calculated`, `analysis`, and `unknown`. Missing, invalid, numeric zero, and `not_applicable` are distinct states. AI may analyze or clean observed candidates but may not manufacture observed keyword suggestions or metrics.

## Completion

A formal `discovery_handoff` exists only when the production validator itself re-verifies the exact `discovery_coverage` receipt, whose report has `coverage_status=PASS` and `formal_handoff_allowed=true`. If any mandatory Seed, Branch Seed, configured competitor domain, or other mandatory source fails or remains unreviewed, mark the coverage batch `BLOCKED`; preserve the partial evidence and do not silently shrink the handoff.

Selection still owns Ideas-stage recall onward, including all Volume/KD/CPC/KGR/SERP/KDRoi and final opportunity decisions. This skill does not add Trends novelty, birth windows, Rising/breakout classification, long-term monitoring, a second root library, or a Discovery database.
