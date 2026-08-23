# Routing Rules

The monitor discovers, validates, classifies, and routes. It never makes final SEO opportunity decisions and never mutates the root library.

## Existing root

When `root_relation=existing_root`, a valid `root_id` links the candidate to `keyword-root-library` without copying its CSV.

Confirmed `emerging`/`breakout` candidates produce a `selection_handoff` containing at least:

`keyword | root_id | signal_type | first_observed_at | age_days | growth | persistence | source_count | source_evidence | volume | kd | cpc | intitle_results | metric_status | metric_provenance | metric_compatibility_status`

Metric values are not stripped from their provenance at handoff. `seo-keyword-selection` receives both compatibility fields and the traceable metric records needed to interpret them.

`new_signal`/`watch` remain monitor-only. The downstream `seo-keyword-selection` skill owns final `do_candidate`, `observe`, and `principle_eliminate` decisions.

## Root candidate

When several related queries expose a plausible new stable demand family, an analyst may set `root_relation=root_candidate` plus a reviewable `root_candidate_hypothesis` and related evidence.

`root_candidate_handoff` requires both:

- `status in {emerging, breakout}`;
- a non-empty `root_candidate_hypothesis`.

If the status is only `new_signal` or `watch`, the hypothesis is retained in `new_root_watchlist` and is not promoted into the formal root-candidate review flow yet.

The monitor never writes `root-library.csv`.

## Unresolved root

If no stable relationship is known, use `root_relation=unresolved`. The candidate goes to `new_root_watchlist` rather than receiving a guessed root.

## Non-actionable states

`mature`, `noise`, and `insufficient_evidence` do not route to selection automatically.
