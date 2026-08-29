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

An Emerging run may skip traditional discovery only when `emerging_pipeline_receipt_ref` points to a `seo-emerging-pipeline/v1` receipt produced by `runtime/emerging_pipeline.py`. The receipt binds:

- the original observation input path and SHA256 plus the fixed `as_of` time;
- the current `emerging_pipeline.py`, all four monitor scripts, and `references/thresholds.json` SHA256 values;
- the validated, aggregated, classified, and routed output paths and SHA256 values.

The Hook reloads every file, checks every hash, replays `validate_observations.py -> aggregate_signals.py -> classify_emergence.py -> route_candidates.py` with the recorded `as_of`, and compares every saved JSON output with the replay. `route_handoff_ref` must point to that receipt's routed output. A bare routes JSON, even with a plausible handoff shape, is not an attestation.

Every routed `selection_handoff` candidate must have exactly one manifest candidate with:

- status `emerging` or `breakout`;
- `root_relation=existing_root`;
- a non-empty `root_id`;
- matching candidate keyword.

Only `net_new`, `breakout`, `emerging_variant`, and `unknown` are canonical `signal_type` values; a confirmed handoff must carry a non-`unknown` canonical value. A complete pipeline that honestly produces `no_handoff` is valid monitor evidence and must remain `no_handoff`; it does not require a fabricated candidate. A bare `route=emerging` or a direct `status=emerging` input is insufficient.

## Candidate lifecycle

Candidate-specific selection stages never fall back to global receipts. Every continuing candidate must own its own:

- `stage6_exact`;
- `intitle_observation`;
- `kgr_intitle`;
- `serp_review`.

For `stage6_exact`, `intitle_observation`, `kgr_intitle`, `serp_review`, and `finalist_trend`, the production validator must be called with `--candidate-id <id>` and the protected command must contain the literal `SEO_CANDIDATE_ID=<id>`. The validator derives `candidate_keyword` from exactly one complete row and writes it to both the validation report and receipt. The Hook compares that normalized value with `manifest.candidates[<id>].keyword`; missing, duplicate, or mismatched rows fail closed. Global discovery receipts must not carry candidate identity.

After verified Exact evidence, the existing evaluator remains authoritative for deterministic early elimination. Candidates with `principle_eliminate_volume`, `principle_eliminate_kd`, or `excluded_manual` stop there and are not forced through KGR/SERP.

A candidate may terminate as `BLOCKED` only with a canonical `blocked_stage`, a matching stage record whose status is `BLOCKED`, and a non-empty real blocker reason.

Finalist Trends remains conditional. A continuing candidate must either have a verified `finalist_trend` PASS, or an explicit `finalist_review` object containing boolean `is_finalist` plus a non-empty `reason`. If `is_finalist=true`, verified Trends is mandatory before COMPLETE.

## Run-level BLOCKED

A bare run-level `status=BLOCKED` is never sufficient. A terminal blocked run requires:

- non-empty `run_id`;
- canonical `blocked_stage`;
- non-empty `blocked_reason`;
- route, when present, must be `traditional` or `emerging`;
- the same canonical stage must exist in the run's `stages` map with `status=BLOCKED`;
- that stage record must contain the same non-empty `blocked_reason`.

This preserves the run-level bypass repair without requiring an external OS signer: a run cannot stop merely by inventing top-level blocker fields; it must first record the blocker on the stage that actually failed.

## Live acceptance requirement

Automated tests prove contracts, hashes, replay behavior, lifecycle gates, and fail-closed control flow. Live acceptance separately exercises the real integrations without requiring external services or market conditions to behave deterministically.

The release acceptance set is:

1. Google Autocomplete in a real browser/CDP session;
2. Google intitle and SERP through the real Google collector;
3. Google Trends with real temporal evidence;
4. authenticated `sem.3ue.com` Ideas and Exact relay collection, with no official API or fallback provider;
5. KGR from the verified Exact + intitle pair;
6. actual Agent Host `PreToolUse` and `Stop` invocation from that host's reviewed/trusted project hook configuration, for **every** host the release covers;
7. one Traditional workflow exercising a deterministic early-elimination candidate and the continuing-candidate gates as far as the external sources permit;
8. one Emerging Monitor run using **real temporal observations** through `validate_observations.py -> aggregate_signals.py -> classify_emergence.py -> route_candidates.py`.

