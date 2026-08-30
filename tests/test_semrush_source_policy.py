from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def runtime_python_files():
    yield from (ROOT / "runtime").rglob("*.py")
    for scripts in (ROOT / "skills").glob("*/scripts"):
        yield from scripts.rglob("*.py")


def test_runtime_has_no_official_semrush_api_or_provider_fallback():
    banned = [
        "api.semrush.com",
        "SEMRUSH_API_KEY",
        "semrush_api_key",
        "ahrefs_fallback",
        "alternative_provider",
    ]
    offenders = []
    for path in runtime_python_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in banned:
            if token in text:
                offenders.append(f"{path.relative_to(ROOT)}:{token}")
    assert offenders == []


def test_semrush_collector_is_same_origin_and_has_no_hardcoded_rpc_endpoint():
    path = ROOT / "runtime" / "collectors" / "semrush_relay_collector.py"
    text = path.read_text(encoding="utf-8")
    assert 'ALLOWED_HOST = "sem.3ue.com"' in text
    assert "/kwogw/v2/webapi" not in text
    assert "ideas.GetKeywords" not in text
    assert "keywords.GetInfo" not in text
    assert "credentials: 'include'" in text
