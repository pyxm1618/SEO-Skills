import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "runtime" / "codex_stage_hook.py"
VALIDATOR = ROOT / "runtime" / "stage_validator.py"
CONTRACTS = ROOT / "runtime" / "stage_contracts.json"
SEMRUSH = ROOT / "runtime" / "collectors" / "semrush_relay_collector.py"
GOOGLE = ROOT / "runtime" / "collectors" / "google_live_collector.py"
MERGER = ROOT / "runtime" / "kgr_evidence_merge.py"
EVALUATOR = ROOT / "skills" / "seo-keyword-selection" / "scripts" / "evaluate_candidates.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def exact_row(**overrides):
    row = {
        "keyword": "wedding calculator",
        "volume": 1000,
        "kd": 20,
        "cpc": 0.20,
        "intent": "informational",
        "competition_level": "low",
        "trend": list(range(1, 13)),
        "metric_source": "Semrush",
        "metric_database": "us",
        "metric_stage": "exact",
        "observed_at": "2026-08-27T00:00:00Z",
        "relay_origin": "https://sem.3ue.com/",
        "provenance_ref": "evidence/semrush-exact.json",
    }
    row.update(overrides)
    return row


def run_hook(tmp_path, payload, manifest):
    manifest_path = tmp_path / "active.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    env = dict(os.environ, SEO_RUN_MANIFEST=str(manifest_path))
    return subprocess.run(
        [sys.executable, str(HOOK), "pre"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
    )


def test_protected_exact_evaluation_without_marker_is_denied_when_stage6_blocked(tmp_path):
    manifest = {
        "run_id": "r1",
        "route": "traditional",
        "status": "IN_PROGRESS",
        "stages": {"stage6_exact": {"status": "BLOCKED", "blocked_reason": "missing CPC"}},
    }
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {
            "command": "python3 skills/seo-keyword-selection/scripts/evaluate_candidates.py --input rows.json --stage exact"
        },
    }
    result = run_hook(tmp_path, payload, manifest)
    assert result.returncode == 2
    assert "stage6_exact" in result.stderr


def test_protected_exact_evaluation_without_marker_is_allowed_when_stage6_passes(tmp_path):
    manifest = {
        "run_id": "r1",
        "route": "traditional",
        "status": "IN_PROGRESS",
        "stages": {"stage6_exact": {"status": "PASS"}},
    }
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {
            "command": "python3 skills/seo-keyword-selection/scripts/evaluate_candidates.py --input rows.json --stage exact"
        },
    }
    assert run_hook(tmp_path, payload, manifest).returncode == 0


def test_unrelated_bash_without_marker_is_not_gated(tmp_path):
    manifest = {
        "run_id": "r1",
        "route": "traditional",
        "status": "IN_PROGRESS",
        "stages": {"stage6_exact": {"status": "BLOCKED"}},
    }
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "python3 -m pytest -q"},
    }
    assert run_hook(tmp_path, payload, manifest).returncode == 0


class FakePage:
    def __init__(self, response):
        self.response = response

    def evaluate(self, _script, _args):
        return {"ok": True, "status": 200, "data": self.response}


def relay_descriptor(mode, **extra):
    data = {
        "path": "/captured/current-path",
        "method": "POST",
        "body": {},
        "capture_observed_at": "2026-08-27T00:00:00Z",
        "capture_evidence_ref": "evidence/current-network-capture.json",
        "mode": mode,
        "metric_database": "us",
    }
    data.update(extra)
    return data


def test_semrush_exact_collect_deterministically_normalizes_current_response_shape():
    semrush = load_module("semrush_relay_collector", SEMRUSH)
    raw = {
        "data": {
            "rows": [
                {
                    "keyword": "wedding calculator",
                    "volume": 1000,
                    "kd": 20,
                    "cpc": 0.2,
                    "intent": "informational",
                    "competition_level": "low",
                    "trend": list(range(1, 13)),
                }
            ]
        }
    }
    result = semrush.collect(
        FakePage(raw),
        relay_descriptor("exact", keyword="wedding calculator"),
    )
    assert result.get("keyword") == "wedding calculator"
    assert result.get("volume") == 1000
    assert result.get("kd") == 20
    assert result.get("cpc") == 0.2
    assert result.get("metric_source") == "Semrush"
    assert result.get("metric_database") == "us"
    assert result.get("metric_stage") == "exact"
    assert result.get("relay_origin") == "https://sem.3ue.com/"
    assert result.get("provenance_ref")
    assert "response" not in result


def test_semrush_ideas_collect_normalizes_rows_instead_of_returning_raw_response():
    semrush = load_module("semrush_relay_collector_ideas", SEMRUSH)
    raw = {
        "data": {
            "rows": [
                {"keyword": "wedding cost calculator", "volume": 900, "kd": 22},
                {"keyword": "wedding budget calculator", "volume": 1200, "kd": 25},
            ]
        }
    }
    result = semrush.collect(
        FakePage(raw),
        relay_descriptor("ideas", seed="wedding calculator"),
    )
    assert result.get("seed") == "wedding calculator"
    assert [row["keyword"] for row in result.get("rows", [])] == [
        "wedding cost calculator",
        "wedding budget calculator",
    ]
    assert result.get("metric_source") == "Semrush"
    assert result.get("provenance_ref")
    assert "response" not in result


