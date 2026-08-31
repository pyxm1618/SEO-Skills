# 阶段三 Live 验收 5/7 · KGR

日期：2026-08-30
工作树：`/Users/milushangdi/Downloads/SEO-Skills-claude`
分支：`claude/claude-code-host`

结论：**PASS**。

KGR 只由本次已验证的 Semrush Exact 与 Google intitle 合并；没有手填 Volume、intitle 或 KGR。

## 命令与原始输出

```bash
~/.venvs/seo-skills/bin/python runtime/kgr_evidence_merge.py \
  --exact .seo-run/stage3-live/traditional/semrush-exact-wedding-calculator.json \
  --intitle .seo-run/stage3-live/traditional/google-intitle-wedding-calculator.json \
  --output .seo-run/stage3-live/traditional/kgr-input-wedding-calculator.json
```

Merger 验证了两个 collector receipt、keyword identity 与 US market/database，输出：

```json
{"keyword":"wedding calculator","volume":320,"intitle_results":493,"metric_source":"Semrush","metric_database":"us","intitle_source":"Google"}
```

随后调用仓库现有 `evaluate_candidates.normalize(..., "final")`，而非另写公式：

```text
kgr=1.540625
kgr_signal=not_blue_ocean
mechanical_status=principle_eliminate_volume
provenance_status=verified
```

KGR 数值是 evaluator 的确定性结果；本项 PASS 不把它伪装成“好词”或 selection handoff。

Production validator：`kgr_intitle PASS`，`complete_count=1`，`blocked_count=0`。

## JSON、来源截图与哈希

| 证据 | 路径 | SHA256 |
| --- | --- | --- |
| merged verified input | `.seo-run/stage3-live/traditional/kgr-input-wedding-calculator.json` | `0fceccbeffead58c19961e62f0de8e56ffd533d27b86e5adbbf3657734417cb1` |
| evaluator output | `.seo-run/stage3-live/traditional/evaluation-early.json` | `8ccb7b48138a8c8f0f724fed5742a14e285aea7507fac419a0c264b0653539dc` |
| Exact raw/receipt | `.seo-run/stage3-live/traditional/semrush-exact-wedding-calculator.raw.json` + `.receipt.json` | 由 normalized receipt 绑定 |
| intitle screenshot | `.seo-run/stage3-live/google/evidence/intitle-wedding-calculator.png` | 由 Google receipt 绑定 |
| KGR validation | `.seo-run/stage3-live/traditional/validation/early-kgr.json` | `kgr_intitle PASS` |
