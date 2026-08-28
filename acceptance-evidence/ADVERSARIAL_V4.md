# Adversarial Integrity Test Suite V4 Report

Re-acceptance against commit `82b0e61a5cd76eb04bb32115c64e500e37ae51c3`.
Executed via `acceptance-evidence/p1_attack_runner_v4.py`.

---

## 1. Summary Matrix

| Test ID | Category | Target Gate | Prereq Passed | Target Gate Hit | Verdict |
|---|---|---|---|---|---|
| **P1-A** | Fake Semrush Receipt | Production Validator Issuance Gate | YES | YES | **PASS** |
| **P1-F** | Fake Google intitle | Production Validator Issuance Gate | YES | YES | **PASS** |
| **P1-G** | Fake Google Trends | Production Validator Issuance Gate | YES | YES | **PASS** |
| **P1-H** | Post-Validation Tampering | Validation Receipt Binding & Evidence Replay | NO (Broker Absent) | NO | **BLOCKED** |
| **P1-L** | Finalist=false Spoof | Candidate Finalist Disposition Gate | YES | YES | **PASS** |
| **P1-O** | Exact Early Elimination Stop | Lifecycle Completion Gate | YES | YES | **PASS** |
| **P1-P** | Mixed BLOCKED + COMPLETE Batch | Multi-Candidate Lifecycle Resolution Gate | YES | YES | **PASS** |
| **P1-Q** | Run-Level Bare BLOCKED | Hook Stop `_verify_blocked_run` Gate | YES | YES | **PASS** |
| **P1-R** | Fake Run Blocker | Hook Stop Run Blocker Attestation Gate | YES | YES | **PASS** |
| **P1-S** | Attested Run Blocker Claim Binding | `verify_external_attestation` Exact Claim Match | YES | YES | **PASS** |
| **P1-T** | Broker-Unavailable Bootstrap Exception | `_verify_blocked_run` Bootstrap Check Gate | YES | YES | **PASS** |
| **P1-B** | Direct Helper Minting | `_assert_issuance_mint_caller` | YES | YES | **PASS** |
| **P1-C** | `SEO_ISSUANCE_SECRET` Env Injection | External Broker Trust Boundary | YES | YES | **PASS** |
| **P1-D** | `.seo-run/.issuance_secret` Workspace Secret | External Broker Trust Boundary | YES | YES | **PASS** |
| **P1-E** | Emerging Route Spoofing | Route Attestation Gate | YES | YES | **PASS** |
| **P1-I** | Candidate Global Receipt Fallback | Candidate Stage Scope Enforcement Gate | YES | YES | **PASS** |
| **P1-K** | Marker Spoofing Override | Command-Derived Protected Transition Priority | YES | YES | **PASS** |
| **P1-M** | Bare `status=COMPLETE` | `_verify_completion_requirements` Gate | YES | YES | **PASS** |

- **Total Adversarial Tests**: 18
- **PASS**: 17
- **FAIL**: 0
- **BLOCKED**: 1 (`P1-H`: genuine broker missing on host)
- **INVALID**: 0

---

## 2. Detailed Test Cases

### P1-A: Complete Fake Semrush Receipt Authenticity Rejection
```text
Test: P1-A
Purpose: Verify that a structurally complete Semrush exact evidence payload with valid schema, artifact hashes, and deterministic raw-response replay is rejected at production validation solely due to untrusted issuance proof.
Preconditions: Non-production schema/contract validation PASSES (0 errors).
Target gate: Production stage validator authenticity / issuance proof verification gate.
Command: python3 runtime/stage_validator.py --stage stage6_exact --input stage6_exact.json --report stage6_exact.report.json --production
Exit code: 2
Relevant stdout: 
Relevant stderr: 
Did prerequisite gates pass? YES
Was the intended target gate reached? YES
Evidence: Passed schema checks, blocked at authenticity/issuance gate: ['evidence receipt issuance proof invalid: trusted issuance broker unavailable; install a root-owned non-writable seo-issuance-broker at /usr/local/libexec or /opt/openai/libexec']
Verdict: PASS
```

---

