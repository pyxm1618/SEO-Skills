# Issuance Broker Live Acceptance Report (V4 Live Re-Audit)

## 1. Broker Host Presence & Filesystem Audit

### Checked Fixed Paths
1. `/usr/local/libexec/seo-issuance-broker`
2. `/opt/openai/libexec/seo-issuance-broker`

### Execution
```bash
$ ls -la /usr/local/libexec/seo-issuance-broker
ls: /usr/local/libexec/seo-issuance-broker: No such file or directory
$ ls -la /opt/openai/libexec/seo-issuance-broker
ls: /opt/openai/libexec/seo-issuance-broker: No such file or directory
$ ls -ld /usr/local/libexec /opt/openai/libexec
ls: /usr/local/libexec: No such file or directory
ls: /opt/openai/libexec: No such file or directory
```

### Audit Findings
- Binary exists: **NO**
- Root-owned regular file: **N/A**
- Mode non-writable by group/world: **N/A**
- Direct agent access to signing secret: **N/A** (No secret or key stored in repository, workspace, or agent env)

---

## 2. Security & Fail-Closed Properties Verification

When the trusted issuance broker is absent:
1. `runtime/evidence_binding.py:_trusted_broker_path()` strictly fails closed, raising:
   ```text
   EvidenceIntegrityError: trusted issuance broker unavailable; install a root-owned non-writable seo-issuance-broker at /usr/local/libexec or /opt/openai/libexec
   ```
2. Direct Agent Broker Sign Attack: **BLOCKED** (Host broker unavailable; cannot be invoked or probed as a live signing oracle).
3. Legitimate Collector Issuance: **BLOCKED** (Cannot obtain signed evidence receipt on host without broker).
4. Legitimate Validator Issuance: **BLOCKED** (Cannot issue validation receipt without broker).
5. Forged / Tampered Proof: **BLOCKED** (Fail-closed on verification).
6. P1-H Post-Validation Tampering: **BLOCKED** (Requires genuine broker-issued receipt before tampering).

---

## 3. Verdict

- **Broker Live**: `BLOCKED`
- **Direct Agent broker sign attack**: `BLOCKED`
- **Legitimate Collector issuance**: `BLOCKED`
- **Legitimate Validator issuance**: `BLOCKED`
- **Forged proof**: `BLOCKED`
- **Tampered proof**: `BLOCKED`
- **P1-H Post-validation tampering**: `BLOCKED`

*(Per acceptance discipline: When host broker is absent, live broker properties MUST be declared BLOCKED, not PASS or synthetic)*

