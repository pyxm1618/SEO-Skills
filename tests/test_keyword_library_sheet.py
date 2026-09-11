import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WRITER = ROOT / "runtime" / "keyword_library_sheet.py"


def load_writer(name="keyword_library_sheet_test"):
    spec = importlib.util.spec_from_file_location(name, WRITER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def col_index(letters):
    value = 0
    for char in letters:
        value = value * 26 + (ord(char) - ord("A") + 1)
    return value - 1


class FakeWorksheet:
    def __init__(self, values=None):
        self.values = [list(row) for row in (values or [])]
        self.hidden = []

    def get_all_values(self):
        return [list(row) for row in self.values]

    def update(self, range_name, values):
        start = range_name.split(":", 1)[0]
        letters = "".join(ch for ch in start if ch.isalpha())
        digits = "".join(ch for ch in start if ch.isdigit())
        row_index = int(digits) - 1
        column_index = col_index(letters)
        while len(self.values) <= row_index:
            self.values.append([])
        for row_offset, incoming in enumerate(values):
            target_row = row_index + row_offset
            while len(self.values) <= target_row:
                self.values.append([])
            while len(self.values[target_row]) < column_index + len(incoming):
                self.values[target_row].append("")
            for offset, value in enumerate(incoming):
                self.values[target_row][column_index + offset] = str(value)

    def append_rows(self, values):
        self.values.extend([list(map(str, row)) for row in values])

    def hide_columns(self, start, end):
        self.hidden.append((start, end))


def row_dict(writer, sheet, row_number=2):
    header = sheet.values[0]
    row = sheet.values[row_number - 1]
    return {name: (row[index] if index < len(row) else "") for index, name in enumerate(header)}


def test_identity_requires_explicit_market_and_language():
    writer = load_writer("identity_requires_context")
    with pytest.raises(ValueError, match="market"):
        writer.resolve_identity({"keyword": "AI Logo Generator"})
    with pytest.raises(ValueError, match="language"):
        writer.resolve_identity({"keyword": "AI Logo Generator", "market": "US"})


def test_identity_context_precedence_is_record_then_run_then_delivery():
    writer = load_writer("identity_precedence")
    identity = writer.resolve_identity(
        {"keyword": "  AI   Logo Generator ", "market": "GB", "language": "en-GB"},
        run_context={"market": "US", "language": "en"},
        delivery_context={"market": "CA", "language": "fr"},
    )
    assert identity.normalized_keyword == "ai logo generator"
    assert identity.market == "GB"
    assert identity.language == "en-GB"
    assert identity.stable_key == "ai logo generator | GB | en-GB"

    run_identity = writer.resolve_identity(
        {"keyword": "AI Logo Generator"},
        run_context={"market": "US", "language": "en"},
        delivery_context={"market": "CA", "language": "fr"},
    )
    assert run_identity.stable_key == "ai logo generator | US | en"


def test_discovery_creates_one_row_and_initializes_human_status():
    writer = load_writer("discovery_create")
    sheet = FakeWorksheet()
    result = writer.upsert_records(
        sheet,
        "discovery",
        [{
            "keyword": "AI Logo Generator",
            "source": "google_autocomplete",
            "source_seed": "ai logo",
            "candidate_id": "c1",
            "batch_id": "b1",
            "evidence_receipt_ref": "evidence/a.json",
        }],
        run_context={"market": "US", "language": "en"},
    )
    assert result["appended_count"] == 1
    assert len(sheet.values) == 2
    row = row_dict(writer, sheet)
    assert row["关键词"] == "AI Logo Generator"
    assert row["状态"] == "新发现"
    assert row["趋势类型"] == "unknown"
    assert row["月搜索量"] == "unknown"
    assert row["stable_keyword_key"] == "ai logo generator | US | en"


def test_same_keyword_market_language_reuses_row_but_different_market_does_not():
    writer = load_writer("identity_upsert")
    sheet = FakeWorksheet()
    writer.upsert_records(
        sheet,
        "discovery",
        [{"keyword": "AI Logo Generator", "source": "a", "candidate_id": "c1"}],
        run_context={"market": "US", "language": "en"},
    )
    writer.upsert_records(
        sheet,
        "discovery",
        [{"keyword": " ai   logo generator ", "source": "b", "candidate_id": "c2"}],
        run_context={"market": "US", "language": "en"},
    )
    assert len(sheet.values) == 2

    writer.upsert_records(
        sheet,
        "discovery",
        [{"keyword": "AI Logo Generator", "source": "c", "candidate_id": "c3"}],
        run_context={"market": "GB", "language": "en"},
    )
    assert len(sheet.values) == 3


def test_cross_skill_field_patches_do_not_overwrite_each_other():
    writer = load_writer("field_isolation")
    sheet = FakeWorksheet()
    context = {"market": "US", "language": "en"}
    writer.upsert_records(sheet, "discovery", [{"keyword": "AI Logo Generator", "source": "google_autocomplete"}], run_context=context)
    writer.upsert_records(
        sheet,
        "selection",
        [{"keyword": "AI Logo Generator", "volume": 1200, "difficulty": 22, "cpc": 1.5, "kdroi": 81.81818182, "kgr": 0.1, "mechanical_status": "do_candidate"}],
        run_context=context,
    )
    writer.upsert_records(
        sheet,
        "emerging",
        [{"keyword": "AI Logo Generator", "estimated_birth_window": "2026-08", "signal_type": "net_new", "demand_history_type": "newly_observed", "growth_rate": 2.4, "status": "emerging"}],
        run_context=context,
    )
    row = row_dict(writer, sheet)
    assert row["CPC"] == "1.5"
    assert row["KDRoi"] == "81.81818182"
    assert row["出生窗口"] == "2026-08"
    assert row["趋势类型"] == "新词"

    writer.upsert_records(
        sheet,
        "selection",
        [{"keyword": "AI Logo Generator", "cpc": 2.0}],
        run_context=context,
    )
    row = row_dict(writer, sheet)
    assert row["出生窗口"] == "2026-08"
    assert row["趋势类型"] == "新词"
    assert row["CPC"] == "2.0"


def test_human_status_is_never_overwritten_after_creation():
    writer = load_writer("human_status")
    sheet = FakeWorksheet()
    context = {"market": "US", "language": "en"}
    writer.upsert_records(sheet, "discovery", [{"keyword": "AI Logo Generator"}], run_context=context)
    status_index = sheet.values[0].index("状态")
    sheet.values[1][status_index] = "已选"

    writer.upsert_records(sheet, "discovery", [{"keyword": "AI Logo Generator", "workflow_status": "放弃"}], run_context=context)
    writer.upsert_records(sheet, "selection", [{"keyword": "AI Logo Generator", "mechanical_status": "principle_eliminate_kd"}], run_context=context)
    writer.upsert_records(sheet, "emerging", [{"keyword": "AI Logo Generator", "status": "noise"}], run_context=context)

    row = row_dict(writer, sheet)
    assert row["状态"] == "已选"
    assert row["selection_mechanical_status"] == "principle_eliminate_kd"
    assert row["emerging_status"] == "noise"


def test_missing_metrics_are_literal_unknown_not_blank_zero_or_false():
    writer = load_writer("unknown_values")
    sheet = FakeWorksheet()
    writer.upsert_records(
        sheet,
        "selection",
        [{"keyword": "AI Logo Generator", "volume": None, "difficulty": None, "cpc": "", "kdroi": None}],
        run_context={"market": "US", "language": "en"},
    )
    row = row_dict(writer, sheet)
    for header in ("月搜索量", "KD", "CPC", "KDRoi"):
        assert row[header] == "unknown"


def test_traditional_discovery_never_marks_keyword_old_or_new_without_temporal_evidence():
    writer = load_writer("discovery_age")
    sheet = FakeWorksheet()
    writer.upsert_records(
        sheet,
        "discovery",
        [{"keyword": "AI Logo Generator", "source": "google_autocomplete"}],
        run_context={"market": "US", "language": "en"},
    )
    assert row_dict(writer, sheet)["趋势类型"] == "unknown"


def test_emerging_trend_type_uses_only_canonical_temporal_evidence():
    writer = load_writer("emerging_trend")
    sheet = FakeWorksheet()
    context = {"market": "US", "language": "en"}
    writer.upsert_records(sheet, "emerging", [{"keyword": "new", "signal_type": "net_new"}], run_context=context)
    writer.upsert_records(sheet, "emerging", [{"keyword": "up", "growth_rate": 1.2}], run_context=context)
    writer.upsert_records(sheet, "emerging", [{"keyword": "flat", "growth_rate": 0}], run_context=context)
    writer.upsert_records(sheet, "emerging", [{"keyword": "down", "growth_rate": -0.4}], run_context=context)
    writer.upsert_records(sheet, "emerging", [{"keyword": "unknown trend", "status": "watch"}], run_context=context)
    got = {row_dict(writer, sheet, row_no)["关键词"]: row_dict(writer, sheet, row_no)["趋势类型"] for row_no in range(2, 7)}
    assert got == {"new": "新词", "up": "上升", "flat": "平稳", "down": "下降", "unknown trend": "unknown"}


def test_nonempty_incompatible_sheet_is_not_rewritten():
    writer = load_writer("schema_safety")
    sheet = FakeWorksheet(values=[["legacy", "header"], ["real", "data"]])
    with pytest.raises(RuntimeError, match="schema"):
        writer.upsert_records(
            sheet,
            "discovery",
            [{"keyword": "AI Logo Generator"}],
            run_context={"market": "US", "language": "en"},
        )
    assert sheet.values == [["legacy", "header"], ["real", "data"]]
