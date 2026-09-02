import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = ROOT / "runtime" / "stage_validator.py"
CONTRACTS_PATH = ROOT / "runtime" / "stage_contracts.json"
COLLECTOR_PATH = ROOT / "runtime" / "collectors" / "google_live_collector.py"
BINDING_PATH = ROOT / "runtime" / "evidence_binding.py"
HOOK_PATH = ROOT / "runtime" / "stage_hook.py"
EXPAND_SEEDS = ROOT / "skills" / "seo-keyword-discovery" / "scripts" / "expand_seeds.py"
CLUSTER = ROOT / "skills" / "seo-keyword-selection" / "scripts" / "cluster_by_serp.py"
QUERY_ROOTS = ROOT / "skills" / "keyword-root-library" / "scripts" / "query_roots.py"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def contracts():
    return json.loads(CONTRACTS_PATH.read_text(encoding="utf-8"))


def expansions_row(**overrides):
    row = {
        "seed": "angel number meaning",
        "people_also_ask": ["How do I know my angel number?"],
        "related_searches": ["angel number calculator", "what is my angel number"],
        "expansion_count": 3,
        "market": "US",
        "language": "en",
        "observed_at": "2026-09-01T10:00:00Z",
        "source": "google_serp_expansions",
        "evidence_ref": "evidence/expansions-angel.png",
    }
    row.update(overrides)
    return row


# --- country-redirect recovery -------------------------------------------------


def test_every_google_search_navigation_goes_through_goto_google():
    """A raw page.goto to a google.com search URL re-opens the ccTLD redirect hole."""
    source = COLLECTOR_PATH.read_text(encoding="utf-8")
    offenders = [
        line.strip()
        for line in source.splitlines()
        if "page.goto(" in line and "www.google.com/search" in line
    ]
    assert offenders == [], f"these must use goto_google: {offenders}"
    # trends.google.com is a different origin with no ccTLD redirect, so it stays direct.
    assert 'goto_google(page, f"https://www.google.com/search' in source


def test_goto_google_retries_through_ncr():
    source = COLLECTOR_PATH.read_text(encoding="utf-8")
    helper = source.split("def goto_google", 1)[1].split("\ndef ", 1)[0]
    assert "https://www.google.com/ncr" in helper
    assert helper.count("page.goto(url") == 2, "must retry the original URL once after /ncr"
    assert "assert_google(page)" in helper


# --- discovery_expansions contract ---------------------------------------------


def test_expansions_contract_accepts_real_shape():
    validator = load(VALIDATOR_PATH, "sv_exp_ok")
    errors = validator.validate_stage("discovery_expansions", expansions_row(), contracts())
    assert errors == []


def test_expansions_contract_rejects_empty_result():
    validator = load(VALIDATOR_PATH, "sv_exp_empty")
    errors = validator.validate_stage(
        "discovery_expansions",
        expansions_row(people_also_ask=[], related_searches=[], expansion_count=0),
        contracts(),
    )
    assert errors, "zero expansions must not satisfy the contract"


def test_expansions_contract_rejects_wrong_source():
    validator = load(VALIDATOR_PATH, "sv_exp_src")
    errors = validator.validate_stage(
        "discovery_expansions", expansions_row(source="google_autocomplete"), contracts()
    )
    assert errors


def test_expansions_count_must_match_observed_terms():
    """The stage contract gates on the count, so binding derives it, never trusts it."""
    binding = load(BINDING_PATH, "eb_count")
    row = expansions_row(expansion_count=99)
    try:
        binding._verify_google_semantics  # noqa: B018 - presence check
    except AttributeError:  # pragma: no cover
        raise AssertionError("google semantics verifier missing")
    source = BINDING_PATH.read_text(encoding="utf-8")
    assert "expansions count differs from observed terms" in source
    assert row["expansion_count"] != len(row["people_also_ask"]) + len(row["related_searches"])


def test_expansions_registered_across_every_integrity_layer():
    """A stage registered in only some layers is the gap this suite exists to catch."""
    assert "discovery_expansions" in contracts()
    binding = load(BINDING_PATH, "eb_reg")
    assert "google_serp_expansions" in binding.EXPECTED_COLLECTORS
    assert "google_serp_expansions" in binding.COLLECTOR_FILES
    assert "google_serp_expansions" in binding.REQUIRED_ARTIFACT_ROLES
    validator = load(VALIDATOR_PATH, "sv_reg")
    assert validator.PRODUCTION_BINDINGS["discovery_expansions"] == "google_serp_expansions"
    hook = load(HOOK_PATH, "hook_reg")
    assert hook.STAGE_EVIDENCE_TYPES["discovery_expansions"] == "google_serp_expansions"


# --- fail-closed production binding --------------------------------------------


def test_unregistered_stage_fails_closed_in_production():
    validator = load(VALIDATOR_PATH, "sv_failclosed")
    errors = validator._validate_production_binding("totally_new_stage", {"x": 1})
    assert errors, "an unregistered stage must not silently skip evidence binding"
    assert "no production evidence binding registered" in errors[0]


