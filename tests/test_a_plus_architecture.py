from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_selection_does_not_own_discovery_steps():
    text = read("skills/seo-keyword-selection/SKILL.md")
    assert "starts at the former Step 5" in text
    assert "belong to `seo-keyword-discovery`" in text


def test_discovery_does_not_own_final_opportunity_decision():
    text = read("skills/seo-keyword-discovery/SKILL.md")
    assert "do not make final opportunity decisions" in text
    assert "does not own Exact qualification, KGR, SERP upgrade, KDRoi" in text


def test_full_discovery_requires_coverage_contract_and_semrush():
    text = read("skills/seo-keyword-discovery/SKILL.md")
    assert "Default Full Traditional Discovery requires Semrush Ideas/Related" in text
    assert "single Full Discovery coverage gate" in text
    assert "Google evidence is retained when Semrush is blocked" in text
    assert "Full Coverage Contract remains `BLOCKED`" in text


def test_discovery_branch_and_competitor_boundaries_are_explicit():
    text = read("skills/seo-keyword-discovery/SKILL.md")
    assert "already observed candidate" in text
    assert "Competitor Organic Keywords are a domain/root-cluster coverage source" in text
    assert "competitor_sweep=not_configured" in text
    assert "does not add Trends novelty" in text


def test_emerging_confirmed_route_skips_discovery():
    text = read("skills/emerging-keyword-monitor/references/routing-rules.md")
    assert "enters `seo-keyword-selection` **directly**" in text
    assert "must never route through `seo-keyword-discovery`" in text
    assert "never rerun Seed generation, Google Autocomplete, or Semrush Ideas" in text


def test_mapping_does_not_restore_generic_discovery_ownership():
    text = read("skills/seo-page-keyword-mapping/references/workflow.md")
    assert "Page-scoped keyword evidence / normalization / ownership expansion" in text
    assert "not** the owner of generic domain/root/Seed discovery" in text


def test_human_final_decision_remains_explicit():
    text = read("skills/seo-keyword-selection/references/selection-sop.md")
    assert "## 20. Human final decision" in text
    assert "No hook or evaluator replaces this decision" in text
