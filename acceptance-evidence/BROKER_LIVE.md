# 第四层：宿主信任边界与 OS-Level Issuance Broker 审计报告 (BROKER_LIVE)

- **验收目标 SHA**：`d616f0202d1d781f15e10aa13e7ade73a58f8e34`
- **审计时间**：2026-08-28T10:03:42+08:00
- **判定结论**：**BROKER LIVE = BLOCKED** (宿主环境缺少信任组件，代码正确 Fail-Closed)

---

## 1. 宿主 Broker 路径探测记录

| 预期 Broker 路径 | 存在状态 | 权限与属主检查 | 结论 |
|---|---|---|---|
| `/usr/local/libexec/seo-issuance-broker` | **NOT FOUND** | N/A | 不存在 |
| `/opt/openai/libexec/seo-issuance-broker` | **NOT FOUND** | N/A | 不存在 |

### 执行命令与输出：
```bash
$ ls -la /usr/local/libexec/seo-issuance-broker /opt/openai/libexec/seo-issuance-broker 2>&1
ls: /opt/openai/libexec/seo-issuance-broker: No such file or directory
ls: /usr/local/libexec/seo-issuance-broker: No such file or directory
```

---

## 2. 信任边界与 Fail-Closed 审计

1. **密钥隔离性**：
   - 仓库内无任何 broker 私钥或 HMAC secret。
   - Agent 运行环境变量 (`SEO_ISSUANCE_SECRET`) 及本地 `.seo-run/.issuance_secret` 均无法获取签发权限。
2. **Fail-Closed 表现**：
   - 当 broker 不存在时，`runtime/evidence_binding.py` 的 `_trusted_broker_path()` 会立即抛出 `EvidenceIntegrityError("trusted issuance broker unavailable; install a root-owned non-writable seo-issuance-broker at /usr/local/libexec or /opt/openai/libexec")`。
   - 所有生产模式 (`--production`) 下的验证和收据签发均安全阻断，未发生权限泄露或降级通行。
3. **真实性原则**：
   - 根据验收禁止事项，验收工程师严禁自行安装不可信的 fake broker 冒充通过，因此准确判定为 **BLOCKED**。
