import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMRUSH = ROOT / "runtime" / "collectors" / "semrush_relay_collector.py"


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _DummyPW:
    def stop(self):
        return None


class _DummyBrowser:
    def close(self):
        return None


def make_semrush_exact(tmp_path, name="exact", payload=None):
    payload = dict(payload or {})
    keyword = str(payload.get("keyword") or "wedding calculator")
    volume = payload.get("volume", 1000)
    kd = payload.get("kd", 20)
    cpc = payload.get("cpc", 0.2)
    intent = payload.get("intent", ["commercial"])
    competition_level = payload.get("competition_level", "low")
    trend = list(payload.get("trend") or [50] * 12)
    observed_at = datetime.now(timezone.utc).isoformat()

    collector = _load_module(f"semrush_fixture_{name}", SEMRUSH)
    capture = tmp_path / f"{name}.capture.json"
    capture.write_text(json.dumps({
        "page_url": "https://sem.3ue.com/",
        "observed_at": observed_at,
        "request_path": "/api/exact",
        "fixture": True,
    }), encoding="utf-8")
    descriptor_path = tmp_path / f"{name}.request.json"
    descriptor = {
        "path": "/api/exact",
        "method": "POST",
        "body": {},
        "capture_observed_at": observed_at,
        "capture_evidence_ref": str(capture),
        "mode": "exact",
        "metric_database": "us",
        "keyword": keyword,
    }
    descriptor_path.write_text(json.dumps(descriptor), encoding="utf-8")

    response = {
        "jsonrpc": "2.0",
        "result": {
            "keywords": [{
                "phrase": keyword,
                "database": "us",
                "volume": volume,
                "difficulty": kd,
                "cpc": cpc,
                "intents": intent,
                "competition_level": competition_level,
                "trend": trend,
            }]
        },
    }
    output = tmp_path / f"{name}.json"
    raw_output = output.with_suffix(".raw.json")

    collector.connect_same_origin = lambda: (_DummyPW(), _DummyBrowser(), object())

    def fake_collect(_page, loaded_descriptor, raw_evidence_ref=None, raw_output_path=None):
        raw_path = Path(raw_output_path)
        raw_record = {
            "observed_at": observed_at,
            "relay_origin": "https://sem.3ue.com/",
            "request_method": loaded_descriptor["method"],
            "request_path": loaded_descriptor["path"],
            "capture_observed_at": loaded_descriptor["capture_observed_at"],
            "capture_evidence_ref": loaded_descriptor["capture_evidence_ref"],
            "mode": loaded_descriptor["mode"],
            "metric_database": loaded_descriptor["metric_database"],
            "seed": loaded_descriptor.get("seed"),
            "keyword": loaded_descriptor.get("keyword"),
            "response": response,
        }
        raw_path.write_text(json.dumps(raw_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return collector.normalize_exact(response, loaded_descriptor, observed_at, str(raw_path))

    collector.collect = fake_collect
    old_argv = sys.argv[:]
    try:
        sys.argv = [
            str(SEMRUSH),
            "--request", str(descriptor_path),
            "--output", str(output),
            "--raw-output", str(raw_output),
        ]
        rc = collector.main()
    finally:
        sys.argv = old_argv
    if rc != 0:
        raise AssertionError("Semrush collector fixture failed to emit bound evidence")
    bound = json.loads(output.read_text(encoding="utf-8"))
    return output, bound, raw_output, capture
