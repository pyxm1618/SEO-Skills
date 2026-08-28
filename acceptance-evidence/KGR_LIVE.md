# 第七层：KGR Live 证据合并审计报告 (KGR_LIVE)

- **验收目标 SHA**：`d616f0202d1d781f15e10aa13e7ade73a58f8e34`
- **执行时间**：2026-08-28T10:04:21+08:00
- **判定结论**：**KGR LIVE = BLOCKED** (因前序 Google intitle 与 Semrush Exact 宿主会话缺失而受阻，合并契约机制验证完全符合规范)

---

## 1. KGR 证据合并机制审计

| 审计项 | 约束要求 | 模块实现 | 判定 |
|---|---|---|---|
| 输入绑定 | 必须由真实 Exact Volume 与 Google intitle 双收据输入 | `merge_exact_and_intitle` 强制双输入 JSON 并校验底层收据 | **PASS** |
| 关键词一致性 | 严格校验关键词匹配 | `_norm_keyword(exact) == _norm_keyword(intitle)` | **PASS** |
| 市场与语言一致性 | 严格校验国家/地区市场匹配 | `_norm_market(exact) == _norm_market(intitle)` | **PASS** |
| 业务逻辑独立性 | 仅合成输入行，不得擅自修改业务判定 | 严格委托 `evaluate_candidates.py` 进行 `calc_kgr` 与阈值比对 | **PASS** |
| 阶段契约重验 | 合并后行必须符合 `kgr_intitle` 阶段契约 | `_fail_if_invalid("kgr_intitle", merged, contracts)` | **PASS** |

---

## 2. 结论

`runtime/kgr_evidence_merge.py` 正确执行了数据合并与双源一致性约束。因宿主上游 Live 数据受阻，如实判定为 **BLOCKED**。
