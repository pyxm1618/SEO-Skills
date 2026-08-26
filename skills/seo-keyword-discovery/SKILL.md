---
name: seo-keyword-discovery
description: Use when reusable demand roots must be turned into concrete keyword candidates through real Google Autocomplete and, when used, current Semrush relay discovery before keyword selection begins.
---

# SEO Keyword Discovery

Own the former `seo-keyword-selection` Steps 0–4 only: candidate-domain context, root handoff, Seed generation, real keyword expansion, and low-risk cleaning. Produce a discovery handoff of concrete keywords; do not make final opportunity decisions.

## Boundaries

- Upstream: `keyword-root-library` supplies roots.
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

If Semrush Ideas/Related is used, current acquisition must use the authenticated same-origin `sem.3ue.com` relay collector. There is no official API, API-key, connector, Ahrefs, or alternative-provider fallback.

Historical captured endpoints may help locate the current UI request but are not current evidence. A relay request becomes usable only after current live HTTP/RPC success and response-shape verification.

## Evidence discipline

Preserve `observed`, `calculated`, `analysis`, and `unknown`. Missing, invalid, numeric zero, and `not_applicable` are distinct states. AI may analyze or clean observed candidates but may not manufacture observed keyword suggestions or metrics.

## Completion

A formal `discovery_handoff` exists only when every mandatory required-Seed acquisition contract passes and any configured mandatory discovery source has current provenance. If a mandatory Seed/source fails, mark the affected discovery batch `BLOCKED`; do not silently shrink the handoff.