### P1-F: Complete Fake Google intitle Authenticity Rejection
```text
Test: P1-F
Purpose: Verify that a structurally complete Google intitle payload with valid PNG screenshot artifact and structured observation is rejected at production validation due to untrusted issuance proof.
Preconditions: Non-production schema/contract validation PASSES (0 errors).
Target gate: Production stage validator authenticity / issuance proof verification gate.
Command: python3 runtime/stage_validator.py --stage intitle_observation --input intitle.json --report intitle.report.json --production
Exit code: 2
Relevant stdout: 
Relevant stderr: 
Did prerequisite gates pass? YES
Was the intended target gate reached? YES
Evidence: Passed schema checks, blocked at authenticity/issuance gate: ['evidence receipt issuance proof invalid: trusted issuance broker unavailable; install a root-owned non-writable seo-issuance-broker at /usr/local/libexec or /opt/openai/libexec']
Verdict: PASS
```

---

### P1-G: Complete Fake Google Trends Authenticity Rejection
```text
Test: P1-G
Purpose: Verify that a structurally complete Google Trends payload with valid temporal JSON timeline payload, PNG screenshot, and series replay is rejected at production validation due to untrusted issuance proof.
Preconditions: Non-production schema/contract validation PASSES (0 errors).
Target gate: Production stage validator authenticity / issuance proof verification gate.
Command: python3 runtime/stage_validator.py --stage finalist_trend --input trends.json --report trends.report.json --production
Exit code: 2
Relevant stdout: 
Relevant stderr: 
Did prerequisite gates pass? YES
Was the intended target gate reached? YES
Evidence: Passed schema checks, blocked at authenticity/issuance gate: ['evidence receipt issuance proof invalid: trusted issuance broker unavailable; install a root-owned non-writable seo-issuance-broker at /usr/local/libexec or /opt/openai/libexec']
Verdict: PASS
```

---

### P1-H: Post-Validation Tampering
```text
Test: P1-H
Purpose: Verify that modifying evidence artifacts after validation receipt issuance causes the Stop hook / validator to deny execution.
Preconditions: Requires genuine broker and authentic production receipts.
Target gate: Hook validation receipt binding & evidence replay gate.
Command: N/A (Host broker missing)
Exit code: 0
Relevant stdout: 
Relevant stderr: 
Did prerequisite gates pass? NO (Broker absent)
Was the intended target gate reached? NO
Evidence: Host issuance broker is not installed at /usr/local/libexec or /opt/openai/libexec; cannot acquire genuine production receipt. Must fail closed.
Verdict: BLOCKED
```

---

### P1-L: Finalist=false Spoof Isolation Test
```text
Test: P1-L
Purpose: Verify that setting is_finalist=false without an external candidate_finalist attestation fails specifically at the finalist disposition gate after all prerequisite stages (Discovery, Exact, intitle, KGR, SERP) have successfully passed.
Preconditions: Shared discovery, stage6_exact, intitle, KGR, SERP all PASS; is_finalist=false without attestation.
Target gate: Candidate finalist disposition / external attestation gate.
Command: hook._verify_completion_requirements(manifest)
Exit code: 2
Relevant stdout: 
Relevant stderr: candidate=cand_1 finalist disposition is not trusted: trusted candidate_finalist attestation missing or invalid
Did prerequisite gates pass? YES
Was the intended target gate reached? YES
Evidence: Discovery, Exact, intitle, KGR, SERP passed; blocked specifically at finalist disposition: candidate=cand_1 finalist disposition is not trusted: trusted candidate_finalist attestation missing or invalid
Verdict: PASS
```

---

### P1-O: Exact Early Elimination Full Stop Lifecycle
```text
Test: P1-O
Purpose: Verify that a candidate deterministically eliminated after Exact (e.g. principle_eliminate_kd) cleanly terminates without requiring intitle/KGR/SERP/Trends stages and allows the run to COMPLETE.
Preconditions: stage6_exact derived status=principle_eliminate_kd; no intitle/KGR/SERP provided.
Target gate: Hook stop candidate lifecycle completion gate.
Command: hook.stop(payload, manifest)
Exit code: 0
Relevant stdout: 
Relevant stderr: 
Did prerequisite gates pass? YES
Was the intended target gate reached? YES
Evidence: Exit=0, Valid=True, Reason=. Candidate eliminated at exact stage terminated cleanly without KGR/SERP.
Verdict: PASS
```

