from pathlib import Path


SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"
SOURCE = Path(__file__).resolve().parents[1] / "references" / "source-policy.md"


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


def test_emerging_skill_reports_first_trusted_signal_immediately():
    text = skill_text()

    assert "第一次可信信号" in text
    assert "立即报告" in text
    assert "7/30 天窗口只用于后续确认" in text
    assert "不是发现等待期" in text


def test_emerging_skill_uses_verified_semrush_relay_contract():
    skill = skill_text()
    source = SOURCE.read_text(encoding="utf-8")

    for text in (skill, source):
        assert "sem.3ue.com" in text
        assert "不得改走需要 API units 的官方 Semrush API/connector" in text
    assert "中转会话失效" in source


def test_emerging_skill_defaults_user_visible_output_to_chinese():
    text = skill_text()

    assert "用户可见输出默认使用中文" in text
    assert "内部 canonical 字段" in text


def test_emerging_skill_prefers_google_sheet_as_auditable_workspace():
    text = skill_text()

    assert "Google Sheet" in text
    assert "默认人工可审计工作台" in text
    assert "不是执行该 Skill 的硬依赖" in text
