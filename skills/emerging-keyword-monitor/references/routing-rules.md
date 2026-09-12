# Routing Rules

The monitor discovers, validates, classifies, and routes. It never makes the final SEO opportunity decision and never mutates the root library.

## Preconditions for any formal route

A candidate may enter canonical routing only when all of the following are true:

- `domain_relation=in_scope`;
- required temporal acquisition completed with `acquisition_status=data_acquired`;
- required evidence is verified (`verification_status=verified`);
- the candidate has a stable `candidate_id` in the current run ledger;
- canonical temporal classification actually ran for that same identity.

A candidate that is `unknown`, `out_of_scope`, `failed`, `not_attempted`, `valid_no_data`, or `pending_evidence` remains auditable but cannot be promoted into a formal downstream handoff merely because it looks commercially interesting.

Canonical reconciliation must satisfy:

`delivery_ids ⊆ route_ids = classified_ids ⊆ candidate_ids`.

## Existing root

When `root_relation=existing_root`, a valid `root_id` links the candidate to `keyword-root-library` without copying or mutating its CSV.

A verified root relationship is inherited through recursive Google Trends Rising discovery. Descendants retain the verified `root_id/root_relation` unless an explicit later review changes that relationship.

Only confirmed `status in {emerging, breakout}` may produce `selection_handoff`.

That handoff enters `seo-keyword-selection` directly. It must not restart keyword discovery for the same confirmed candidate.

The handoff preserves temporal evidence/provenance and may also carry already-existing compatible commercial metrics. Emerging does not create missing Volume/KD/CPC/KDRoi/KGR/ SERP metrics; Selection owns those acquisitions and decisions.

Google's source-side `Breakout` label and demand-history context such as `preexisting`/`resurgent` remain evidence/context only. They do not create the downstream decision by themselves.

`new_signal` and `watch` remain monitor-only even if they look promising.

## Root candidate

`root_candidate_handoff` requires both:

- confirmed `status in {emerging, breakout}`;
- a non-empty, reviewable `root_candidate_hypothesis`.

If the status is only `new_signal` or `watch`, retain the hypothesis in `new_root_watchlist`.

The monitor never writes `root-library.csv`.

## Unresolved root

If no stable relationship is known, use `root_relation=unresolved`. Do not guess a root merely to force a handoff.

## Non-actionable temporal states

`mature`, `noise`, and `insufficient_evidence` do not route to Selection automatically.

`mature` means established demand, not “平稳”; it remains a temporal classification, not a delivery instruction.

## BLOCKED run delivery

A `BLOCKED` run performs zero production Sheet mutation and no production delivery handoff. Review artifacts may still describe what would have been eligible once blockers are resolved, but they are not production writes.
