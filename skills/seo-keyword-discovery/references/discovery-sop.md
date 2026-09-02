# SEO Keyword Discovery SOP

This file is the migrated former `seo-keyword-selection` Steps 0–4. It changes ownership, not the SEO opportunity-selection method.

## Step 0 — Candidate domains

Build a domain pool from interests, experience, observed markets, and prior wins. Do not use Volume/KD/CPC to eliminate domains before demand discovery.

## Step 1 — Root handoff

Obtain roots from `keyword-root-library`. Prefer relevant `verified`/`active` roots and keep new `candidate` roots separate. Never copy the canonical root CSV into this skill.

## Step 2 — Domain × root → Seed

Generate natural demand-entry Seeds. A Seed is a demand starting point, not an opportunity keyword. Avoid mechanical root permutations that create unnatural phrases.

For each run, explicitly record which Seeds are `required`. Full Traditional Discovery requires three Seed-level acquisitions for every required Seed: Google Autocomplete, Google PAA/Related check, and Semrush Ideas/Related. All required acquisitions must be completed before the batch can produce a formal handoff. The PAA/Related requirement is to perform and evidence the check; a real Google page with neither block is a valid zero-result PASS.

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

### Mandatory Google People Also Ask / Related Searches check

For every required Seed, run the current live collector in `expansions` mode against a real Google result page and validate with `discovery_expansions`.

The check has three legitimate outcomes:

- `result_status=observed`: People Also Ask, Related Searches, or both returned rows. Preserve every row and reconcile it through the same candidate row ledger as other first-round sources.
- `result_status=not_present`: the real page loaded and was successfully checked, but neither block was present. Record `expansion_count=0`; this is a PASS with no rows to reconcile.
- acquisition failure or no execution: preserve `BLOCKED` or `NOT_RUN`; Full Coverage cannot pass.

Do not convert “Google returned nothing” into a blocker, and do not convert “the AI skipped the check” into a fake empty PASS.

### Semrush Ideas / Related — mandatory for Full Discovery

For the default Full route, acquire Semrush Ideas/Related for every required Seed only through the current authenticated same-origin `sem.3ue.com` relay session. The request shape must be re-confirmed live from the current UI/session; historical captures are locator hints only. A Semrush block preserves any Google observation but blocks Full Coverage and formal handoff.

No official Semrush API, API key, official connector, Ahrefs, or other provider may replace relay failure.

### Domain/cluster competitor sweep

If the run explicitly configures competitor domains, acquire competitor organic keywords through the same current authenticated `sem.3ue.com` relay and record one status/evidence reference per configured domain. A configured failure is `BLOCKED`. With no domains, record `configured=false`, `status=not_configured`; this is not a fake PASS and does not block the otherwise complete Full route.

Competitor inputs must be user-provided or already verified project inputs. Discovery must not invent domains.

Other real observed sources from the old Step 3 may be retained as supplementary evidence, but they never satisfy the mandatory Google/Semrush contracts unless they are actual observations from the named source.

### Demand branch expansion

After merging the first-round candidate pool, semantic analysis may declare a required Branch Seed only by referencing an existing observed candidate. Record `branch_seed` (the exact candidate keyword), `parent_seed`, `originating_candidate_id`, `source`, `evidence_ref`, `branch_reason`, `analysis_status=required`, and depth. Depth is derived from the visited parent chain — a Root Seed is depth 0 and a Branch Seed is its parent's depth plus one — so a declared depth that contradicts the chain is rejected rather than accepted.

Every required Branch Seed then runs the same three mandatory acquisitions as a root Seed:

1. real Google Autocomplete;
2. real Google PAA/Related check, where a genuine zero-result check is still PASS;
3. Semrush Ideas/Related.

A missing or blocked mandatory Branch acquisition remains in the ledger and blocks Full Coverage. Rows observed by Branch Autocomplete, PAA/Related, or Semrush are reconciled in `branch_row_ledger`; kept rows become `branch_candidates` and enter the final handoff.

