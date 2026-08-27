import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "runtime" / "codex_stage_hook.py"
FIXTURE_FACTORY = ROOT / "tests" / "evidence_fixture_factory.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bound_stage_row(tmp_path, stage, label):
    if stage != "stage6_exact":
        return {"test": True}
    fixtures = load_module(f"codex_hook_fixture_{label}", FIXTURE_FACTORY)
    _output, bound, _raw, _capture = fixtures.make_semrush_exact(tmp_path, f"{label}-{stage}", {
        "keyword": "wedding calculator",
        "volume": 1000,
        "kd": 20,
        "cpc": 0.2,
        "intent": ["commercial"],
        "competition_level": "low",
        "trend": [50] * 12,
    })
    return bound


def _bind_pass_records(tmp_path, manifest):
    def bind(record, stage, candidate_id, label):
        if not isinstance(record, dict) or record.get("status") != "PASS" or record.get("validation_receipt_ref"):
            return
        report_path = tmp_path / f"{label}-{stage}.report.json"
        receipt_path = report_path.with_suffix(".receipt.json")
        report = {
            "stage": stage,
            "status": "PASS",
            "production": True,
            "candidate_id": candidate_id,
            "complete_count": 1,
            "blocked_count": 0,
            "complete": [_bound_stage_row(tmp_path, stage, label)],
            "blocked": [],
            "validation_receipt_ref": str(receipt_path),
        }
        report_path.write_text(json.dumps(report), encoding="utf-8")
        receipt = {
            "schema": "seo-stage-validation/v1",
            "stage": stage,
            "status": "PASS",
            "candidate_id": candidate_id,
            "report_ref": str(report_path),
            "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        }
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        record["validation_receipt_ref"] = str(receipt_path)

    for stage, record in manifest.get("stages", {}).items():
        bind(record, stage, None, "global")
    for candidate_id, stages in manifest.get("candidates", {}).items():
        for stage, record in stages.items():
            bind(record, stage, candidate_id, candidate_id)


def run_hook(tmp_path, mode, payload, manifest):
    _bind_pass_records(tmp_path, manifest)
    manifest_path = tmp_path / "active.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    env = dict(os.environ, SEO_RUN_MANIFEST=str(manifest_path))
    return subprocess.run(
        [sys.executable, str(HOOK), mode],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
    )


def test_pretooluse_denies_invalid_preceding_stage(tmp_path):
    manifest = {
        "run_id": "r1",
        "route": "traditional",
        "status": "IN_PROGRESS",
        "stages": {"stage6_exact": {"status": "BLOCKED", "blocked_reason": "missing CPC"}},
    }
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "SEO_STAGE_REQUIRE=stage6_exact python3 downstream.py"},
    }
    result = run_hook(tmp_path, "pre", payload, manifest)
    assert result.returncode == 2
    assert "stage6_exact" in result.stderr
    assert "missing CPC" in result.stderr


def test_pretooluse_allows_valid_contract(tmp_path):
    manifest = {
        "run_id": "r1",
        "route": "traditional",
        "status": "IN_PROGRESS",
        "stages": {"stage6_exact": {"status": "PASS", "blocked_reason": ""}},
    }
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "SEO_STAGE_REQUIRE=stage6_exact python3 downstream.py"},
    }
    result = run_hook(tmp_path, "pre", payload, manifest)
    assert result.returncode == 0


def test_pretooluse_can_gate_one_candidate_without_blocking_others(tmp_path):
    manifest = {
        "run_id": "r1",
        "route": "traditional",
        "status": "IN_PROGRESS",
        "stages": {},
        "candidates": {
            "good": {"stage6_exact": {"status": "PASS", "blocked_reason": ""}},
            "bad": {"stage6_exact": {"status": "BLOCKED", "blocked_reason": "relay failed"}},
        },
    }
    base = {"hook_event_name": "PreToolUse", "tool_name": "Bash"}
    good = dict(base, tool_input={"command": "SEO_STAGE_REQUIRE=stage6_exact SEO_CANDIDATE_ID=good python3 downstream.py"})
    bad = dict(base, tool_input={"command": "SEO_STAGE_REQUIRE=stage6_exact SEO_CANDIDATE_ID=bad python3 downstream.py"})
    assert run_hook(tmp_path, "pre", good, manifest).returncode == 0
    assert run_hook(tmp_path, "pre", bad, manifest).returncode == 2


def test_stop_blocks_incomplete_active_run(tmp_path):
    manifest = {"run_id": "r1", "route": "traditional", "status": "IN_PROGRESS", "stages": {}}
    payload = {"hook_event_name": "Stop", "stop_hook_active": False, "last_assistant_message": "done"}
    result = run_hook(tmp_path, "stop", payload, manifest)
    assert result.returncode == 2
    assert "IN_PROGRESS" in result.stderr


def test_stop_allows_blocked_run_to_end(tmp_path):
    manifest = {"run_id": "r1", "route": "traditional", "status": "BLOCKED", "stages": {}}
    payload = {"hook_event_name": "Stop", "stop_hook_active": False, "last_assistant_message": "blocked"}
    assert run_hook(tmp_path, "stop", payload, manifest).returncode == 0


def test_stop_hook_active_prevents_recursive_block(tmp_path):
    manifest = {"run_id": "r1", "route": "traditional", "status": "IN_PROGRESS", "stages": {}}
    payload = {"hook_event_name": "Stop", "stop_hook_active": True, "last_assistant_message": "continuing"}
    assert run_hook(tmp_path, "stop", payload, manifest).returncode == 0
