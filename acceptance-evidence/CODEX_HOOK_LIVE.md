# 第八层：Codex Hook 宿主集成审计报告 (CODEX_HOOK_LIVE)

- **验收目标 SHA**：`d616f0202d1d781f15e10aa13e7ade73a58f8e34`
- **执行时间**：2026-08-28T10:04:29+08:00
- **Hook 脚本**：`runtime/codex_stage_hook.py`
- **配置文件**：`.codex/hooks.json`
- **判定结论**：**CODEX HOOK INTEGRATION = PASS** (真实子进程执行全部符合生命周期控制契约)

---

## 1. 宿主 Hook 拦截与放行测试矩阵

| 事件类型 | 测试场景 | 输入 Payload 与 Manifest | 预期行为 | 实际执行结果 | 判定 |
|---|---|---|---|---|---|
| **PreToolUse** | 缺失前置 Stage | 执行受保护 intitle 命令，前置 Exact 为 NOT_RUN | 阻断执行 (Exit 2) | Exit 2 (`SEO stage gate denied stage6_exact; status=NOT_RUN`) | **PASS** |
| **PreToolUse** | 无关普通命令 | 执行 `ls -la` 等普通工具调用 | 直接放行 (Exit 0) | Exit 0 | **PASS** |
| **PreToolUse** | 伪造 Stage Marker | 命令附带 `SEO_STAGE_REQUIRE=fake_stage` | 依据真实命令推导并阻断 | Exit 2 (拦截假 marker) | **PASS** |
| **PreToolUse** | Candidate Mismatch | 候选词收据不匹配目标候选词 | 阻断执行 (Exit 2) | Exit 2 (`validation receipt candidate mismatch`) | **PASS** |
| **PreToolUse** | 证据篡改 | 验证收据生成后修改底层数据文件 | 重放计算哈希不符，阻断 | Exit 2 (`PASS validation receipt invalid`) | **PASS** |
| **Stop** | 运行仍在进行中 | `status=IN_PROGRESS` | 阻止会话停止 (Exit 2) | Exit 2 (`is IN_PROGRESS; finish required stages...`) | **PASS** |
| **Stop** | 虚假 COMPLETE | 声明 `COMPLETE` 但无合法完整 stages | 阻止会话停止 (Exit 2) | Exit 2 (`cannot be COMPLETE...`) | **PASS** |
| **Stop** | 合法 BLOCKED 退出 | 声明 `status=BLOCKED` 且提供 reason | 允许正常停止 (Exit 0) | Exit 0 | **PASS** |
| **Stop** | Hook 循环防护 | `stop_hook_active=True` | 允许正常退出防止死循环 | Exit 0 | **PASS** |

---

## 2. 结论

`runtime/codex_stage_hook.py` 宿主集成表现健壮，严格根据真实命令和完整生命周期推导准入准出，**CODEX HOOK INTEGRATION = PASS**。
