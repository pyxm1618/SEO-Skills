import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = ROOT / "runtime" / "collectors" / "google_trends_collector.py"


def _load_collector():
    collector_dir = str(COLLECTOR.parent)
    inserted = collector_dir not in sys.path
    if inserted:
        sys.path.insert(0, collector_dir)
    try:
        spec = importlib.util.spec_from_file_location("trends_rate_limit_test", COLLECTOR)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        if inserted:
            sys.path.remove(collector_dir)


class _Body:
    def inner_text(self, timeout=5000):
        return "429. That's an error. We're sorry, but you have sent too many requests to us recently. Please try again later."


class _Page:
    url = "https://trends.google.com/trends/explore?geo=US&date=today+12-m&q=perfume"

    def locator(self, selector):
        assert selector == "body"
        return _Body()


def test_google_trends_429_is_an_explicit_rate_limit_blocker():
    trends = _load_collector()

    with pytest.raises(RuntimeError, match=r"(?i)(429|rate[_ -]?limit|too many requests)"):
        trends._assert_trends_page(_Page())