### Agent Host acceptance

These Skills are host-neutral; their hook wiring is not. Each host reads only its own configuration, so a host that was never wired runs the SEO method with the integrity gates **inert** — the protection appears present and enforces nothing. Host acceptance is therefore recorded **per host**, and a host without its own recorded Host acceptance is not a released host, however green the automated suite is.

Known host configurations:

- Claude Code — `.claude/settings.json` (`PreToolUse`, `Stop`, `SubagentStop`);
- Codex — `.codex/hooks.json` (`PreToolUse`, `Stop`).

For each host the release covers:

- project-local hooks must be reviewed and trusted in that host before its smoke test;
- the smoke test must demonstrate **automatic** invocation by the host, not a manual run of `runtime/codex_stage_hook.py`;
- it must be exercised from both the repository root and a repository subdirectory, so relative working-directory assumptions cannot silently disable the gate;
- every event through which that host could reach run completion must be gated. Claude Code's `Stop` does not fire for subagents, so `SubagentStop` is required there and is proven separately; a host with an equivalent delegation path needs the equivalent proof.

A further host may be added only once its own hook configuration exists and its Host acceptance is recorded. Copying the Skills into a host that has no equivalent hook mechanism ships the SEO method without its execution-integrity guarantees; such a host may be documented as unsupported, but must not be presented as a released host.

The Hook normalizes only a matching copy of Bash input, including backslash-newline continuations and repeated whitespace. The command passed to the tool is not changed. Single-line, multiline, `&&`, and directory-prefixed equivalent protected commands must resolve to the same prerequisite stage.

### Emerging acceptance semantics

Live acceptance must not manufacture an `emerging` or `breakout` result just to force a `selection_handoff`.

A real-data Emerging E2E is successful when real temporal observations pass through the complete Monitor pipeline and the resulting classification and route are consistent with the configured rules. Honest outcomes such as `watch`, `insufficient_evidence`, `monitor_only`, or `no_handoff` are valid Live outcomes when that is what the evidence supports. The positive `emerging/breakout -> selection_handoff` branch remains covered by deterministic regression tests and may additionally be demonstrated Live when the real evidence naturally produces such a candidate.

### Accepted external-environment blocker

A third-party source can block a Live request for reasons outside repository control, for example Google returning a CAPTCHA / `/sorry/` abnormal-traffic page. Such an event is never called `PASS`, but it may be recorded as `ACCEPTED_ENVIRONMENT_BLOCKER` for **release acceptance** when all of the following are true:

- the real collector reached the intended external source and captured the blocker evidence;
- the blocker is demonstrably external rather than a parser/contract bug;
- no mock, synthetic data, official Semrush API, alternative SEO provider, or other fallback was used;
- the collector and downstream workflow fail closed rather than fabricating or advancing with incomplete evidence;
- targeted regression tests cover the relevant parser/extractor behavior; and
- there is no open P0/P1 indicating that valid source data would be accepted incorrectly or that required gates can be bypassed.

`ACCEPTED_ENVIRONMENT_BLOCKER` means the software correctly handled an unavailable external dependency. It does **not** turn the blocked observation into evidence and does not allow that individual production run to continue past the blocked stage.

## Release decision

A release candidate may be recommended for merge when:

- the repository-wide automated suite and compile checks pass;
- P0 = 0 and P1 = 0;
- Semrush relay-only policy and evidence provenance remain intact;
- Host acceptance passes for every host the release covers;
- the real-data Emerging Monitor pipeline passes under the semantics above; and
- any remaining Live source failure is only an `ACCEPTED_ENVIRONMENT_BLOCKER` meeting every condition above.

A real code defect, unverifiable provenance, provider fallback, fabricated observation, missing Host enforcement, or open P0/P1 remains `DO NOT MERGE`.
