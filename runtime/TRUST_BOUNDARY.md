# SEO Execution Integrity Scope

This repository protects **normal agent workflow correctness and evidence traceability**. It is designed to stop Codex/AI from accidentally skipping real collection, treating `unknown` as observed data, switching providers, advancing with incomplete stages, or claiming `COMPLETE` before the canonical workflow is satisfied.

It does **not** claim cryptographic separation from a malicious local principal that already has arbitrary shell access and can rewrite the repository and its evidence files. Building that OS-level security boundary is outside the scope of these SEO Skills.

## Production evidence boundary

Observed evidence still has strict production requirements:

- Google observations must come through the project Google live collector and include the required current screenshot / structured observation or Trends temporal payload.
- Semrush observations must come from the authenticated same-origin `sem.3ue.com` relay. Official Semrush API and alternative-provider fallback remain forbidden.
- Collector receipts bind the expected collector name, the current collector source SHA256, normalized output SHA256, and the exact required artifact roles/hashes.
- Verification replays Semrush normalization from the saved raw relay response and rechecks Google source URLs, observations, screenshots, and Trends timelines.
- A plain row containing fields such as `metric_source=Semrush` is never enough; production validation requires the complete evidence receipt and artifacts.

These controls are intended to make the expected path deterministic, auditable, and fail-closed when real observations are unavailable.

## Validation receipts

A production Stage PASS must carry a validation receipt. The receipt binds:

- canonical stage;
- candidate scope when applicable;
- current `runtime/stage_validator.py` source SHA256;
- validation report path and SHA256.

The Stop/PreToolUse hook reloads the report and reruns production evidence validation against the **current underlying evidence** before trusting the PASS. Editing a report or evidence artifact after validation therefore invalidates its hash or its semantic replay.

## Emerging route handoff

Traditional runs require their verified discovery stages.

An Emerging run may skip traditional discovery only when `route_handoff_ref` points to a structured output compatible with `emerging-keyword-monitor/scripts/route_candidates.py`. Every routed candidate must have exactly one confirmed `selection_handoff` with:

- status `emerging` or `breakout`;
- `root_relation=existing_root`;
- a non-empty `root_id`;
- matching candidate keyword.

A bare `route=emerging` is insufficient.

## Candidate lifecycle

Candidate-specific selection stages never fall back to global receipts. Every continuing candidate must own its own:

- `stage6_exact`;
- `intitle_observation`;
- `kgr_intitle`;
- `serp_review`.

After verified Exact evidence, the existing evaluator remains authoritative for deterministic early elimination. Candidates with `principle_eliminate_volume`, `principle_eliminate_kd`, or `excluded_manual` stop there and are not forced through KGR/SERP.

A candidate may terminate as `BLOCKED` only with a canonical `blocked_stage`, a matching stage record whose status is `BLOCKED`, and a non-empty real blocker reason.

Finalist Trends remains conditional. A continuing candidate must either have a verified `finalist_trend` PASS, or an explicit `finalist_review` object containing boolean `is_finalist` plus a non-empty `reason`. If `is_finalist=true`, verified Trends is mandatory before COMPLETE.

## Run-level BLOCKED

A bare run-level `status=BLOCKED` is never sufficient. A terminal blocked run requires:

- non-empty `run_id`;
- canonical `blocked_stage`;
- non-empty `blocked_reason`;
- route, when present, must be `traditional` or `emerging`.

This preserves the run-level bypass repair without requiring an external OS signer.

## Live acceptance requirement

Automated tests prove contracts, hashes, replay behavior, lifecycle gates, and fail-closed control flow. Final acceptance must separately exercise the real host integrations:

1. Google Autocomplete in a real browser/CDP session;
2. Google intitle and SERP with current screenshots/observations;
3. Google Trends with current temporal evidence;
4. authenticated `sem.3ue.com` Ideas and Exact relay collection, with no official API or fallback provider;
5. KGR from the verified Exact + intitle pair;
6. actual Codex Host `PreToolUse` and `Stop` invocation from `.codex/hooks.json`;
7. one Traditional end-to-end run;
8. one Emerging end-to-end run using a real monitor `selection_handoff`.

If a required external source or host integration is unavailable, that Live item is `BLOCKED`, never synthetically promoted to PASS.
