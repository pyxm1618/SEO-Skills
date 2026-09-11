import importlib.util
import json
import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parents[1]
EXPORTER = SKILL_ROOT / "scripts" / "export_to_sheet.py"


def load_module(name, path):
    scripts_dir = str(path.parent)
    sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.path.remove(scripts_dir)
    return module


def col_index(letters):
    value = 0
    for char in letters:
        value = value * 26 + (ord(char) - ord("A") + 1)
    return value - 1


class FakeWorksheet:
    def __init__(self, values=None, fail_on=None):
        self.values = [list(row) for row in (values or [])]
        self.fail_on = fail_on
        self.hidden = []

    def get_all_values(self):
        if self.fail_on == "get":
            raise RuntimeError("network is unavailable")
        return [list(row) for row in self.values]

    def update(self, range_name, values):
        if self.fail_on == "update":
            raise RuntimeError("permission denied")
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
        if self.fail_on == "append":
            raise RuntimeError("quota exceeded")
        self.values.extend([list(map(str, row)) for row in values])

    def hide_columns(self, start, end):
        self.hidden.append((start, end))


def database(records, **meta):
    payload = {"schema_version": 1, "records": records}
    payload.update(meta)
    return payload


def record(**overrides):
    base = {
        "domain": "wedding",
        "keyword": "wedding content creator",
        "discovery_source": "google_trends_rising",
        "status": "emerging",
        "signal_type": "net_new",
    }
    base.update(overrides)
    return base


def row_dict(sheet, row_number=2):
    header = sheet.values[0]
    row = sheet.values[row_number - 1]
    return {name: row[index] if index < len(row) else "" for index, name in enumerate(header)}


def seed_selection_row(exporter, sheet):
    library = exporter.library
    library.upsert_records(
        sheet,
        "selection",
        [{
            "keyword": "wedding content creator",
            "volume": 900,
            "difficulty": 24,
            "cpc": 1.2,
            "kdroi": 45.0,
            "mechanical_status": "do_candidate",
        }],
        run_context={"market": "US", "language": "en"},
    )


def test_default_worksheet_is_unified_keyword_library():
    exporter = load_module("emerging_sheet_default", EXPORTER)
    assert exporter.DEFAULT_WORKSHEET == "关键词库"


def test_emerging_updates_existing_stable_row_instead_of_creating_duplicate():
    exporter = load_module("emerging_same_row", EXPORTER)
    sheet = FakeWorksheet()
    seed_selection_row(exporter, sheet)

    result = exporter.export(
        sheet,
        database(
            [record(estimated_birth_window="2026-08", birth_confidence="high", growth_rate=2.4)],
            market="US",
            language="en",
        ),
    )

    assert result["stable_row_count"] == 1
    assert result["appended_count"] == 0
    assert len(sheet.values) == 2
    row = row_dict(sheet)
    assert row["趋势类型"] == "新词"
    assert row["出生窗口"] == "2026-08"
    assert row["birth_confidence"] == "high"
    assert row["emerging_status"] == "emerging"


def test_emerging_patch_preserves_selection_metrics_and_human_status():
    exporter = load_module("emerging_preserve_selection", EXPORTER)
    sheet = FakeWorksheet()
    seed_selection_row(exporter, sheet)
    mapping = {name: index for index, name in enumerate(sheet.values[0])}
    sheet.values[1][mapping["状态"]] = "已选"

    exporter.export(
        sheet,
        database(
            [record(signal_type="breakout", growth_rate=1.5, estimated_birth_window="unknown")],
            market="US",
            language="en",
        ),
    )

    row = row_dict(sheet)
    assert row["CPC"] == "1.2"
    assert row["KDRoi"] == "45.0"
    assert row["selection_mechanical_status"] == "do_candidate"
    assert row["状态"] == "已选"
    assert row["趋势类型"] == "上升"


def test_emerging_does_not_use_its_volume_or_kd_to_overwrite_selection_owned_metrics():
    exporter = load_module("emerging_metric_ownership", EXPORTER)
    sheet = FakeWorksheet()
    seed_selection_row(exporter, sheet)

    exporter.export(
        sheet,
        database(
            [record(volume=99999, kd=99, cpc=99, signal_type="breakout", growth_rate=1.0)],
            market="US",
            language="en",
        ),
    )

    row = row_dict(sheet)
    assert row["月搜索量"] == "900"
    assert row["KD"] == "24"
    assert row["CPC"] == "1.2"


def test_trend_type_requires_temporal_evidence_and_unknown_stays_unknown():
    exporter = load_module("emerging_trend_evidence", EXPORTER)
    sheet = FakeWorksheet()
    exporter.export(
        sheet,
        database([record(signal_type="unknown", status="watch")], market="US", language="en"),
    )
    assert row_dict(sheet)["趋势类型"] == "unknown"


