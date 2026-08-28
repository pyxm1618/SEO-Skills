# 第六层：Semrush Relay Live 真实采集审计报告 (SEMRUSH_LIVE)

- **验收目标 SHA**：`d616f0202d1d781f15e10aa13e7ade73a58f8e34`
- **执行时间**：2026-08-28T10:04:10+08:00
- **判定结论**：**SEMRUSH RELAY LIVE = BLOCKED** (宿主未提供活跃的 `sem.3ue.com` 认证会话与网络抓取包，代码严格限制并 Fail-Closed)

---

## 1. 采集策略与数据源审计

| 策略项 | 要求 | 实现审计 | 判定 |
|---|---|---|---|
| 域名限制 | 仅允许同源 Relay `sem.3ue.com` | `ALLOWED_HOST = "sem.3ue.com"` 硬编码校验 | **PASS** |
| 官方 API 禁止 | 严禁使用官方 Semrush API / API Key | 源码中无任何官方 endpoint 或 key 注入接口 | **PASS** |
| Provider Fallback 禁止 | 严禁降级至 Ahrefs / DataForSEO 等 | 源码无任何 fallback 机制，缺失时直接抛异常 | **PASS** |
| 时效性校验 | 请求描述符捕获时间限制 900 秒以内 | `DEFAULT_CAPTURE_MAX_AGE_SECONDS = 900` 动态比对 | **PASS** |
| 确定性重放 | 仅依据 observed schema 重放为规范行 | `_normalize_ideas_item` / `_normalize_exact_item` 确定性处理 | **PASS** |

---

## 2. 真实 Live 执行记录

- **执行命令**：
```bash
python3 runtime/collectors/semrush_relay_collector.py --request <capture.json> --output <out.json>
```
- **实际状态**：当前测试机未连接 `sem.3ue.com` 已认证会话，无活跃实时网络抓包。
- **Fail-Closed 表现**：Collector 正确拒绝并返回 Exit Code 2，未发生假冒数据或降级 API 访问。
