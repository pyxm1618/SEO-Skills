from pathlib import Path


SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"
SOURCE = Path(__file__).resolve().parents[1] / "references" / "source-acquisition.md"


def test_selection_skill_uses_verified_semrush_relay_contract():
    skill = SKILL.read_text(encoding="utf-8")
    source = SOURCE.read_text(encoding="utf-8")

    for text in (skill, source):
        assert "sem.3ue.com" in text
        assert "不得改走需要 API units 的官方 Semrush API/connector" in text
    assert "中转会话失效" in source


def test_selection_skill_defaults_user_visible_output_to_chinese():
    text = SKILL.read_text(encoding="utf-8")

    assert "用户可见输出默认使用中文" in text
    assert "内部 canonical 字段" in text


def test_selection_skill_prefers_google_sheet_as_auditable_workspace():
    text = SKILL.read_text(encoding="utf-8")

    assert "Google Sheet" in text
    assert "默认人工可审计工作台" in text
    assert "不是执行该 Skill 的硬依赖" in text
