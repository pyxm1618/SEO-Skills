# SEO Keyword Discovery SOP

This file is the migrated former `seo-keyword-selection` Steps 0–4. It changes ownership, not the SEO method.

## Step 0 — Candidate domains

Build a domain pool from interests, experience, observed markets, and prior wins. Do not use Volume/KD/CPC to eliminate domains before demand discovery.

## Step 1 — Root handoff

Obtain roots from `keyword-root-library`. Prefer relevant `verified`/`active` roots and keep new `candidate` roots separate. Never copy the canonical root CSV into this skill.

## Step 2 — Domain × root → Seed

Generate natural demand-entry Seeds. A Seed is a demand starting point, not an opportunity keyword. Avoid mechanical root permutations that create unnatural phrases.

For each run, explicitly record which Seeds are `required`. Every required Seed must pass the Google Autocomplete contract before the batch can produce a formal handoff.

## Step 3 — Expand concrete candidates

### Mandatory Google Autocomplete

For every required Seed:

1. open a real current Google Search page in the target country/language;
2. enter the Seed into the search input;
3. read the current visible autocomplete dropdown;
4. save `seed`, `suggestions`, `country`, `language`, `observed_at`, `source=google_autocomplete`, and `evidence_ref`;
5. validate with the `discovery_autocomplete` stage contract.

Network failure, CAPTCHA, unavailable/unconfirmed DOM, zero visible suggestions, or unprovable source blocks that required Seed and therefore the affected discovery batch/handoff.

Do not substitute AI suggestions, Bing, WebSearch snippets/results, or third-party suggestion tools.

### Semrush Ideas / Related when used

When the discovery route uses Semrush Ideas/Related, acquire it only through the current authenticated same-origin `sem.3ue.com` relay session. The request shape must be re-confirmed live from the current UI/session; historical captures are locator hints only.

No official Semrush API, API key, official connector, Ahrefs, or other provider may replace relay failure.

Other real observed sources from the old Step 3 may be retained as optional supporting discovery evidence, but they never satisfy the mandatory Google Autocomplete contract unless they are actual Google Autocomplete observations.

## Step 4 — Low-risk cleaning

Deduplicate and remove clear brand/navigation terms and obvious semantic drift. Preserve `domain`, `root`, `parent_seed`, source, source detail, and evidence provenance. Do not remove a term merely because competition feels high.

AI semantic analysis is allowed here, but it cannot rewrite an AI-created phrase into an `observed` candidate without a real source observation.

## Discovery handoff

The handoff contains concrete keywords and their discovery provenance. It may carry observed Semrush Ideas fields when they were actually returned, but it performs no Step 5 threshold decision.

`seo-keyword-selection` resumes at former Step 5. Rows without Ideas Volume/KD may therefore legitimately enter selection as `pending_metrics` and route to Stage 6 Exact acquisition.
