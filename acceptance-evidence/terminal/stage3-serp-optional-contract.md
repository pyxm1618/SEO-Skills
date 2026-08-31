# 阶段三契约修订 · SERP 改为可选

日期：2026-08-31
工作树：`/Users/milushangdi/Downloads/SEO-Skills-claude`
分支：`claude/claude-code-host`

结论：**PASS（契约与自动化行为）**。本次不改写任何 Live 原始事实：intitle 的真实 PASS 保留，
SERP `/sorry/` 仍是 unavailable 且不是 PASS/AEB，Traditional continuing intitle 仍是 FAIL。
变化只在于 SERP 不再是验收、Keyword Selection 或 Page Keyword Mapping 的硬门槛。

## 新契约

- Live 验收第 2 项只要求真实 Google intitle；SERP 不进入验收分母。
- Selection：Exact + intitle + KGR 是 continuing candidate 必需门；SERP 可省略或以带真实原因的
  非 terminal `serp_review.status=BLOCKED` 留档。它不能成为 candidate/run `blocked_stage`。
- KD 40–50 只有在 candidate-bound production receipt 通过、弱位 rank/URL 与真实 Top-10 匹配时
  才能晋级；缺失、BLOCKED、手填或不匹配均为 `observe_serp`。
- Mapping：`serp_fast_status=unknown` 不阻断 Primary 或 batch；observed `mismatch` 仍否决。
- 独立 URL 缺少 observed `serp_overlap` 时必须保持 `review`；validator 拒绝直接提交的无证据
  `independent_url_candidate`。拼错状态及非有限/超出 `[0,1]` 的 overlap 均无效。
- 如果声称 SERP PASS，原有真实 top-10、candidate-bound receipt、provenance 与 no-fallback 校验全部保留。

## TDD RED

Selection/Hook 修改前：

```bash
python3 -m pytest -q \
  skills/seo-keyword-selection/tests/test_selection.py::test_kd_40_50_without_optional_serp_stays_observe_not_pending \
  tests/test_hook_requirement_integrity.py::test_traditional_candidate_can_complete_without_optional_serp \
  tests/test_hook_requirement_integrity.py::test_traditional_candidate_can_record_optional_serp_unavailable \
  tests/test_hook_requirement_integrity.py::test_optional_serp_pass_is_verified_when_present \
  tests/test_final_release_repairs.py::test_multiline_protected_commands_have_same_stage_as_single_line
```

结果：`5 failed, 7 passed`。旧行为返回 `pending_serp`、强制 `serp_review PASS`，并让 Trends 依赖 SERP。

Mapping 修改前：三个可选 SERP 行为测试为 `3 failed`；随后独立 URL 校验回归为 `1 failed`，
证实旧 evaluator/validator 会阻塞 unknown SERP，且 standalone validator 会接受无 overlap 的独立 URL。

独立审查随后复现 4 个 fail-closed 缺口：SERP 可被滥用为 terminal blocker；手填两条弱位可在无
receipt 时晋级；拼错 `serp_fast_status` 可成为 Primary；负数/布尔/NaN overlap 可支持独立 URL。
每项均先加入失败回归再修复。

二次复审又定位 3 个边界：公开的 `verified_serp_results` 参数可绕过收据解析；`False/0` 状态会因
falsy 默认值变成 `unknown`；page-pair overlap 尚未复用严格 ratio 校验。对应 4 个定向测试先得到
`4 failed`，修复后得到 `4 passed`；验证结果现在只能由内部 candidate-bound receipt 解析产生。

## GREEN 与完整回归

```bash
python3 -m pytest -q skills/seo-keyword-selection/tests/test_selection.py \
  tests/test_hook_requirement_integrity.py tests/test_final_release_repairs.py \
  tests/test_observed_evidence_binding.py
# 98 passed

python3 -m pytest -q skills/seo-page-keyword-mapping/tests/test_mapping.py
# 17 passed

python3 -m pytest -q
# 379 passed in 6.85s
```

两次修改前/修改后 Skill 压力复测也得到一致结果：修改前会因 SERP unknown 阻塞；修改后会保留
`unknown`/`observe_serp` 并继续，同时拒绝 observed mismatch、无证据晋级和无 overlap 的独立 URL。

最终独立只读复审：Critical/Important/Minor 均无发现；复审方另跑定向回归 `25 passed`、完整套件
`379 passed in 6.81s`，并确认 Exact、intitle、KGR、relay-only 来源和 candidate-bound receipt 门禁未削弱。

## 阶段三台账重算

`PASS=6`，`ACCEPTED_ENVIRONMENT_BLOCKER=0`，`FAIL=1`，`UNREVIEWED=0`；
`7 = 6 + 0 + 1 + 0`。唯一 FAIL 是 Traditional continuing candidate 的必需 intitle/KGR 未完成，
因此当前 release decision 仍为 **DO NOT MERGE**，但依据已不再包含可选 SERP unavailable。
