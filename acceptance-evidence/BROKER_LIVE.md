# Issuance Broker Live Acceptance Report (V4)

## 1. Broker Host Presence & Ownership Audit

### Checked Paths
1. `/usr/local/libexec/seo-issuance-broker`
2. `/opt/openai/libexec/seo-issuance-broker`

### Execution
```bash
$ ls -la /usr/local/libexec/seo-issuance-broker
ls: /usr/local/libexec/seo-issuance-broker: No such file or directory
$ ls -la /opt/openai/libexec/seo-issuance-broker
ls: /opt/openai/libexec/seo-issuance-broker: No such file or directory
```

### Audit Findings
- Binary exists: **NO**
- Root-owned regular file: **N/A**
- Mode non-writable by group/world: **N/A**
- Direct agent access to signing secret: **N/A**

---

## 2. Fail-Closed Verification

When the trusted issuance broker is absent, `runtime/evidence_binding.py:_trusted_broker_path()` raises:
```text
EvidenceIntegrityError: trusted issuance broker unavailable; install a root-owned non-writable seo-issuance-broker at /usr/local/libexec or /opt/openai/libexec
```

As a result:
- Direct agent `sign` request: **BLOCKED** (cannot be tested against live host oracle)
- Signing secret unreadability: **BLOCKED**
- Real proof / tamper / replay tests: **BLOCKED**
- Live production collector minting: **BLOCKED**

---

## 3. Verdict

- **Broker Live**: `BLOCKED`
- (Per Acceptance Discipline: Broker absence MUST be recorded as `BLOCKED`, never as `PASS` or synthetic substitute).

