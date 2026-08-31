# 阶段三 Live 验收 6/7 · Traditional workflow

首次执行：2026-08-30
完成重试：2026-08-31
工作树：`/Users/milushangdi/Downloads/SEO-Skills-claude`
分支：`claude/claude-code-host`

结论：**PASS**。2026-08-30 首次执行时，continuing candidate 的 intitle 遇到 Google
`/sorry/`，当时如实记 FAIL；2026-08-31 在同一隔离 Google profile 重试后取得真实 intitle=113，
与已验证 Exact Volume=720 合并，production KGR receipt PASS，evaluator 计算 KGR=0.15694444。
SERP 保持 `absent` 且为可选，没有参与晋级。

## 显式候选台账

| candidate | Exact 门 | evaluator | 后续 |
| --- | --- | --- | --- |
| `wedding calculator` | PASS：Volume 320 / KD 22 / CPC 1.7 | `principle_eliminate_volume` | 按 Traditional 规则应在 Exact 后确定性早退 |
| `wedding cost calculator` | PASS：Volume 720 / KD 18 / CPC 1.65 | `do_candidate`（final stage） | intitle=113；KGR=0.15694444 PASS；SERP absent/可选 |

两个 candidate 的 identity 分别绑定到 production validator：

```text
cand_wedding_calculator_early -> stage6_exact PASS, candidate_keyword=wedding calculator
cand_wedding_cost_calculator_continue -> stage6_exact PASS, candidate_keyword=wedding cost calculator
```

全局真实证据：

- `discovery_autocomplete PASS`：10 条 Google 可见建议；
- `discovery_semrush_ideas PASS`：30 条当前 `sem.3ue.com` Ideas；
- 两条 `stage6_exact PASS`：当前 US Exact；
- continuing intitle 首次尝试：`BLOCKED: Page.wait_for_selector ... #result-stats`，exit 2，保留为历史失败；
- continuing intitle 完成重试：真实 Google collector 输出 113，production receipt PASS；
- continuing KGR：verified Exact + verified intitle，production receipt PASS；
- continuing SERP：未执行，evaluator 为 `serp_evidence_status=absent`；按修订契约属于可选项。

独立 KGR 与 Trends 验收使用 `wedding calculator` 的真实证据，属于第 5/7 与 3/7；本条
Traditional PASS 只使用 continuing candidate 自己绑定的 Exact、intitle 与 KGR receipt。

## 完成重试命令与原始输出

9333 当时仍监听但所有标签页已关闭，`/json/list` 为空，Playwright 尚未到 Google 页面就报
`Browser context management is not supported`。创建空白 target 后，同一专用 profile 的连接探针为：

```text
{'context_count': 1, 'cookie_count': 13, 'google_auth_cookie_count': 0, 'page_urls': ['about:blank']}
```

真实 intitle collector：

```bash
SEO_GOOGLE_CDP_URL=http://127.0.0.1:9333 \
SEO_CANDIDATE_ID=cand_wedding_cost_calculator_continue \
~/.venvs/seo-skills/bin/python runtime/collectors/google_live_collector.py intitle \
  --keyword 'wedding cost calculator' --market US \
  --evidence-dir .seo-run/stage3-live/google/evidence \
  --output .seo-run/stage3-live/traditional/google-intitle-wedding-cost-calculator.json
```

```json
{"keyword":"wedding cost calculator","intitle_results":113,"source":"Google","market":"US","observed_at":"2026-08-31T02:15:25.697171+00:00","evidence_ref":".seo-run/stage3-live/google/evidence/intitle-wedding-cost-calculator.png","observation_ref":".seo-run/stage3-live/google/evidence/intitle-wedding-cost-calculator.json","evidence_receipt_ref":".seo-run/stage3-live/traditional/google-intitle-wedding-cost-calculator.receipt.json"}
```

随后依次运行 production `intitle_observation` validator、`kgr_evidence_merge.py`、production
`kgr_intitle` validator 与 final evaluator；退出码全部为 0。final evaluator 的关键原始输出：

```json
{
  "count": 1,
  "status_counts": {"do_candidate": 1},
  "keyword": "wedding cost calculator",
  "volume": 720,
  "difficulty": 18,
  "intitle_results": 113,
  "kgr": 0.15694444,
  "kgr_signal": "pass_lt_0_25",
  "serp_evidence_status": "absent",
  "mechanical_status": "do_candidate",
  "provenance_status": "verified"
}
```

## 证据路径

| 证据 | 路径 | SHA256 / 状态 |
| --- | --- | --- |
| early evaluator | `.seo-run/stage3-live/traditional/evaluation-early.json` | `8ccb7b48138a8c8f0f724fed5742a14e285aea7507fac419a0c264b0653539dc` |
| continuing evaluator | `.seo-run/stage3-live/traditional/evaluation-continuing.json` | `f2ded151b7da0446f2ae0f4410ace04f88d9f582aefea440bfa8c77efc173e5b` |
| early Exact validation | `.seo-run/stage3-live/traditional/validation/early-exact.json` | PASS |
| continuing Exact validation | `.seo-run/stage3-live/traditional/validation/continuing-exact.json` | PASS |
| continuing intitle output | `.seo-run/stage3-live/traditional/google-intitle-wedding-cost-calculator.json` | `0b1ef4bdf59d453d97015dc7fb2dbd8325bae321dd2fe8660850f3e425b3f425` |
| continuing intitle screenshot | `.seo-run/stage3-live/google/evidence/intitle-wedding-cost-calculator.png` | `0cdd72fcb95891b258c2bfc99b06aaa6430a8f3782350d5e3657c16c1a332026` |
| continuing intitle validation | `.seo-run/stage3-live/traditional/validation/continuing-intitle.json` | PASS / `ffe85ed17a4840bc636c59ef4ac51392c4bcd7d7579a1294c615c651b0e24aee` |
| continuing KGR input | `.seo-run/stage3-live/traditional/kgr-input-wedding-cost-calculator.json` | `e5a8a35ae82e6a74c63952a7dae0cc14a6895b02c9cf0ff34934565f68b92703` |
| continuing KGR validation | `.seo-run/stage3-live/traditional/validation/continuing-kgr.json` | PASS / `3b32d287b2ae5eff95fdd26bf4b3465233a901eed900990eaa27e542a441e5e0` |
| Google blocker diagnostic | `.seo-run/stage3-live/google/serp-sorry-diagnostic.json` | `ab8866c561a3ff072900851991a8264d05b79bf99ab96be26b802255e2c94ab5` |
| first-page SERP screenshot | `.seo-run/stage3-live/google/evidence/serp-wedding-calculator.png` | `7cc6cb837c9d149641b47f97aa7b74ecac72b8ad0d9118a90ffbb1094c9ec398` |

没有 mock、合成数据、手写指标、官方 API 或 provider 降级；首次失败保留，完成重试使用新的真实证据。
