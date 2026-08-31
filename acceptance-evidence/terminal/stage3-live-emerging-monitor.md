# 阶段三 Live 验收 7/7 · Emerging Monitor

日期：2026-08-30
工作树：`/Users/milushangdi/Downloads/SEO-Skills-claude`
分支：`claude/claude-code-host`

结论：**PASS**。真实 temporal observations 已经过完整 Monitor 流水线；实际结果为 5 条
`watch -> new_root_watchlist`，没有制造 `emerging/breakout` 或 selection handoff。

## 最小探路与最终命令

用户给定的最小探路命令先成功抵达真实 Google Trends，但 `wedding` 的 Related/Rising 是合法空集：

```text
status=PASS, no_rising_queries, candidates=0, observations=0
```

该次只证明连接链路，不冒充“真实时序 Monitor PASS”。随后从用户给定 `wedding` anchor 的当前
`sem.3ue.com` Ideas UI 捕获取得真实 supplemental candidates，再执行：

```bash
SEO_GOOGLE_CDP_URL=http://127.0.0.1:9333 \
SEO_BROWSER_CDP_URL=http://127.0.0.1:9334 \
~/.venvs/seo-skills/bin/python skills/emerging-keyword-monitor/scripts/run_emerging_radar.py \
  --domain wedding --anchor wedding \
  --semrush-request .seo-run/stage3-live/semrush/ideas-wedding-request.json \
  --max-depth 1 --per-anchor-limit 5 --max-candidates 5 \
  --run-dir .seo-run/emerging-radar-live \
  --output .seo-run/emerging-radar-live/run-summary.json
```

```json
{"status":"PASS","candidate_counts":{"discovered":5,"supplemental":30,"unique_pool":5,"classified":5},"temporal_point_count":2045,"stage_validations":{"trends_related":1,"discovery_semrush_ideas":1,"trends_timeline":15}}
```

每条 candidate 都有三个独立窗口：`today 5-y` 262 点、`today 12-m` 54 点、`today 3-m`
93 点，共 `5 * (262 + 54 + 93) = 2045` 个真实点。15 个 `trends_timeline` production
validation 全部 PASS。

## 诚实分类与路由

| keyword | status | confidence | estimated birth window | route |
| --- | --- | --- | --- | --- |
| `how to choose a wedding venue` | watch | medium | 2025-11 ~ 2026-08 | new_root_watchlist |
| `how to choose a wedding dress` | watch | medium | 2025-11 ~ 2026-08 | new_root_watchlist |
| `taylor swift wedding photos` | watch | medium | 2026-06 ~ 2026-08 | new_root_watchlist |
| `colter wall secret wedding` | watch | medium | unknown | new_root_watchlist |
| `taylor swift wedding dress` | watch | medium | unknown | new_root_watchlist |

`unknown` 在本地 JSON 中仍为 `null`，在 Sheet mirror 中按导出合同显示为 `unknown`；没有转为 0
或空字符串。

## Sheet 实跑与读回

```bash
~/.venvs/seo-skills/bin/python skills/emerging-keyword-monitor/scripts/export_to_sheet.py \
  --database .seo-run/emerging-radar-live/emerging-keywords.json \
  --sheet-id 1EWw_Z2xBDrMfbpFLpB-0Phr8R8HOA7Ab5gQ-aqt63zM \
  --credentials ~/.config/seo-sheets/service-account.json
```

```text
{"status":"PASS","record_count":5,"updated_count":0,"appended_count":5,"header_written":true}
readback: expected=5, matched=5, missing=0, mismatched=0,
          unknown_cells=34, header_matches=true
```

## JSON、截图与哈希

| 证据 | 路径 | SHA256 |
| --- | --- | --- |
| run summary | `.seo-run/emerging-radar-live/run-summary.json` | `02c715b521d9a9f4afe0c296be3b9add136a96732c55a3f466001872b7958b71` |
| validation | `.seo-run/emerging-radar-live/run-summary.validation.json` | `f9cb6317cabc5b3de48527c2098d79d82f4641c3685122d715b6c9c1551f72cc` |
| database | `.seo-run/emerging-radar-live/emerging-keywords.json` | `19f760913d77b2c115fe4ba4a3ab3c474e53372902594841cba0e44a195d445a` |
| CSV | `.seo-run/emerging-radar-live/emerging-keywords.csv` | `6e460aba548d8903282904873ab415f068c3e98e87e3c4fcb8fa1d9f2ec7f313` |

代表性截图：

- `.seo-run/emerging-radar-live/evidence/trends-how-to-choose-a-wedding-venue-us-today-5-y-5ab7d469df3d.png`
- `.seo-run/emerging-radar-live/evidence/trends-how-to-choose-a-wedding-venue-us-today-12-m-ccd9a2ebab79.png`
- `.seo-run/emerging-radar-live/evidence/trends-how-to-choose-a-wedding-venue-us-today-3-m-2adc716eb5b3.png`

没有 API/fallback、mock、合成 observation 或人为强制 handoff。
