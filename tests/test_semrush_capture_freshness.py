import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = ROOT / "runtime" / "collectors" / "semrush_relay_collector.py"


def load_collector():
    spec = importlib.util.spec_from_file_location("semrush_relay_freshness", COLLECTOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_load_request_rejects_stale_historical_capture(tmp_path):
    collector = load_collector()
    descriptor = {
        "path": "/captured/current-path",
        "method": "POST",
        "body": {},
        "capture_observed_at": "2000-01-01T00:00:00Z",
        "capture_evidence_ref": "evidence/historical-network-capture.json",
        "mode": "exact",
        "metric_database": "us",
        "keyword": "wedding calculator",
    }
    path = tmp_path / "request.json"
    path.write_text(json.dumps(descriptor), encoding="utf-8")

    try:
        collector.load_request(path)
    except RuntimeError as exc:
        assert "stale" in str(exc).lower() or "fresh" in str(exc).lower()
    else:
        raise AssertionError("historical relay request descriptors must not satisfy current-live acquisition")
