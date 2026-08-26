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

When used, retain at least:

`seed | rows | observed_at | metric_source | relay_origin | provenance_ref`

Rules:

- `metric_source=Semrush`;
- `relay_origin` host is exactly `sem.3ue.com`;
- current HTTP/RPC request and response shape must have been live verified in the authenticated same-origin session;
- missing metrics remain missing/unknown and do not become zero.

## Candidate handoff fields

Preserve as available:

`keyword | domain | root | parent_seed | source | source_detail | observed_at | evidence_ref`

If Semrush Ideas returned observed fields, those fields may pass through with their provenance. The discovery handoff does not convert them into Exact evidence and does not make selection decisions.

## Batch completion

For the mandatory Google source retain:

`batch_id | required_seed_count | autocomplete_pass_count | status`

A formal handoff requires `status=PASS` and equality of `required_seed_count` and `autocomplete_pass_count`. Blocked required Seeds must remain visible in the run report with their reason; they may not be silently removed.