def test_birth_window_uses_estimated_birth_window_not_first_observed_at():
    exporter = load_module("emerging_birth_window", EXPORTER)
    sheet = FakeWorksheet()
    exporter.export(
        sheet,
        database(
            [record(first_observed_at="2026-09-01T00:00:00Z", estimated_birth_window=None)],
            market="US",
            language="en",
        ),
    )
    row = row_dict(sheet)
    assert row["出生窗口"] == "unknown"
    assert row["first_observed_at"] == "2026-09-01T00:00:00Z"


def test_identity_context_is_strict_and_never_defaults_to_us_en():
    exporter = load_module("emerging_identity_context", EXPORTER)
    with pytest.raises(ValueError, match="market"):
        exporter.export(FakeWorksheet(), database([record()]))


def test_explicit_delivery_context_can_supply_identity():
    exporter = load_module("emerging_delivery_context", EXPORTER)
    sheet = FakeWorksheet()
    result = exporter.export(
        sheet,
        database([record()]),
        delivery_context={"market": "US", "language": "en"},
    )
    assert result["appended_count"] == 1
    assert row_dict(sheet)["stable_keyword_key"] == "wedding content creator | US | en"


def test_export_failure_is_reported_and_never_rewrites_local_outputs(tmp_path):
    exporter = load_module("emerging_failure", EXPORTER)
    db_path = tmp_path / "emerging-keywords.json"
    payload = database([record()], market="US", language="en")
    db_path.write_text(json.dumps(payload), encoding="utf-8")
    before = db_path.read_bytes()

    with pytest.raises(RuntimeError):
        exporter.export(FakeWorksheet(fail_on="append"), payload)

    assert db_path.read_bytes() == before


def test_cli_dry_run_needs_no_credentials_and_reports_stable_identity(tmp_path, capsys, monkeypatch):
    exporter = load_module("emerging_cli_dry", EXPORTER)
    db_path = tmp_path / "emerging-keywords.json"
    db_path.write_text(json.dumps(database([record()], market="US", language="en")), encoding="utf-8")

    def explode(*args, **kwargs):
        raise AssertionError("dry run must not open a worksheet")

    monkeypatch.setattr(sys, "argv", ["export_to_sheet.py", "--database", str(db_path), "--dry-run"])
    assert exporter.main(worksheet_factory=explode) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["worksheet"] == "关键词库"
    assert printed["record_count"] == 1
    assert printed["stable_row_count"] == 1


def test_cli_uses_shared_sheet_environment_and_blocks_missing_credentials(tmp_path, capsys, monkeypatch):
    exporter = load_module("emerging_cli_blocked", EXPORTER)
    db_path = tmp_path / "emerging-keywords.json"
    db_path.write_text(json.dumps(database([record()], market="US", language="en")), encoding="utf-8")
    monkeypatch.setenv("SEO_KEYWORD_SHEET_ID", "abc")
    monkeypatch.delenv("SEO_SHEETS_CREDENTIALS", raising=False)
    monkeypatch.setattr(sys, "argv", ["export_to_sheet.py", "--database", str(db_path)])
    assert exporter.main(worksheet_factory=lambda *a, **k: FakeWorksheet()) == 2
    assert "BLOCKED" in capsys.readouterr().err


def test_cli_explicit_market_language_supply_delivery_context(tmp_path, capsys, monkeypatch):
    exporter = load_module("emerging_cli_context", EXPORTER)
    db_path = tmp_path / "emerging-keywords.json"
    db_path.write_text(json.dumps(database([record()])), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["export_to_sheet.py", "--database", str(db_path), "--market", "US", "--language", "en", "--dry-run"],
    )
    assert exporter.main(worksheet_factory=lambda *a, **k: FakeWorksheet()) == 0
    assert json.loads(capsys.readouterr().out)["stable_row_count"] == 1


def test_record_without_keyword_is_rejected():
    exporter = load_module("emerging_keyword_required", EXPORTER)
    with pytest.raises(ValueError):
        exporter.export(
            FakeWorksheet(),
            database([{"domain": "wedding", "keyword": "  "}], market="US", language="en"),
        )


def test_tilde_paths_are_expanded(monkeypatch, tmp_path):
    exporter = load_module("emerging_tilde", EXPORTER)
    monkeypatch.setenv("HOME", str(tmp_path))
    expanded = exporter.expand_path("~/.config/seo-sheets/service-account.json")
    assert expanded == str(tmp_path / ".config/seo-sheets/service-account.json")
