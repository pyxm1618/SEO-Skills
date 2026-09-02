import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS_HOOKS = ROOT / ".agents" / "hooks.json"
AGENTS_SKILLS = ROOT / ".agents" / "skills"
STAGE_HOOK = ROOT / "runtime" / "stage_hook.py"

REQUIRED_SKILLS = (
    "keyword-root-library",
    "seo-keyword-discovery",
    "emerging-keyword-monitor",
    "seo-keyword-selection",
    "seo-page-keyword-mapping",
)


def _load_agents_hooks():
    assert AGENTS_HOOKS.exists(), ".agents/hooks.json must exist"
    return json.loads(AGENTS_HOOKS.read_text(encoding="utf-8"))


def test_agents_hooks_json_structure_and_events():
    config = _load_agents_hooks()
    assert "seo-stage-gate" in config, "top-level key must be a named hook"
    hook_def = config["seo-stage-gate"]

    assert "PreToolUse" in hook_def, "PreToolUse event must be configured"
    pre_groups = hook_def["PreToolUse"]
    assert isinstance(pre_groups, list) and len(pre_groups) >= 1
    assert pre_groups[0].get("matcher") == "run_command", "Antigravity matcher for shell commands must be run_command"
    assert "hooks" in pre_groups[0]
    pre_cmd = pre_groups[0]["hooks"][0]["command"]
    assert "runtime/stage_hook.py pre" in pre_cmd

    assert "Stop" in hook_def, "Stop event must be configured"
    stop_handlers = hook_def["Stop"]
    assert isinstance(stop_handlers, list) and len(stop_handlers) >= 1
    # Antigravity Stop is flat (no matcher, handler directly in list)
    stop_cmd = stop_handlers[0]["command"]
    assert "runtime/stage_hook.py stop" in stop_cmd


def test_agents_skills_directories_and_frontmatter():
    assert AGENTS_SKILLS.exists(), ".agents/skills must exist"
    for name in REQUIRED_SKILLS:
        skill_dir = AGENTS_SKILLS / name
        assert skill_dir.is_dir(), f".agents/skills/{name} must be a directory"
        skill_file = skill_dir / "SKILL.md"
        assert skill_file.is_file(), f".agents/skills/{name}/SKILL.md must exist"

        content = skill_file.read_text(encoding="utf-8")
        assert content.startswith("---"), f"{name}/SKILL.md must start with YAML frontmatter"
        parts = content.split("---", 2)
        assert len(parts) >= 3, f"{name}/SKILL.md must have closed frontmatter"
        frontmatter = parts[1]
        assert f"name: {name}" in frontmatter, f"{name}/SKILL.md frontmatter must contain 'name: {name}'"
        assert "description:" in frontmatter, f"{name}/SKILL.md frontmatter must contain 'description:'"


def test_antigravity_pre_tool_use_denies_with_json(tmp_path):
    manifest = {
        "run_id": "r1",
        "route": "traditional",
        "status": "IN_PROGRESS",
        "stages": {"stage6_exact": {"status": "BLOCKED", "blocked_reason": "missing CPC"}},
    }
    manifest_path = tmp_path / "active.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    # Antigravity format payload
    payload = {
        "conversationId": "test-conv-123",
        "stepIdx": 10,
        "toolCall": {
            "name": "run_command",
            "args": {
                "CommandLine": "SEO_STAGE_REQUIRE=stage6_exact python3 downstream.py"
            }
        }
    }

    env = dict(sys.modules["os"].environ, SEO_RUN_MANIFEST=str(manifest_path))
    proc = subprocess.run(
        [sys.executable, str(STAGE_HOOK), "pre"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
    )

    assert proc.returncode == 0, "Antigravity hook must exit 0 and return decision in stdout"
    output = json.loads(proc.stdout)
    assert output.get("decision") == "deny"
    assert "stage6_exact" in output.get("reason", "")
    assert "missing CPC" in output.get("reason", "")


def test_antigravity_stop_blocks_inprogress_run_with_json(tmp_path):
    manifest = {
        "run_id": "r1",
        "route": "traditional",
        "status": "IN_PROGRESS",
    }
    manifest_path = tmp_path / "active.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    payload = {
        "conversationId": "test-conv-123",
        "executionNum": 1,
        "terminationReason": "model_stop",
        "fullyIdle": True,
    }

    env = dict(sys.modules["os"].environ, SEO_RUN_MANIFEST=str(manifest_path))
    proc = subprocess.run(
        [sys.executable, str(STAGE_HOOK), "stop"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
    )

    assert proc.returncode == 0, "Antigravity hook must exit 0 and return decision in stdout"
    output = json.loads(proc.stdout)
    assert output.get("decision") == "continue"
    assert "Active SEO production run r1 is IN_PROGRESS" in output.get("reason", "")


def test_antigravity_stop_allows_when_no_manifest():
    payload = {
        "conversationId": "test-conv-123",
        "executionNum": 1,
        "terminationReason": "model_stop",
    }
    env = dict(sys.modules["os"].environ, SEO_RUN_MANIFEST="/nonexistent/active.json")
    proc = subprocess.run(
        [sys.executable, str(STAGE_HOOK), "stop"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
    )
    assert proc.returncode == 0
    output = json.loads(proc.stdout) if proc.stdout.strip() else {}
    assert output == {} or output.get("decision") != "continue"