---

### P1-P: Mixed BLOCKED + COMPLETE Candidate Batch Lifecycle
```text
Test: P1-P
Purpose: Verify that a batch containing an attested BLOCKED candidate and a valid COMPLETE candidate allows Stop and preserves distinct per-candidate statuses.
Preconditions: Candidate A attested BLOCKED, Candidate B valid COMPLETE.
Target gate: Hook stop multi-candidate lifecycle resolution gate.
Command: hook.stop(payload, manifest)
Exit code: 0
Relevant stdout: 
Relevant stderr: 
Did prerequisite gates pass? YES
Was the intended target gate reached? YES
Evidence: Exit=0, Valid=True. Mixed batch preserved cand_blocked=BLOCKED and cand_good=COMPLETE, allowed full run completion.
Verdict: PASS
```

---

### P1-Q: Run-Level Bare BLOCKED Bypass Rejection
```text
Test: P1-Q
Purpose: Verify that setting manifest.status = BLOCKED without an attested run blocker or valid stage blocker is denied at the Stop hook (verifying the newly fixed P1 vulnerability).
Preconditions: Bare status=BLOCKED with no stages or blocker details.
Target gate: Hook stop _verify_blocked_run gate.
Command: python3 runtime/codex_stage_hook.py stop
Exit code: 2
Relevant stdout: 
Relevant stderr: Active SEO production run attack-run-q cannot be BLOCKED: BLOCKED run requires blocked_stage
Did prerequisite gates pass? YES
Was the intended target gate reached? YES
Evidence: Exit=2, Stderr=Active SEO production run attack-run-q cannot be BLOCKED: BLOCKED run requires blocked_stage
Verdict: PASS
```

---

### P1-R: Fake Run Blocker Without External Attestation Rejection
```text
Test: P1-R
Purpose: Verify that declaring a run-level blocker (e.g. stage6_exact) without an external run_blocked attestation is denied.
Preconditions: status=BLOCKED with blocked_stage=stage6_exact but missing attestation.
Target gate: Hook stop run-blocker attestation verification gate.
Command: python3 runtime/codex_stage_hook.py stop
Exit code: 2
Relevant stdout: 
Relevant stderr: Active SEO production run attack-run-r cannot be BLOCKED: run blocked attestation missing
Did prerequisite gates pass? YES
Was the intended target gate reached? YES
Evidence: Exit=2, Stderr=Active SEO production run attack-run-r cannot be BLOCKED: run blocked attestation missing
Verdict: PASS
```

---

### P1-S: Attested Run Blocker Claim Binding Tamper Resistance
```text
Test: P1-S
Purpose: Verify that an attested run blocker strictly binds run_id, route, terminal_status, blocked_stage, and blocked_reason against tampering.
Preconditions: Valid attested claims bound to run_id, route, stage, reason; tested tamper on each attribute.
Target gate: verify_external_attestation exact claim matching gate.
Command: hook.stop(payload, tampered_manifests)
Exit code: 0
Relevant stdout: 
Relevant stderr: 
Did prerequisite gates pass? YES
Was the intended target gate reached? YES
Evidence: Valid ret=0, Tamper run_id ret=2, Tamper route ret=2, Tamper stage ret=2, Tamper reason ret=2
Verdict: PASS
```

---

### P1-T: Broker-Unavailable Bootstrap Exception and Boundary
```text
Test: P1-T
Purpose: Verify that when the broker is unavailable, ONLY the exact claim blocked_stage=trust_boundary and blocked_reason="trusted issuance broker unavailable" is allowed, while any other stage/reason is rejected, and if the broker exists the bootstrap claim is rejected.
Preconditions: Broker missing allows only exact trust_boundary claim; rejects generalized blockers or if broker exists.
Target gate: _verify_blocked_run bootstrap broker-check gate.
Command: hook.stop(payload, manifests)
Exit code: 0
Relevant stdout: 
Relevant stderr: 
Did prerequisite gates pass? YES
Was the intended target gate reached? YES
Evidence: Missing broker bootstrap: ret=0; Tampered stage: ret=2; Tampered reason: ret=2; Broker present bootstrap rejected: ret=2
Verdict: PASS
```

