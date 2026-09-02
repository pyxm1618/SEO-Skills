# Discovery Data Contracts

## Data states

Use the existing four semantic kinds only:

- `observed` — produced by a real collector/source;
- `calculated` — deterministic output from observed inputs;
- `analysis` — semantic/intent/quality interpretation;
- `unknown` — genuinely unavailable.

Do not add a fifth semantic kind. Separately preserve these value states:

- missing: field absent/unavailable;
- invalid: supplied value malformed or impossible;
- `0`: a real observed/calculated numeric zero;
- `not_applicable`: the field does not apply.

They are not interchangeable and must not be coerced into one another.

## Google Autocomplete observation

Required fields:

`seed | suggestions | country | language | observed_at | source | evidence_ref`

Rules:

- `source` must be `google_autocomplete`;
- `suggestions` must contain at least one current visible dropdown suggestion;
- a required Seed with zero suggestions is `BLOCKED`, not a successful empty observation;
- source/evidence must come from the project live Google collector.

## Google PAA/Related observation

Required fields:

`seed | people_also_ask | related_searches | expansion_count | result_status | market | language | observed_at | source | evidence_ref`

Rules:

- `source` must be `google_serp_expansions`;
- every required Seed and Branch Seed must run the check;
- `result_status=observed` means at least one PAA or Related Search row was observed;
- `result_status=not_present` is valid only when the real Google result page was successfully checked and both observed lists are empty; `expansion_count` is then the real numeric zero;
- `NOT_RUN` and acquisition failure are not equivalent to `not_present` and block Full Coverage;
- observed rows enter the same row-accounting system as other Discovery sources.

The requirement is therefore “must check”, not “Google must display the blocks”.

## Semrush Ideas/Related observation

For Full Traditional Discovery, retain at least:

`seed | rows | observed_at | metric_source | relay_origin | provenance_ref`

Rules:

- `metric_source=Semrush`;
- `relay_origin` host is exactly `sem.3ue.com`;
- current HTTP/RPC request and response shape must have been live verified in the authenticated same-origin session;
- missing metrics remain missing/unknown and do not become zero.

## Semrush competitor organic observation

The domain/cluster competitor sweep uses the existing current relay collector with:

`competitor_domain | rows | observed_at | metric_source | metric_database | metric_stage | relay_origin | provenance_ref`

`metric_stage` is `competitor_organic`; `relay_origin` must be `sem.3ue.com`; rows and any returned metrics remain observed with the raw-response receipt. No competitor domain may be synthesized by the Agent.

## Candidate handoff fields

Preserve as available:

`candidate_id | keyword | domain | root | parent_seed | source_seed | source | source_detail | observed_at | evidence_ref | evidence_receipt_ref`

If Semrush Ideas returned observed fields, those fields may pass through with their provenance. The discovery handoff does not convert them into Exact evidence and does not make selection decisions.

## Upstream input manifest

Before a Full Coverage ledger is evaluated, the Root/Natural Seeds handoff is frozen as a `seo-discovery-input/v1` manifest and receives a production `discovery_input_manifest` validation receipt. It contains:

`schema | batch_id | root_handoff_receipt_ref | root_handoff_receipt_sha256 | seed_plan | source_receipts | candidate_inventory | candidate_analysis`

`seed_plan` contains `original_seed_count` and the complete ordered `seeds` list. `candidate_inventory` contains `original_candidate_count` and the complete observed Candidate records, including `candidate_id`, `keyword`, `source`, `source_seed`, and `evidence_receipt_ref`. `candidate_analysis` contains exactly one record per Candidate: `candidate_id | analysis_status | branch_required | analysis_reason`. The referenced Root/Natural Seeds receipt must be a `seo-root-natural-seeds/v1` PASS object whose `batch_id` and exact `seed_plan` match the manifest. Coverage compares the current ledger to this receipt; missing, extra, reordered, or rewritten items are blocked. Production also requires the manifest/report hashes and validator source hash to match.

## Source receipts and the row ledger

`source_receipts` is the complete set of first-round acquisition receipts the manifest is signed against. Each record carries `evidence_type`, the acquisition identity (`seed`, or `competitor_domain` for a competitor sweep), and `evidence_receipt_ref`.

The binding is enforced in both directions. Every Candidate's `evidence_receipt_ref` must appear in this set, and Coverage requires every passing first-round mandatory acquisition to be frozen here: each required Seed's Google Autocomplete receipt, Google PAA/Related receipt, and Semrush receipt, plus each configured competitor domain's receipt. A valid zero-result PAA/Related receipt is still frozen even though it contributes no rows. Otherwise a whole source could pass on its own receipt while escaping Coverage accounting. Branch Seed receipts are not in this set because a Branch Seed does not exist when the manifest is signed; they are reconciled in the Coverage ledger instead.

`candidate_inventory.row_ledger` accounts for **every row those receipts actually returned**. It holds one record per receipt with an ordered `rows` list that must equal the receipt's observed rows exactly, in order. A zero-result PAA/Related receipt has no observed keyword rows and therefore contributes no Candidate rows. Each non-empty row declares one `disposition`:

