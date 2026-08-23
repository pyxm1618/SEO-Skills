from pathlib import Path


SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"


def skill_text() -> str:
    return SKILL.read_text(encoding="utf-8")


def test_skill_requires_canonical_runtime_enums():
    text = skill_text()

    assert "Do not invent aliases such as `candidate`" in text
    assert "`net_new`, `breakout`, `emerging_variant`, or `unknown`" in text
    assert "`new_expression`, `typo`, `modifier_shift`, or `unknown`" in text
    assert (
        "`new_signal`, `watch`, `emerging`, `breakout`, `mature`, `noise`, "
        "or `insufficient_evidence`"
    ) in text


def test_skill_separates_hypothesis_from_confirmed_classification():
    text = skill_text()

    assert "possible_breakout" in text
    assert "must not emit `signal_type=breakout`" in text
    assert "must not emit `status=emerging` or `status=breakout`" in text


def test_skill_requires_canonical_routing():
    text = skill_text()

    assert (
        "`selection_handoff`, `root_candidate_handoff`, `new_root_watchlist`, "
        "`monitor_only`, or `no_handoff`"
    ) in text
    assert "Only `status in {emerging, breakout}` may produce `selection_handoff`" in text
    assert "`new_signal` and `watch` must remain `monitor_only`" in text