Complete one explicit analysis record for every Candidate in the upstream manifest, including `analysis_status=COMPLETE`, `branch_required` as a boolean, and a reason. The authoritative `branch_required` decision controls whether exactly one Branch record is required; it cannot be changed in the Coverage ledger to make a missing Branch disappear. The Candidate's `source_seed`, its source receipt identity, and the Branch `parent_seed` must agree.

Do not requeue every keyword. Reject visited/cycle duplicates and enforce configurable maximum branch depth and branch count as execution safety limits.

## Step 4 — Low-risk cleaning

Deduplicate and remove clear brand/navigation terms and obvious semantic drift. Preserve `domain`, `root`, `parent_seed`, source, source detail, and evidence provenance. Do not remove a term merely because competition feels high.

Cleaning runs before the manifest freeze, and every decision is recorded in `candidate_inventory.row_ledger`: each observed row is `kept`, `dedupe_of` a kept Candidate, or `excluded` under a supported `rule_code`. A row may not simply disappear — an unaccounted row blocks the manifest. Duplicate claims are recomputed from the observed keywords rather than trusted.

AI semantic analysis is allowed here, but it cannot rewrite an AI-created phrase into an `observed` candidate without a real source observation.

## Discovery Coverage

Build one `discovery_coverage` ledger for the run. It must reconcile the upstream manifest's original Seed/Candidate totals and authoritative Candidate analysis with explicit PASS, BLOCKED, NOT_RUN, or UNKNOWN records, then report the computed counts and blockers.

Full Coverage requires every required root Seed and required Branch Seed to have:

- Google Autocomplete PASS;
- Google PAA/Related check PASS, including legitimate `result_status=not_present` zero-result checks;
- Semrush Ideas/Related PASS.

`Google Autocomplete PASS` alone is not Full Coverage. A skipped or blocked expansion check, Semrush block, incomplete required Branch Seed, or failed configured competitor sweep makes coverage `BLOCKED` while retaining prior evidence.

Only a production-verified `coverage_status=PASS` record with `formal_handoff_allowed=true` may authorize the handoff workflow.

## Google Sheet delivery and formal handoff

After Coverage PASS, construct the complete handoff JSON with the exact verified Candidate set. Before running production `discovery_handoff` validation, deliver that JSON with:

```bash
python3 skills/seo-keyword-discovery/scripts/export_to_sheet.py \
  --handoff .seo-run/discovery-handoff.json
```

The exporter uses `SEO_KEYWORD_SHEET_ID` and `SEO_SHEETS_CREDENTIALS` unless explicit CLI values are supplied. It writes to the separate `keyword_discovery` worksheet in the existing SEO keyword Spreadsheet, then reads the current batch back. Missing, extra, duplicate, partially written, or differing rows block delivery.

On exact readback the exporter writes a `seo-discovery-sheet-delivery/v1` receipt and decorates the handoff JSON with `sheet_delivery_receipt_ref`. The receipt is bound to the exact handoff content (except for its own receipt-ref field), current exporter source, batch, worksheet, and exact verified row count.

Production `discovery_handoff` validation then re-verifies both:

1. the exact `discovery_coverage` receipt and complete keyword reconciliation;
2. the Sheet-delivery receipt.

Dropping a Candidate, inventing a keyword, skipping Sheet delivery, changing the handoff after Sheet delivery, or partially writing the worksheet blocks formal handoff issuance.

A Branch Seed's acquisition is a real source like any other: its observed rows are accounted for in `branch_row_ledger`, the rows kept become `branch_candidates`, and those keywords enter the same handoff as the first-round Candidates. So a promoted demand branch delivers the keywords it found in the same run.

`seo-keyword-selection` resumes at former Step 5 only after the production handoff PASS. Rows without Ideas Volume/KD may therefore legitimately enter selection as `pending_metrics` and route to Stage 6 Exact acquisition.
