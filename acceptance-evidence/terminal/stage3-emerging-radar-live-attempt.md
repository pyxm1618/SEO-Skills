# 阶段三 · Emerging Radar 真实 Live 采集尝试

宿主：Claude Code
工作树：`/Users/milushangdi/Downloads/SEO-Skills-claude`
分支：`claude/claude-code-host`
提交：`902e8ae`（记录时）
日期：2026-08-30

结论：**`ACCEPTED_ENVIRONMENT_BLOCKER`，不是 `PASS`。**
真实关键词数据**未取得**。本次证明的是「外部依赖不可用时软件行为正确」，不构成对采集结果的验收。

---

## 环境准备

Playwright 与 gspread 装在专用虚拟环境 `~/.venvs/seo-skills`，未修改 Homebrew 系统 Python
（Homebrew Python 3.14 为 PEP 668 externally-managed，直接安装会被拒且有破坏风险）。

Google 浏览器隔离：全新 profile，独立调试端口，与用户日常浏览器完全分离。

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9333 \
  --user-data-dir=/tmp/seo-google-clean-profile \
  --no-first-run --no-default-browser-check --disable-sync
```

`SEO_GOOGLE_CDP_URL=http://127.0.0.1:9333`

### 登出隔离验证

设计要求 Google 采集上下文不得含任何 Google 认证 cookie，否则 `connect()` 必须失败。
实测通过 `google_live_collector.connect()`：

```
connect() succeeded -> isolation check passed
total cookies in context : 0
google.* cookies         : 0
google AUTH cookies      : 0 (must be 0)
browser contexts         : 1
```

---

## 执行命令

```bash
SEO_GOOGLE_CDP_URL=http://127.0.0.1:9333 \
~/.venvs/seo-skills/bin/python skills/emerging-keyword-monitor/scripts/run_emerging_radar.py \
  --domain wedding --anchor wedding \
  --max-depth 1 --per-anchor-limit 5 --max-candidates 5 \
  --run-dir .seo-run/emerging-radar-live \
  --output .seo-run/emerging-radar-live/run-summary.json
```

规模为刻意选择的最小值，用于先验证链路而非追求候选数量。

## 结果

```json
{"status": "BLOCKED", "candidate_counts": {"discovered": 0, "supplemental": 0, "unique_pool": 0, "classified": 0}}
```

阶段记录：

```json
"emerging_radar_run": {
  "status": "BLOCKED",
  "blocked_reason": "BLOCKED: Google Trends related result could not be confirmed; blocker_evidence_ref=...; blocker_screenshot_ref=..."
}
```

`recursive_edge_policy = google_trends_rising_only`，`supplemental_recursive = false`，anchor pool 记录完整。

### 外部阻塞的直接证据

采集器抵达的真实页面：`https://trends.google.com/trends/explore?geo=US&date=today+12-m&q=wedding`

页面正文（截图与 JSON 一致）：

```
429. that's an error.
we're sorry, but you have sent too many requests to us recently.
please try again later. that's all we know.
```

证据文件（`.seo-run/` 被 `.gitignore` 排除，此处留存哈希以便追溯）：

| 文件 | SHA256 |
| --- | --- |
| `evidence/trends-related-wedding-us-today-12-m-60211c496098-blocked.json` | `05703ed9def2008c93caf1ff11d2fdc08d49ec551230c19b5c58c5aef37553d8` |
| `evidence/trends-related-wedding-us-today-12-m-60211c496098-blocked.png` | `b6e1d80286065fcc2b3a14c63db8321a527836096bf3b87b383609c24e6c8213` |
| `run-summary.json` | `ad5b035232f0bed13431f2bebd04d83b7d128f8b25c5f253f5e0ffd80643f036` |

---

## `ACCEPTED_ENVIRONMENT_BLOCKER` 六项条件逐条核对

依据 `runtime/TRUST_BOUNDARY.md`。

| 条件 | 结果 | 依据 |
| --- | --- | --- |
| 真实采集器抵达目标外部源并捕获阻塞证据 | 满足 | 页面 URL 为 trends.google.com/trends/explore；JSON + 截图均已落盘 |
| 阻塞可证为外部原因而非解析/契约缺陷 | 满足 | Google 返回 429 限流页；页面无 Trends 结果结构可供解析 |
| 未使用 mock、合成数据、官方 Semrush API、替代 provider 或任何 fallback | 满足 | 候选数为 0；无任何替代来源被调用 |
| 采集器与下游工作流 fail closed，未伪造亦未带不完整证据前进 | 满足 | run `BLOCKED`；stage `BLOCKED` 并保留结构化 blocker |
| 有针对性回归测试覆盖相关 parser/extractor 行为 | 满足（**本次新增**） | 见下 |
| 无开放 P0/P1 表明有效源数据会被错误接受或门禁可被绕过 | 满足 | 363 passed；PR #24 四项 P1 已逐条复核并实测 |

### 第 5 项原本不满足，为此新增回归测试

记录本次尝试前，`tests/test_emerging_radar_google_safety.py` 覆盖了上下文隔离、cookie 拒绝、
延迟 payload 等待与解析器行为，但**没有任何测试覆盖「Google 返回错误页时必须 fail-closed 并留证」**
——即本次真实发生的场景。因此新增：

`test_related_fails_closed_with_evidence_when_google_returns_an_error_page`

断言：抛出 `RuntimeError` 且错误消息含 `blocker_evidence_ref=` 与 `blocker_screenshot_ref=`；
blocker JSON 落盘且 `observed_related_payload_count == 0`、`blocker == related_result_not_confirmed`、
`body_excerpt` 含 `429`；且 payload 中**不含** `related_queries` 字段
（即不得留下任何可能被误认为已观测需求的内容）。

在补上该测试之前，本条件不成立，故不得记录为 `ACCEPTED_ENVIRONMENT_BLOCKER`。

---

## 仍未完成

- **真实关键词数据未取得。** 限流按 IP 计，需更换网络出口或等待其自然解除后重跑。
- 未取得 Trends timeline 真实序列，故 `estimated_birth_window` 的真实数据表现尚未验证
  （仅有构造数据与单元测试覆盖）。
- Google Sheet 导出已在真实表格上验证（见提交 `902e8ae`），但导入的是构造样例数据，
  尚未导入真实雷达输出。
