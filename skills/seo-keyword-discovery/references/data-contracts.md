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

`schema | batch_id | root_handoff_receipt_ref | root_handoff_receipt_sha256 | seed_plan | candidate_inventory | candidate_analysis`

`seed_plan` contains `original_seed_count` and the complete ordered `seeds` list. `candidate_inventory` contains `original_candidate_count` and the complete observed Candidate records, including `candidate_id`, `keyword`, `source`, `source_seed`, and `evidence_receipt_ref`. `candidate_analysis` contains exactly one record per Candidate: `candidate_id | analysis_status | branch_required | analysis_reason`. The referenced Root/Natural Seeds receipt must be a `seo-root-natural-seeds/v1` PASS object whose `batch_id` and exact `seed_plan` match the manifest. Coverage compares the current ledger to this receipt; missing, extra, reordered, or rewritten items are blocked. Production also requires the manifest/report hashes and validator source hash to match.

## Coverage ledger

The run ledger records:

`batch_id | discovery_mode | upstream_input | required_seeds | observed_candidates | candidate_analysis | required_branch_seeds | competitor_sweep | other_mandatory_sources | max_branch_depth | max_branch_seeds`

Each required Seed and Branch Seed has nested `autocomplete` and (for Full Discovery) `semrush` records with `status` and an evidence receipt on PASS. Non-PASS records retain a reason. `source_seed` binds an observed Candidate to the Seed that produced its receipt; production validation checks that receipt's original Seed. A Branch Seed must match one Candidate's exact normalized keyword, source, and evidence reference, and its `parent_seed` must equal that Candidate's `source_seed`. A Branch cannot be its own parent, point to a future/unvisited node, or bypass the authoritative `branch_required` decision.

Each `other_mandatory_sources` PASS record must declare a supported `evidence_type` and a receipt. Production verifies the receipt's file, evidence type, collector, collector source hash, normalized hash, and required artifacts through the existing evidence binding.

## Coverage summary and handoff

The validator computes and exposes:

`required_seed_count | autocomplete_pass_count | semrush_required_count | semrush_pass_count | required_branch_seed_count | branch_seed_pass_count | competitor_sweep_configured | competitor_sweep_status | coverage_status | blocked_reasons | formal_handoff_allowed`

Full Coverage requires equality of every mandatory source total and pass count, a PASS `discovery_coverage` validation receipt, and `formal_handoff_allowed=true`. A formal `discovery_handoff` must carry `coverage_status=PASS` and the exact `coverage_receipt_ref`. Blocked/NOT_RUN/UNKNOWN items remain visible; they may not be silently removed to make counts equal.
