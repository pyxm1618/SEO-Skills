# 阶段二补充 · Claude Code 当前 Hook 路径复验

日期：2026-08-31
宿主：Claude Code
工作树：`/Users/milushangdi/Downloads/SEO-Skills-claude`
分支：`claude/claude-code-host`
运行时基线：`2fac394c3e832f43fbee16980da0ea6299ce6a54`
配置：`.claude/settings.json`
当前脚本：`runtime/stage_hook.py`

本文件补充验证 `runtime/codex_stage_hook.py` 更名后的**当前接线路径**。初始宿主验收的
完整命令、工作目录与事件归属保留在 `stage2-claude-host-gates.md`。本文件依据执行该次复验的
Claude Code 会话所提交的现场报告整理；当前文档同步会话没有重新触发 hook。报告明确声明没有
手工执行 `runtime/stage_hook.py`，四项拦截均由全新 Claude Code 会话自动触发。

## 证据组成与限制

当前路径结论采用组合证据，而不是只靠一行 stderr 反推事件：

1. 初始宿主验收已用完整命令/工作目录分别证明根目录与子目录 `PreToolUse`，并用子代理与主代理
   的结束时序分别证明 `SubagentStop` 与 `Stop`；历史原始输出保留旧脚本名，不改写。
2. 当前 `.claude/settings.json` 把三个事件都接到 `runtime/stage_hook.py`，
   `tests/test_claude_hooks_config.py` 校验 `PreToolUse`、`Stop`、`SubagentStop` 接线完整。
3. 本次 Claude 执行者的现场报告逐项标注 A=根目录、B=子目录、C=`SubagentStop`、D=`Stop`，
   并提供下列当前脚本输出和 C/D 的完成时序。

B 的 stderr 本身不编码调用方 cwd；C 与 D 的 hook command 本来就相同，因此单看 stderr 也不能
区分事件名。B/C 的事件归属依据执行者现场报告与既有完整验收，当前输出只证明更名后的脚本实际
被调用。用户已明确接受该现场报告，不要求再次扰动真实宿主状态；因此本次是**组合证据 PASS**，
不是把不充分的单行输出包装成独立证明。

## 结果

| 项目 | 结果 |
| --- | --- |
| A 根目录 `PreToolUse` | PASS |
| B 子目录 `PreToolUse` | PASS |
| C `SubagentStop` | PASS |
| D `Stop` | PASS |

## A · 根目录 PreToolUse

Claude Code 自动拒绝受保护命令：

```text
PreToolUse:Bash hook error: [cd "$(git rev-parse --show-toplevel)" && python3 runtime/stage_hook.py pre]: SEO stage gate denied stage6_exact; active run manifest is missing
```

结果：**PASS**。错误前缀来自宿主 hook 执行器，并明确指向当前
`runtime/stage_hook.py pre`。

## B · 子目录 PreToolUse

从 `skills/seo-keyword-selection` 子目录执行同类受保护命令，Claude Code 自动返回：

```text
PreToolUse:Bash hook error: [cd "$(git rev-parse --show-toplevel)" && python3 runtime/stage_hook.py pre]: SEO stage gate denied stage6_exact; active run manifest is missing
```

结果：**PASS（组合证据）**。子目录执行没有绕过门禁，且仍由仓库根目录下的当前脚本处理；
子目录归属来自执行者现场报告，stderr 负责证明当前脚本被调用。

## C · SubagentStop

专用 probe manifest 处于 `IN_PROGRESS` 时，子代理首次结束被自动拦截：

```text
[cd "$(git rev-parse --show-toplevel)" && python3 runtime/stage_hook.py stop]: Active SEO production run 448154806b0b4f30bc7d9f61b2e7565c is IN_PROGRESS; finish required stages or mark the run BLOCKED with the real blocker before stopping.
```

收到真实 hook feedback 后，probe 才按 canonical stage 和一致 blocker reason 收敛为合法
`BLOCKED`；子代理第二次结束放行并返回 `subagent-probe-complete-2`。

结果：**PASS（组合证据）**。执行者报告阻断发生在子代理结束边界，随后第二次结束才完成；
输出前缀明确指向当前 `runtime/stage_hook.py stop`。由于 `Stop` 与 `SubagentStop` 共用同一命令，
不把这行 stderr 单独描述成事件名证明。

## D · Stop

第二个专用 probe manifest 处于 `IN_PROGRESS` 时，主代理首次结束被自动拦截：

```text
Stop hook feedback:
[cd "$(git rev-parse --show-toplevel)" && python3 runtime/stage_hook.py stop]: Active SEO production run 38d1c5433c224b578fa056b480a1f96c is IN_PROGRESS; finish required stages or mark the run BLOCKED with the real blocker before stopping.
```

结果：**PASS**。主代理不能在活动 run 未收敛时结束，且宿主调用的是当前
`runtime/stage_hook.py stop`。

## 异常与证据边界

- C 的第一次子代理启动遇到 Claude API `429 rate_limit`，没有形成验收证据，也没有计为
  PASS；表中 PASS 来自重试后实际触发 `SubagentStop` 的运行。
- D 的首次 `Stop` 阻断已经针对 run `38d1c5433c224b578fa056b480a1f96c` 产生。之后同一
  worktree 的另一个并发 Claude 会话覆盖了 `.seo-run/active.json`，所以最终移入
  `/tmp/seo-host-stop-probe.json` 的内容不是该 run。该临时文件**不作为 D 的证据**；D 只依据
  上述宿主原始反馈判定。
- 这次覆盖实证了 `.seo-run/active.json` 是 worktree 级单例状态，不具备多会话并发隔离。
  同一 worktree 不得并发使用默认 manifest；操作约束见 `README.md` 和
  `runtime/TRUST_BOUNDARY.md`。
- 四项输出均未出现旧路径 `runtime/codex_stage_hook.py`。

## 清理与最终判定

最终 `.seo-run/active.json` 不存在，probe manifest 已移到 `/tmp`，工作区状态为：

```text
## claude/claude-code-host...origin/claude/claude-code-host
```

最终判定：**`CLAUDE_HOST_CURRENT_PATH=PASS`（组合证据）**。
