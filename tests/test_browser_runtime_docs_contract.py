from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "runtime" / "BROWSER_RUNTIME_CONTRACT.md"


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_shared_browser_runtime_contract_exists_and_covers_current_behavior():
    assert CONTRACT.is_file()
    text = CONTRACT.read_text(encoding="utf-8")
    for required in (
        "headful",
        "SEO_GOOGLE_CDP_URL",
        "worker page",
        "browser_page_leak",
        "NEEDS_HUMAN",
        "exit code 3",
        "existing unresolved blocker",
        "fail closed",
        "headless",
        "HTTP fallback",
    ):
        assert required in text


def test_live_google_docs_reference_one_shared_runtime_contract():
    paths = (
        "README.md",
        "runtime/TRUST_BOUNDARY.md",
        "CLAUDE.md",
        "skills/emerging-keyword-monitor/SKILL.md",
        "skills/emerging-keyword-monitor/references/source-policy.md",
        "skills/seo-keyword-discovery/SKILL.md",
        "skills/seo-keyword-discovery/references/source-acquisition.md",
        "skills/seo-keyword-selection/SKILL.md",
        "skills/seo-keyword-selection/references/source-acquisition.md",
    )
    for path in paths:
        assert "runtime/BROWSER_RUNTIME_CONTRACT.md" in _read(path), path
