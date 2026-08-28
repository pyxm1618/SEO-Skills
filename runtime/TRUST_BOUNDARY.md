# SEO Execution Integrity Trust Boundary

Production evidence authenticity cannot be established by a secret, token, or signer stored in the same agent-writable repository or environment. A normal Codex/agent workflow can read and execute repository code, so any same-principal signing material would be forgeable.

## Trusted issuance broker

`runtime/evidence_binding.py` therefore delegates production issuance and verification to an OS-level broker at one of these fixed paths:

- `/usr/local/libexec/seo-issuance-broker`
- `/opt/openai/libexec/seo-issuance-broker`

The repository accepts only a regular, non-symlink executable that is root-owned and not group/world writable. The repository does not create or store the broker signing secret. If no trusted broker is installed, production issuance/verification fails closed.

The broker is part of the host trust boundary, not this repository. It MUST independently enforce authorization. In particular, a normal agent invoking the broker directly with a fabricated `sign` request MUST be denied. Repository-side Python stack inspection is defense in depth only and MUST NOT be treated as the authoritative security boundary.

The broker supports:

- `sign`: issue a production evidence or stage-validation proof only for an authorized collector/validator execution;
- `verify`: verify an issued proof against the expected issuer/kind/subject hash;
- `verify-attestation`: verify host-controlled workflow attestations used for facts that an agent must not self-declare.

## Workflow attestations

The Stop gate uses external attestations for workflow facts that cannot safely be accepted from `active.json` alone:

- `emerging_route`: binds `run_id`, route=`emerging`, and the exact candidate-id set to a trusted emerging-selection handoff;
- `candidate_finalist`: binds `run_id` and `candidate_id`, and carries a boolean `is_finalist` claim;
- `candidate_blocked`: binds `run_id`, `candidate_id`, terminal status `BLOCKED`, and the canonical blocked stage;
- `run_blocked`: binds `run_id`, route (or `unresolved` before route resolution), terminal status `BLOCKED`, `blocked_stage`, and the exact `blocked_reason` for a run-level terminal blocker.

Traditional route identity is established by its mandatory verified discovery stages. Emerging is allowed to skip discovery only with the trusted route attestation.

A bare run-level `status=BLOCKED` is never sufficient. Normal run-level blockers require a trusted `run_blocked` attestation, so an agent cannot skip collection or lifecycle gates merely by editing `active.json`.

There is one narrow bootstrap exception: when the trusted issuance broker itself is absent, the Stop hook may accept only the exact blocker `blocked_stage=trust_boundary` and `blocked_reason="trusted issuance broker unavailable"`, and only after directly confirming that `_trusted_broker_path()` fails for broker unavailability. This exception exists because the missing broker cannot attest its own absence. It MUST NOT be generalized to browser, Semrush, collector, data, or workflow blockers; if a trusted broker is present, the bootstrap claim is rejected.

## Candidate lifecycle

Candidate-specific selection stages never fall back to global receipts. Every candidate that continues through selection must own its own `stage6_exact`, `intitle_observation`, `kgr_intitle`, and `serp_review` validation chain.

After verified Exact evidence, the existing evaluator remains authoritative for deterministic early elimination. Candidates with `principle_eliminate_volume`, `principle_eliminate_kd`, or `excluded_manual` stop there and are not forced through KGR/SERP. A genuinely blocked candidate may also terminate without blocking other candidates, but only when its blocker is externally attested.

Finalist Trends remains conditional. The agent cannot escape it by writing `is_finalist=false`: finalist disposition must either be demonstrated by a verified `finalist_trend` stage or by a trusted candidate-finalist attestation.

## Acceptance requirement

Automated tests without the host broker may prove fail-closed behavior and mechanism regressions, but they cannot prove Live issuance. Final acceptance must separately demonstrate:

1. the real broker is installed at an allowed OS path with correct ownership/mode;
2. normal agent code cannot read signing material;
3. a direct agent `sign` request is denied;
4. direct CLI collector/validator execution can obtain valid issuance only when authorized by the broker;
5. broker verification rejects forged/tampered proofs;
6. route/finalist/candidate-blocker/run-blocker attestations are bound to the claimed run/candidate state;
7. a bare or tampered run-level `BLOCKED` claim is denied;
8. a valid `run_blocked` attestation is accepted only for the exact bound route/stage/reason;
9. the broker-missing bootstrap exception succeeds only when the trusted broker is actually unavailable and is rejected when the broker exists.

If these host checks cannot be performed, broker-dependent Live acceptance is `BLOCKED`, not `PASS`.
