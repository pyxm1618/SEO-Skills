# 阶段二 · Claude Code Host 门禁生效证明

宿主：Claude Code
工作树：`/Users/milushangdi/Downloads/SEO-Skills-claude`
分支：`claude/claude-code-host`
配置来源：`.claude/settings.json`（`PreToolUse` / `Stop` / `SubagentStop`）
日期：2026-08-29

所有拦截均为**宿主自动触发**，不是手工执行 `runtime/codex_stage_hook.py`。判定依据是 Claude Code 返回的 `PreToolUse:Bash hook error:` 前缀——该前缀只可能由宿主的 hook 执行器产生。

使用的 run manifest（`.seo-run/active.json`）：

```json
{
  "run_id": "acceptance_stage2_dg",
  "route": "traditional",
  "status": "IN_PROGRESS",
  "stages": {
    "stage6_exact": {
      "status": "BLOCKED",
      "blocked_reason": "acceptance D-G probe: no real Semrush relay evidence"
    }
  }
}
```

---

## C — PreToolUse 拦截前置 stage 未满足的受保护命令

命令（由 Claude Code 在工作树根目录发起）：

```
python3 skills/seo-keyword-selection/scripts/evaluate_candidates.py --input /tmp/nonexistent_probe.json --stage exact
```

宿主返回：

```
PreToolUse:Bash hook error: [cd "$(git rev-parse --show-toplevel)" && python3 runtime/codex_stage_hook.py pre]: SEO stage gate denied stage6_exact; status=BLOCKED: live hook probe - not a real run
```

**结果：PASS。** 命令未执行；阻断理由回灌至模型，且携带该 stage 记录的真实 `blocked_reason`。

注：该次探针使用的 manifest `run_id` 为 `live_hook_probe`，`blocked_reason` 为 `live hook probe - not a real run`；其余条件与上表一致。

---

## D — 工作目录位于子目录时门禁不失效

这是 `fe3df63 fix: run Codex hooks from repository root` 所修复缺陷的回归验收点：hook 若以相对路径在非仓库根目录启动会静默失效。

命令：

```
cd skills && python3 seo-keyword-selection/scripts/evaluate_candidates.py --input /tmp/probe.json --stage exact
```

宿主返回：

```
PreToolUse:Bash hook error: [cd "$(git rev-parse --show-toplevel)" && python3 runtime/codex_stage_hook.py pre]: SEO stage gate denied stage6_exact; status=BLOCKED: acceptance D-G probe: no real Semrush relay evidence
```

**结果：PASS。** 子目录下仍然拦截。

补充证据——`git rev-parse --show-toplevel` 在 worktree 中正确解析到 worktree 根而非主仓：

```
$ git rev-parse --show-toplevel
/Users/milushangdi/Downloads/SEO-Skills-claude
```

---

## F — SubagentStop 拦截子代理，防止绕过完整性门禁

Claude Code 的 `Stop` 事件**不会**在子代理结束时触发。若只注册 `Stop`，把 SEO 流程放进子代理即可完整绕过完整性门禁——保护看似存在，实则未上电。本项验证 `.claude/settings.json` 中的 `SubagentStop` 封住了该缺口。

方法：在 manifest 处于 `IN_PROGRESS` 期间派出一个子代理，只让它执行一条只读命令 `git log --oneline -1`，并要求它如实回报结束时收到的任何阻断提示。

子代理逐字回报：

```
Stop hook feedback:
[cd "$(git rev-parse --show-toplevel)" && python3 runtime/codex_stage_hook.py stop]: Active SEO production run acceptance_stage2_dg is IN_PROGRESS; finish required stages or mark the run BLOCKED with the real blocker before stopping.
```

**结果：PASS。** 要点：

- 阻断在子代理**结束时**触发，而非工具调用阶段——与 `SubagentStop` 语义一致；
- `run_id` 为 `acceptance_stage2_dg`，与当前 manifest 一致，证明 hook 读取的是真实运行期状态而非硬编码文本；
- 子代理未被允许静默完成，被要求补齐 stage 或以真实 blocker 标记 BLOCKED；
- 子代理按指示未对该 run 采取任何行动，未修改任何文件。

---

## E — Stop 拦截未完成的 run（主代理）

方法：在 manifest 仍为 `IN_PROGRESS` 时，主代理正常结束回合。

宿主返回：

```
Stop hook feedback:
[cd "$(git rev-parse --show-toplevel)" && python3 runtime/codex_stage_hook.py stop]: Active SEO production run acceptance_stage2_dg is IN_PROGRESS; finish required stages or mark the run BLOCKED with the real blocker before stopping.
```

**结果：PASS。** 主代理无法在 run 未收敛时静默结束；`run_id` 与当前 manifest 一致。

`codex_stage_hook.py:467` 的 `stop_hook_active` 保护使该阻断为一次性，不会形成死循环。

---

## G — 清除 manifest 后的行为

### G-1 无关命令不受影响

```
$ python3 -m pytest tests/test_claude_hooks_config.py -q
....                                                                     [100%]
4 passed in 0.00s
```

**结果：PASS。** 门禁只作用于受保护命令，日常工作不受阻。

### G-2 受保护命令在无活动 run 时仍然拒绝（fail-closed）

```
$ python3 skills/seo-keyword-selection/scripts/evaluate_candidates.py --input /tmp/probe.json --stage exact
PreToolUse:Bash hook error: [...codex_stage_hook.py pre]: SEO stage gate denied stage6_exact; active run manifest is missing
```

**结果：PASS（符合设计）。** 这是 `codex_stage_hook.py:446` 的有意行为：受保护的生产命令不得脱离受追踪的 run 执行。删除 manifest 不是绕过门禁的手段。

验收执行时对本项的初始预期是"清空后放行"，实测更严格；经核对源码确认为设计意图，非缺陷。

### G-3 Stop 恢复放行

manifest 删除后，主代理正常结束回合，未再收到 Stop 阻断（`stop()` 在 manifest 缺失时返回 0）。

---

## 阶段二小结

| # | 项目 | 结果 |
| --- | --- | --- |
| A | `/hooks` 确认三事件已加载并信任 | 待人工确认（需宿主 UI） |
| B | 5 个 Skill 被自动发现 | PASS（会话内已列出，软链发现有效） |
| C | PreToolUse 拦截受保护命令 | PASS |
| D | 子目录下门禁不失效 | PASS |
| E | Stop 拦截未完成 run | PASS |
| F | SubagentStop 拦截子代理 | PASS |
| G | 清除 manifest 后行为正确 | PASS |

C–G 全部由 Claude Code 宿主自动触发，无一项以手工执行 `runtime/codex_stage_hook.py` 代替。