def test_evidence_exempt_stages_stay_exempt():
    validator = load(VALIDATOR_PATH, "sv_exempt")
    assert validator._validate_production_binding("discovery_handoff", {"batch_id": "b1"}) == []


def test_every_contract_stage_is_bound_or_explicitly_exempt():
    validator = load(VALIDATOR_PATH, "sv_cover")
    for stage in contracts():
        assert (
            stage in validator.PRODUCTION_BINDINGS or stage in validator.EVIDENCE_EXEMPT_STAGES
        ), f"{stage} would fail closed at production time"


# --- seed expansion ------------------------------------------------------------


def run(script, *args):
    return subprocess.run(
        [sys.executable, str(script), *args], capture_output=True, text=True, cwd=str(ROOT)
    )


def test_expand_seeds_marks_everything_as_analysis():
    out = run(EXPAND_SEEDS, "--domain", "tarot", "--topic", "tarot", "--format", "json", "--limit", "30")
    assert out.returncode == 0, out.stderr
    payload = json.loads(out.stdout)
    assert payload["seeds"]
    assert {row["data_state"] for row in payload["seeds"]} == {"analysis"}
    for row in payload["seeds"]:
        assert "volume" not in row and "evidence_ref" not in row


def test_expand_seeds_applies_universal_patterns():
    out = run(EXPAND_SEEDS, "--domain", "tarot", "--topic", "tarot", "--format", "json", "--limit", "200")
    seeds = {row["seed"] for row in json.loads(out.stdout)["seeds"]}
    assert "tarot calculator" in seeds, "universal root patterns must be applied to the topic"


def test_expand_seeds_blocks_unknown_domain():
    out = run(EXPAND_SEEDS, "--domain", "no-such-domain-xyz")
    assert out.returncode == 2
    assert "BLOCKED" in out.stderr


def test_apply_pattern_skips_literal_roots():
    module = load(EXPAND_SEEDS, "expand_seeds")
    assert module.apply_pattern("x calculator", "tarot") == "tarot calculator"
    assert module.apply_pattern("free x", "tarot") == "free tarot"
    assert module.apply_pattern("dog age calculator", "tarot") is None


# --- SERP overlap clustering ---------------------------------------------------


def write_serp(tmp_path, keyword, urls):
    path = tmp_path / f"{keyword.replace(' ', '-')}.json"
    path.write_text(
        json.dumps(
            {
                "keyword": keyword,
                "results": [{"rank": i + 1, "url": u, "title": "t"} for i, u in enumerate(urls)],
            }
        ),
        encoding="utf-8",
    )
    return str(path)


def test_cluster_merges_at_threshold_and_splits_below(tmp_path):
    a = write_serp(tmp_path, "kw a", ["https://x.com/1", "https://y.com/2", "https://z.com/3", "https://p.com/4"])
    b = write_serp(tmp_path, "kw b", ["https://x.com/1", "https://y.com/2", "https://z.com/3", "https://q.com/5"])
    c = write_serp(tmp_path, "kw c", ["https://m.com/9", "https://n.com/8", "https://o.com/7", "https://r.com/6"])
    out = run(CLUSTER, "--input", a, b, c, "--threshold", "3", "--format", "json")
    assert out.returncode == 0, out.stderr
    report = json.loads(out.stdout)
    assert report["cluster_count"] == 2
    assert report["data_state"] == "calculated"
    merged = [c["members"] for c in report["clusters"] if len(c["members"]) == 2][0]
    assert sorted(merged) == ["kw a", "kw b"]


def test_cluster_url_canonicalisation_ignores_cosmetic_differences():
    module = load(CLUSTER, "cluster_by_serp")
    variants = [
        "https://www.example.com/page/",
        "http://example.com/page",
        "https://example.com/page?utm_source=x#frag",
    ]
    assert len({module.canonical_url(v) for v in variants}) == 1


def test_cluster_requires_two_inputs(tmp_path):
    only = write_serp(tmp_path, "kw a", ["https://x.com/1"])
    out = run(CLUSTER, "--input", only)
    assert out.returncode == 2
    assert "at least two" in out.stderr


def test_cluster_rejects_evidence_without_results(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"keyword": "kw", "results": []}), encoding="utf-8")
    other = write_serp(tmp_path, "kw b", ["https://x.com/1"])
    out = run(CLUSTER, "--input", str(bad), other)
    assert out.returncode == 2
    assert "BLOCKED" in out.stderr


# --- root library visibility ---------------------------------------------------


def test_root_overview_lists_domains_beyond_the_documentation_example():
    out = run(QUERY_ROOTS, "--overview")
    assert out.returncode == 0, out.stderr
    for domain in ("wedding", "tarot", "astrology", "bitcoin"):
        assert domain in out.stdout, f"{domain} missing from coverage overview"
    assert "通用词根" in out.stdout


def test_root_overview_needs_no_other_arguments():
    """A non-technical operator must be able to see coverage with one command."""
    out = run(QUERY_ROOTS, "--overview")
    assert out.returncode == 0
    assert "行业" in out.stdout
