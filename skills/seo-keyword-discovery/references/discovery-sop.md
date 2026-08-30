# SEO Keyword Discovery SOP

This file is the migrated former `seo-keyword-selection` Steps 0–4. It changes ownership, not the SEO method.

## Step 0 — Candidate domains

Build a domain pool from interests, experience, observed markets, and prior wins. Do not use Volume/KD/CPC to eliminate domains before demand discovery.

## Step 1 — Root handoff

Obtain roots from `keyword-root-library`. Prefer relevant `verified`/`active` roots and keep new `candidate` roots separate. Never copy the canonical root CSV into this skill.

## Step 2 — Domain × root → Seed

Generate natural demand-entry Seeds. A Seed is a demand starting point, not an opportunity keyword. Avoid mechanical root permutations that create unnatural phrases.

For each run, explicitly record which Seeds are `required`. Full Traditional Discovery also requires Semrush Ideas/Related for every required Seed. Every required Seed must pass both source contracts before the batch can produce a formal handoff.

After the first-round source collection, run Step 4 low-risk cleaning, complete Candidate analysis, and only then freeze the Root/Natural Seeds handoff as a `seo-discovery-input/v1` `discovery_input_manifest` before Coverage. The manifest records the original Seed total/list, the complete set of first-round source receipts, the row ledger accounting for every row those receipts returned, the resulting Candidate inventory, and the complete analysis state for every Candidate. Cleaning must precede the freeze so the frozen denominator is provable against real receipts while the analysis workload stays bounded to kept Candidates. Obtain and retain its production validation receipt; the later Coverage ledger must match it exactly.

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

### Semrush Ideas / Related — mandatory for Full Discovery

For the default Full route, acquire Semrush Ideas/Related for every required Seed only through the current authenticated same-origin `sem.3ue.com` relay session. The request shape must be re-confirmed live from the current UI/session; historical captures are locator hints only. A Semrush block preserves any Google observation but blocks Full Coverage and formal handoff.

No official Semrush API, API key, official connector, Ahrefs, or other provider may replace relay failure.

### Domain/cluster competitor sweep

If the run explicitly configures competitor domains, acquire competitor organic keywords through the same current authenticated `sem.3ue.com` relay and record one status/evidence reference per configured domain. A configured failure is `BLOCKED`. With no domains, record `configured=false`, `status=not_configured`; this is not a fake PASS and does not block the otherwise complete Full route.

Competitor inputs must be user-provided or already verified project inputs. Discovery must not invent domains.

Other real observed sources from the old Step 3 may be retained as supplementary evidence, but they never satisfy the mandatory Google/Semrush contracts unless they are actual observations from the named source.

### Demand branch expansion

After merging the first-round candidate pool, semantic analysis may declare a required Branch Seed only by referencing an existing observed candidate. Record `branch_seed` (the exact candidate keyword), `parent_seed`, `originating_candidate_id`, `source`, `evidence_ref`, `branch_reason`, `analysis_status=required`, and depth. Depth is derived from the visited parent chain — a Root Seed is depth 0 and a Branch Seed is its parent's depth plus one — so a declared depth that contradicts the chain is rejected rather than accepted. A Branch Seed then runs real Google Autocomplete and Semrush Ideas/Related. A missing or blocked Branch Seed remains in the ledger and blocks Full Coverage.

Complete one explicit analysis record for every Candidate in the upstream manifest, including `analysis_status=COMPLETE`, `branch_required` as a boolean, and a reason. The authoritative `branch_required` decision controls whether exactly one Branch record is required; it cannot be changed in the Coverage ledger to make a missing Branch disappear. The Candidate's `source_seed`, its source receipt identity, and the Branch `parent_seed` must agree.

Do not requeue every keyword. Reject visited/cycle duplicates and enforce configurable maximum branch depth and branch count as execution safety limits.

## Step 4 — Low-risk cleaning

Deduplicate and remove clear brand/navigation terms and obvious semantic drift. Preserve `domain`, `root`, `parent_seed`, source, source detail, and evidence provenance. Do not remove a term merely because competition feels high.

Cleaning runs before the manifest freeze, and every decision is recorded in `candidate_inventory.row_ledger`: each observed row is `kept`, `dedupe_of` a kept Candidate, or `excluded` under a supported `rule_code`. A row may not simply disappear — an unaccounted row blocks the manifest. Duplicate claims are recomputed from the observed keywords rather than trusted.

AI semantic analysis is allowed here, but it cannot rewrite an AI-created phrase into an `observed` candidate without a real source observation.

## Discovery Coverage and handoff

Build one `discovery_coverage` ledger for the run. It must reconcile the upstream manifest's original Seed/Candidate totals and authoritative Candidate analysis with explicit PASS, BLOCKED, NOT_RUN, or UNKNOWN records, then report the computed counts and blockers. `Google PASS` alone is not Full Coverage. `Semrush BLOCKED`, an incomplete required Branch Seed, or a failed configured competitor sweep makes coverage `BLOCKED` while retaining prior evidence.

Only a production-verified `coverage_status=PASS` record may authorize `discovery_handoff`. The handoff validator re-verifies the exact Coverage receipt at issuance time and reconciles the handoff `keywords` list against the verified observed Candidate inventory: dropping a Candidate or adding an unverified keyword blocks issuance. The handoff contains concrete keywords and their discovery provenance and points to the exact coverage validation receipt. It may carry observed Semrush Ideas or competitor fields when they were actually returned, but it performs no Step 5 threshold decision.

A Branch Seed's own acquisition proves the branch was explored; its observed keywords do not enter this handoff. Routing them to selection requires a further Discovery round that freezes them in its own manifest.

`seo-keyword-selection` resumes at former Step 5. Rows without Ideas Volume/KD may therefore legitimately enter selection as `pending_metrics` and route to Stage 6 Exact acquisition.
