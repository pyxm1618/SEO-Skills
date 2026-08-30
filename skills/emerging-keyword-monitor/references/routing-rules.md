# Routing Rules

The monitor discovers, validates, classifies, and routes. It never makes final SEO opportunity decisions and never mutates the root library.

## Existing root

When `root_relation=existing_root`, a valid `root_id` links the candidate to `keyword-root-library` without copying its CSV.

Confirmed `emerging`/`breakout` candidates produce a `selection_handoff` containing at least:

`domain | keyword | root_id | signal_type | demand_history_type | estimated_birth_window | birth_source_resolution | birth_reason | first_observed_at | age_days | growth | persistence | source_count | source_evidence | volume | kd | cpc | intitle_results | metric_status | metric_provenance | metric_compatibility_status | kgr_compatibility_status | discovery_depth | parent_anchor | google_rising_label`

That handoff enters `seo-keyword-selection` **directly**. It must never route through `seo-keyword-discovery`; never rerun Seed generation, Google Autocomplete, or Semrush Ideas for the confirmed keyword.

Selection reuses compatible fresh handoff evidence. Any missing/incompatible evidence is acquired beginning at the earliest missing **selection** contract (for example Stage 6 Exact, `intitle`, SERP, or finalist Trends), not by restarting discovery.

Discovery provenance and history annotations travel with the handoff, but they do not make a selection decision. A Google `Breakout` label remains an observed source fact, and `preexisting`/`resurgent` history remains visible to selection as context; neither is converted into a downstream decision by this monitor.

Metric values are not stripped from provenance. `metric_compatibility_status` describes the core `volume + kd + cpc` context, while `kgr_compatibility_status` separately describes the `volume + intitle_results` pairing used for KGR.

`new_signal`/`watch` remain monitor-only. The downstream selection skill owns final `do_candidate`, `observe`, and `principle_eliminate` decisions.

## Root candidate

When several related queries expose a plausible new stable demand family, an analyst may set `root_relation=root_candidate` plus a reviewable `root_candidate_hypothesis` and related evidence.

`root_candidate_handoff` requires both:

- `status in {emerging, breakout}`;
- a non-empty `root_candidate_hypothesis`.

If the status is only `new_signal` or `watch`, retain the hypothesis in `new_root_watchlist` rather than promoting it.

The monitor never writes `root-library.csv`.

## Unresolved root

If no stable relationship is known, use `root_relation=unresolved`. The candidate goes to `new_root_watchlist` rather than receiving a guessed root.

## Non-actionable states

`mature`, `noise`, and `insufficient_evidence` do not route to selection automatically.