def test_semrush_exact_schema_mismatch_fails_closed():
    semrush = load_module("semrush_relay_collector_bad_schema", SEMRUSH)
    raw = {"data": {"rows": [{"keyword": "wedding calculator", "volume": 1000}]}}
    try:
        semrush.collect(FakePage(raw), relay_descriptor("exact", keyword="wedding calculator"))
    except RuntimeError as exc:
        assert "schema" in str(exc).lower() or "missing" in str(exc).lower()
    else:
        raise AssertionError("exact schema mismatch must fail closed")


def test_stage6_numeric_sanity_rejects_impossible_values():
    validator = load_module("stage_validator_numeric", VALIDATOR)
    contracts = json.loads(CONTRACTS.read_text(encoding="utf-8"))
    for row, field in [
        (exact_row(volume=-1), "volume"),
        (exact_row(kd=101), "kd"),
        (exact_row(cpc=-0.01), "cpc"),
    ]:
        errors = validator.validate_stage("stage6_exact", row, contracts)
        assert any(field in error for error in errors)


def test_mixed_batch_reports_partial_and_nonzero_exit(tmp_path):
    input_path = tmp_path / "rows.json"
    report_path = tmp_path / "report.json"
    input_path.write_text(json.dumps([exact_row(), exact_row(keyword="bad", cpc=None)]), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--stage",
            "stage6_exact",
            "--input",
            str(input_path),
            "--report",
            str(report_path),
        ],
        text=True,
        capture_output=True,
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "PARTIAL"
    assert report["complete_count"] == 1
    assert report["blocked_count"] == 1
    assert report["blocked"][0]["errors"]
    assert result.returncode != 0


def test_kgr_merge_joins_verified_exact_volume_and_google_intitle_then_evaluator_calculates():
    assert MERGER.exists(), "deterministic KGR evidence merger is missing"
    merger = load_module("kgr_evidence_merge", MERGER)
    evaluator = load_module("evaluate_candidates_for_kgr", EVALUATOR)
    contracts = json.loads(CONTRACTS.read_text(encoding="utf-8"))
    intitle = {
        "keyword": "wedding calculator",
        "intitle_results": 50,
        "source": "Google",
        "market": "US",
        "observed_at": "2026-08-27T00:10:00Z",
        "evidence_ref": "evidence/google-intitle.png",
    }
    merged = merger.merge_exact_and_intitle(exact_row(), intitle, contracts)
    assert merged["volume"] == 1000
    assert merged["intitle_results"] == 50
    assert merged["exact_provenance_ref"] == "evidence/semrush-exact.json"
    assert merged["intitle_provenance_ref"] == "evidence/google-intitle.png"
    evaluated = evaluator.normalize(merged, "final")
    assert evaluated["kgr"] == 0.05


def test_kgr_merge_rejects_keyword_mismatch():
    assert MERGER.exists(), "deterministic KGR evidence merger is missing"
    merger = load_module("kgr_evidence_merge_mismatch", MERGER)
    contracts = json.loads(CONTRACTS.read_text(encoding="utf-8"))
    intitle = {
        "keyword": "travel checklist",
        "intitle_results": 50,
        "source": "Google",
        "market": "US",
        "observed_at": "2026-08-27T00:10:00Z",
        "evidence_ref": "evidence/google-intitle.png",
    }
    try:
        merger.merge_exact_and_intitle(exact_row(), intitle, contracts)
    except ValueError as exc:
        assert "keyword" in str(exc).lower()
    else:
        raise AssertionError("keyword mismatch must fail closed")


def test_trends_parser_extracts_observed_temporal_series():
    google = load_module("google_live_collector_trends", GOOGLE)
    assert hasattr(google, "parse_trends_timeline"), "Google Trends temporal payload parser is missing"
    payload = {
        "default": {
            "timelineData": [
                {"time": "1767225600", "formattedTime": "Jan 1, 2026", "value": [20]},
                {"time": "1767830400", "formattedTime": "Jan 8, 2026", "value": [35]},
            ]
        }
    }
    series = google.parse_trends_timeline(payload)
    assert series == [
        {"time": "1767225600", "formatted_time": "Jan 1, 2026", "value": 20},
        {"time": "1767830400", "formatted_time": "Jan 8, 2026", "value": 35},
    ]


def test_finalist_trend_contract_requires_real_temporal_series():
    validator = load_module("stage_validator_trends", VALIDATOR)
    contracts = json.loads(CONTRACTS.read_text(encoding="utf-8"))
    screenshot_only = {
        "keyword": "dream meaning",
        "is_finalist": True,
        "google_trends_source": "Google Trends",
        "google_trends_observed_at": "2026-08-27T00:00:00Z",
        "google_trends_evidence_ref": "evidence/trends.png",
    }
    errors = validator.validate_stage("finalist_trend", screenshot_only, contracts)
    assert any("series" in error for error in errors)
