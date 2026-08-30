import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "runtime" / "stage_contracts.json"
HOOK = ROOT / "runtime" / "stage_hook.py"
SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_contracts_cover_related_timeline_and_radar_run():
    contracts = json.loads(CONTRACTS.read_text(encoding="utf-8"))
    hook = load_module("stage_hook_radar_contracts_red", HOOK)

    assert {"trends_related", "trends_timeline", "emerging_radar_run"} <= set(contracts)
    assert {"trends_related", "trends_timeline", "emerging_radar_run"} <= set(hook.CANONICAL_STAGES)


def test_skill_documents_timeframe_and_google_breakout_separation():
    text = SKILL.read_text(encoding="utf-8")
    assert "different timeframe" in text.lower()
    assert "google_rising_label" in text
    assert "logged-out" in text or "logged out" in text
