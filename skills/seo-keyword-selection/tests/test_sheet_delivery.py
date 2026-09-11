import importlib.util
import json
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[1]
SCRIPT = BASE / "scripts" / "evaluate_candidates.py"


def load_evaluator(name="selection_sheet_delivery"):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
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
            target = row_index + row_offset
            while len(self.values) <= target:
                self.values.append([])
            while len(self.values[target]) < column_index + len(incoming):
                self.values[target].append("")
            for offset, value in enumerate(incoming):
                self.values[target][column_index + offset] = str(value)

    def append_rows(self, values):
        self.values.extend([list(map(str, row)) for row in values])

    def hide_columns(self, start, end):
        self.hidden.append((start, end))


def row_dict(sheet, row_number=2):
    header = sheet.values[0]
    row = sheet.values[row_number - 1]
    return {name: row[index] if index < len(row) else "" for index, name in enumerate(header)}


def canonical_row(evaluator, **overrides):
    base = {
        "keyword": "ai logo generator",
        "volume": 1200,
        "difficulty": 20,
        "cpc": 1.5,
        "intitle_results": 120,
        "metric_source": "Semrush",
        "metric_database": "us",
        "metric_stage": "exact",
        "observed_at": "2026-09-11T00:00:00Z",
    }
    base.update(overrides)
    return evaluator.normalize(base, "final", {})


def seed_emerging_row(evaluator, sheet):
    evaluator.library.upsert_records(
        sheet,
        "emerging",
        [{
            "keyword": "ai logo generator",
            "signal_type": "net_new",
            "estimated_birth_window": "2026-08",
            "birth_confidence": "medium",
            "status": "emerging",
        }],
        run_context={"market": "US", "language": "en"},
    )


def test_selection_exposes_unified_library_default():
    evaluator = load_evaluator("selection_sheet_default")
    assert evaluator.DEFAULT_WORKSHEET == "关键词库"


def test_selection_delivery_patches_canonical_metrics_after_evaluation():
    evaluator = load_evaluator("selection_sheet_metrics")
    sheet = FakeWorksheet()
    row = canonical_row(evaluator)

    result = evaluator.deliver_to_sheet(
        sheet,
        [row],
        run_context={"market": "US", "language": "en"},
    )

    assert result["stable_row_count"] == 1
    written = row_dict(sheet)
    assert written["月搜索量"] == "1200"
    assert written["KD"] == "20"
    assert written["CPC"] == "1.5"
    assert written["KDRoi"] == "90.0"
    assert written["KGR"] == "0.1"
    assert written["selection_mechanical_status"] == "do_candidate"


def test_selection_delivery_preserves_emerging_fields_and_human_status():
    evaluator = load_evaluator("selection_sheet_preserve")
    sheet = FakeWorksheet()
    seed_emerging_row(evaluator, sheet)
    mapping = {name: index for index, name in enumerate(sheet.values[0])}
    sheet.values[1][mapping["状态"]] = "已选"

    evaluator.deliver_to_sheet(
        sheet,
        [canonical_row(evaluator, cpc=2.0)],
        run_context={"market": "US", "language": "en"},
    )

    written = row_dict(sheet)
    assert written["出生窗口"] == "2026-08"
    assert written["趋势类型"] == "新词"
    assert written["emerging_status"] == "emerging"
    assert written["状态"] == "已选"
    assert written["CPC"] == "2.0"


def test_selection_mechanical_status_never_becomes_human_workflow_status():
    evaluator = load_evaluator("selection_sheet_status")
    sheet = FakeWorksheet()
    evaluator.deliver_to_sheet(
        sheet,
        [canonical_row(evaluator, difficulty=60)],
        run_context={"market": "US", "language": "en"},
    )
    written = row_dict(sheet)
    assert written["selection_mechanical_status"] == "principle_eliminate_kd"
    assert written["状态"] == "新发现"


def test_missing_selection_metrics_write_literal_unknown():
    evaluator = load_evaluator("selection_sheet_unknown")
    sheet = FakeWorksheet()
    row = evaluator.normalize({"keyword": "ai logo generator"}, "final", {})
    evaluator.deliver_to_sheet(
        sheet,
        [row],
        run_context={"market": "US", "language": "en"},
    )
    written = row_dict(sheet)
    for header in ("月搜索量", "KD", "CPC", "KDRoi", "KGR"):
        assert written[header] == "unknown"


def test_intent_is_written_only_when_real_pass_through_value_exists():
    evaluator = load_evaluator("selection_sheet_intent")
    sheet = FakeWorksheet()
    evaluator.deliver_to_sheet(
        sheet,
        [canonical_row(evaluator, intent="transactional")],
        run_context={"market": "US", "language": "en"},
    )
    assert row_dict(sheet)["意图"] == "transactional"

    evaluator.deliver_to_sheet(
        sheet,
        [canonical_row(evaluator, intent="unknown", cpc=2.0)],
        run_context={"market": "US", "language": "en"},
    )
    assert row_dict(sheet)["意图"] == "transactional"


def test_selection_identity_context_is_strict():
    evaluator = load_evaluator("selection_sheet_identity")
    with pytest.raises(ValueError, match="market"):
        evaluator.deliver_to_sheet(FakeWorksheet(), [canonical_row(evaluator)])


def test_delivery_is_separate_from_metric_calculation():
    evaluator = load_evaluator("selection_sheet_separation")
    row = canonical_row(evaluator)
    assert row["kdroi"] == 90.0
    assert row["kgr"] == 0.1
    # Computing a canonical row alone must not require or touch a Sheet.
    assert "sheet_delivery" not in row


def test_sheet_output_cli_flag_exists_without_changing_default_json_output(tmp_path, monkeypatch, capsys):
    evaluator = load_evaluator("selection_sheet_cli_default")
    source = tmp_path / "input.json"
    source.write_text(json.dumps({"rows": [{"keyword": "x", "volume": 1000, "difficulty": 20, "cpc": 1}]}), encoding="utf-8")
    monkeypatch.setattr(
        evaluator.sys,
        "argv",
        ["evaluate_candidates.py", "--input", str(source), "--stage", "final", "--format", "json"],
    )
    assert evaluator.main() == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["rows"][0]["keyword"] == "x"


def test_sheet_output_cli_requires_final_stage(tmp_path, monkeypatch, capsys):
    evaluator = load_evaluator("selection_sheet_cli_stage")
    source = tmp_path / "input.json"
    source.write_text(json.dumps({"rows": [{"keyword": "x", "volume": 1000, "difficulty": 20}]}), encoding="utf-8")
    monkeypatch.setattr(
        evaluator.sys,
        "argv",
        [
            "evaluate_candidates.py", "--input", str(source), "--stage", "ideas", "--format", "json",
            "--sheet-output", "--market", "US", "--language", "en",
        ],
    )
    assert evaluator.main() == 2
    assert "final" in capsys.readouterr().err