- `kept` — becomes a Candidate; `candidate_id` must resolve to an inventory Candidate whose keyword equals the row and whose `evidence_receipt_ref` is this receipt. A Candidate is kept exactly once.
- `dedupe_of` — the row repeats a kept Candidate; `candidate_id` must resolve to a Candidate holding the **same normalized keyword**. Production recomputes this relation instead of trusting the declaration.
- `excluded` — removed by Step 4 low-risk cleaning; requires a `rule_code` of `brand_or_navigation`, `semantic_drift`, or `non_target_language_or_market`, plus a `reason`.

There is deliberately no opportunity-shaped exclusion code. Volume, difficulty, and competition judgements belong to selection, not to Discovery cleaning.

The Candidate inventory is the denominator for the whole run. Because the row ledger must balance against real receipts, rows cannot be curated away before signing: a dropped row blocks the manifest instead of shrinking the denominator. Production verifies each receipt through the existing evidence binding before reconciling its rows.

## Coverage ledger

The run ledger records:

`batch_id | discovery_mode | upstream_input | required_seeds | observed_candidates | candidate_analysis | required_branch_seeds | branch_candidates | branch_row_ledger | competitor_sweep | other_mandatory_sources | max_branch_depth | max_branch_seeds`

`observed_candidates` stays exactly equal to the frozen manifest inventory. Branch acquisitions happen after the freeze, so their output lives in `branch_candidates`, reconciled by `branch_row_ledger` under the same row-accounting rules as the manifest: every row a branch receipt returned is `kept`, `dedupe_of` an existing candidate, or `excluded` under a supported `rule_code`, and every Branch candidate must be the `kept` target of a real branch row. Each Branch candidate's `source_seed` must be a Branch Seed that completed in this run. A Branch may still only originate from a first-round Candidate carrying an authoritative `branch_required=true`.

Each required Seed and Branch Seed has nested `autocomplete`, `expansions`, and (for Full Discovery) `semrush` records with `status` and an evidence receipt on PASS. Non-PASS records retain a reason. `expansions.status=PASS` may represent either observed rows or a verified `result_status=not_present` zero-result check. Missing `expansions`, `NOT_RUN`, `BLOCKED`, or `UNKNOWN` cannot satisfy Full Coverage.

`source_seed` binds an observed Candidate to the Seed that produced its receipt; production validation checks that receipt's original Seed. A Branch Seed must match one Candidate's exact normalized keyword, source, and evidence reference, and its `parent_seed` must equal that Candidate's `source_seed`. A Branch cannot be its own parent, point to a future/unvisited node, or bypass the authoritative `branch_required` decision.

Each `other_mandatory_sources` PASS record must declare a supported `evidence_type` and a receipt. Production verifies the receipt's file, evidence type, collector, collector source hash, normalized hash, and required artifacts through the existing evidence binding.

## Coverage summary

The validator computes and exposes at least:

`required_seed_count | autocomplete_pass_count | expansions_required_count | expansions_pass_count | semrush_required_count | semrush_pass_count | required_branch_seed_count | branch_seed_pass_count | branch_expansions_required_count | branch_expansions_pass_count | branch_candidate_count | competitor_sweep_configured | competitor_sweep_status | coverage_status | blocked_reasons | formal_handoff_allowed`

Full Coverage requires equality of every mandatory-source total and pass count, including the PAA/Related check total, a PASS `discovery_coverage` validation receipt, and `formal_handoff_allowed=true`. Blocked/NOT_RUN/UNKNOWN items remain visible; they may not be silently removed to make counts equal.

## Formal handoff and Google Sheet delivery

A formal `discovery_handoff` carries `coverage_status=PASS`, the exact `coverage_receipt_ref`, and a `keywords` list whose items each declare:

`candidate_id | keyword | source | source_seed | evidence_receipt_ref`

Production reconciles that list against the verified Coverage record: it must cover the first-round Candidate inventory **and** the reconciled Branch candidates exactly, so the handoff can neither drop a Candidate nor introduce a keyword Coverage never verified.

Before production handoff validation, the exact handoff is exported to the existing SEO Google Spreadsheet, separate worksheet `keyword_discovery`. The exporter reads the current batch back and requires exact equality. A successful delivery writes a receipt with:

`schema | status | batch_id | worksheet | sheet_id | record_count | verified_count | handoff_binding_sha256 | exporter_source_sha256 | verified_at`

where `schema=seo-discovery-sheet-delivery/v1`, `status=PASS`, `worksheet=keyword_discovery`, and `record_count=verified_count=len(handoff.keywords)`. The exporter then adds `sheet_delivery_receipt_ref` to the handoff JSON.

The binding hash covers the complete handoff content except the `sheet_delivery_receipt_ref` field itself, allowing the receipt to be created first and then referenced without a circular hash. Production handoff validation re-computes that binding, verifies the current exporter source hash, exact batch and row counts, and the receipt file. A missing Sheet receipt, partial write, extra/missing/duplicate current-batch row, or handoff mutation after delivery blocks production handoff PASS.

JSON remains the machine-authoritative handoff/evidence artifact. Google Sheet delivery is mandatory for completion. CSV is optional and is not a formal output contract.