---

### P1-B: Direct Helper Minting Rejection
```text
Test: P1-B
Purpose: Verify that normal helper or test code invoking _mint_issuance_proof is denied.
Preconditions: _mint_issuance_proof called from test/helper code.
Target gate: _assert_issuance_mint_caller
Command: binding._mint_issuance_proof(...)
Exit code: 0
Did prerequisite gates pass? YES
Was the intended target gate reached? YES
Evidence: Direct helper minting denied: True
Verdict: PASS
```

---

### P1-C: Attacker-Controlled SEO_ISSUANCE_SECRET Env Variable Rejection
```text
Test: P1-C
Purpose: Verify that setting SEO_ISSUANCE_SECRET environment variable does not grant signing authority.
Preconditions: SEO_ISSUANCE_SECRET set in environment.
Target gate: Issuance trust boundary outside environment variables.
Command: binding._mint_issuance_proof(...)
Exit code: 0
Did prerequisite gates pass? YES
Was the intended target gate reached? YES
Evidence: Env secret denied signing authority: True
Verdict: PASS
```

---

### P1-D: Workspace-Readable .issuance_secret Rejection
```text
Test: P1-D
Purpose: Verify that creating .seo-run/.issuance_secret workspace file does not grant signing authority.
Preconditions: Workspace secret file present in .seo-run.
Target gate: Issuance trust boundary outside workspace files.
Command: binding._mint_issuance_proof(...)
Exit code: 0
Did prerequisite gates pass? YES
Was the intended target gate reached? YES
Evidence: Workspace secret denied signing authority: True
Verdict: PASS
```

---

### P1-E: Emerging Route Self-Declaration Without External Attestation Rejection
```text
Test: P1-E
Purpose: Verify that setting route=emerging in active.json without an emerging_route external attestation is rejected.
Preconditions: route=emerging without route_attestation_ref.
Target gate: _infer_canonical_required_stages / _verify_route_attestation.
Command: hook._infer_canonical_required_stages(...)
Exit code: 0
Did prerequisite gates pass? YES
Was the intended target gate reached? YES
Evidence: Route spoof rejected: True, reason=emerging route attestation missing
Verdict: PASS
```

---

### P1-I: Candidate Global Receipt Fallback Rejection
```text
Test: P1-I
Purpose: Verify that candidates without per-candidate stage6_exact cannot borrow global stage receipts.
Preconditions: Candidates lack individual stage6_exact; only global stage6_exact provided.
Target gate: _verify_candidate_completion exact stage receipt check.
Command: hook._verify_completion_requirements(manifest)
Exit code: 0
Did prerequisite gates pass? YES
Was the intended target gate reached? YES
Evidence: Global fallback denied: True, reason=candidate=cand_a stage6_exact is not verified: stage status is not PASS
Verdict: PASS
```

---

### P1-K: Marker Spoof Override Prevention
```text
Test: P1-K
Purpose: Verify that injecting SEO_STAGE_REQUIRE into protected collector commands cannot override the command-inferred protected stage.
Preconditions: SEO_STAGE_REQUIRE=fake_non_protected injected into protected collector command.
Target gate: _required_transition command-derived rule priority.
Command: hook._required_transition(payload)
Exit code: 0
Did prerequisite gates pass? YES
Was the intended target gate reached? YES
Evidence: Protected command rule took precedence: stage_inferred=stage6_exact
Verdict: PASS
```

---

### P1-M: Bare status=COMPLETE Without Stages Rejection
```text
Test: P1-M
Purpose: Verify that setting status=COMPLETE without passing required stages is denied at Stop.
Preconditions: status=COMPLETE with no validated stages.
Target gate: Hook stop _verify_completion_requirements gate.
Command: hook.stop(payload, manifest)
Exit code: 2
Did prerequisite gates pass? YES
Was the intended target gate reached? YES
Evidence: Bare COMPLETE denied with code 2
Verdict: PASS
```

