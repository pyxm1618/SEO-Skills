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


class FakeWorksheet:
    """Records calls instead of contacting Google."""

    def __init__(self, values=None, fail_on=None):
        self.values = [list(row) for row in (values or [])]
        self.fail_on = fail_on
        self.updates = []
        self.appended = []

    def get_all_values(self):
        if self.fail_on == "get":
            raise RuntimeError("network is unavailable")
        return [list(row) for row in self.values]

    def update(self, range_name, values):
        if self.fail_on == "update":
            raise RuntimeError("permission denied")
        self.updates.append((range_name, values))

    def append_rows(self, values):
        if self.fail_on == "append":
            raise RuntimeError("quota exceeded")
        self.appended.extend(values)


def database(records):
    return {"schema_version": 1, "records": records}


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


def cell(exporter, row, header):
    return row[exporter.HEADER.index(header)]


def test_unknown_is_never_collapsed_into_blank_or_zero():
    exporter = load_module("sheet_unknown_red", EXPORTER)
    rows = exporter.build_rows(
        database([
            record(
                estimated_birth_window=None,
                demand_history_type="unknown",
                growth_rate=None,
                growth_status="from_observed_zero_baseline",
                volume=None,
                kd=None,
                root_id=None,
            )
        ])
    )

    row = rows[0]
    for header in ("Birth window", "Growth rate", "Volume", "KD", "Root id", "Demand history"):
        assert cell(exporter, row, header) == "unknown", header
    # The reason a growth rate is unknown must survive next to it.
    assert cell(exporter, row, "Growth status") == "from_observed_zero_baseline"
    assert "" not in {cell(exporter, row, h) for h in ("Birth window", "Volume")}
    assert "0" not in {cell(exporter, row, h) for h in ("Birth window", "Volume", "KD")}


def test_zero_is_preserved_and_not_turned_into_unknown():
    exporter = load_module("sheet_zero_red", EXPORTER)
    rows = exporter.build_rows(database([record(volume=0, growth_rate=0.0)]))

    assert cell(exporter, rows[0], "Volume") == "0"
    assert cell(exporter, rows[0], "Growth rate") == "0.0"


def test_google_breakout_label_is_kept_separate_from_classifier_verdict():
    exporter = load_module("sheet_breakout_red", EXPORTER)
    rows = exporter.build_rows(
        database([
            record(
                signal_type="net_new",
                status="emerging",
                google_rising_label="Breakout",
                is_google_breakout=True,
            )
        ])
    )

    row = rows[0]
    assert cell(exporter, row, "Google rising label (source)") == "Breakout"
    assert cell(exporter, row, "Google breakout flag (source)") == "true"
    # Google's own label must not leak into the classifier's columns.
    assert cell(exporter, row, "Signal type (classifier)") == "net_new"
    assert cell(exporter, row, "Status (classifier)") == "emerging"


def test_repeated_export_updates_in_place_without_duplicating_rows():
    exporter = load_module("sheet_upsert_red", EXPORTER)
    first = FakeWorksheet()
    exporter.export(first, database([record(status="watch")]))

    assert first.appended and len(first.appended) == 1
    seeded = [exporter.HEADER, first.appended[0]]

    second = FakeWorksheet(values=seeded)
    result = exporter.export(second, database([record(status="emerging")]))

    assert result["appended_count"] == 0
    assert result["updated_count"] == 1
    assert second.appended == []
    range_name, values = second.updates[0]
    assert range_name.startswith("A2:")
    assert cell(exporter, values[0], "Status (classifier)") == "emerging"


def test_new_keyword_is_appended_while_existing_one_is_updated():
    exporter = load_module("sheet_mixed_red", EXPORTER)
    existing_row = exporter.build_row(record(status="watch"))
    sheet = FakeWorksheet(values=[exporter.HEADER, existing_row])

    result = exporter.export(
        sheet,
        database([
            record(status="emerging"),
            record(keyword="micro wedding", status="watch"),
        ]),
    )

    assert result["updated_count"] == 1
    assert result["appended_count"] == 1
    assert len(sheet.appended) == 1


def test_header_is_rewritten_when_the_sheet_header_drifts():
    exporter = load_module("sheet_header_red", EXPORTER)
    sheet = FakeWorksheet(values=[["Keyword", "Something else"], ["wedding", "x"]])

    result = exporter.export(sheet, database([record()]))

    assert result["header_written"] is True
    assert sheet.updates[0][1] == [exporter.HEADER]
    # A drifted header cannot be trusted as an index, so rows are re-appended
    # rather than written over unrelated cells.
    assert result["appended_count"] == 1


def test_export_failure_is_reported_and_never_rewrites_local_outputs(tmp_path):
    exporter = load_module("sheet_failure_red", EXPORTER)
    db_path = tmp_path / "emerging-keywords.json"
    payload = database([record()])
    db_path.write_text(json.dumps(payload), encoding="utf-8")
    before = db_path.read_bytes()

    with pytest.raises(RuntimeError):
        exporter.export(FakeWorksheet(fail_on="append"), payload)

    assert db_path.read_bytes() == before


def test_cli_dry_run_needs_no_credentials(tmp_path, capsys):
    exporter = load_module("sheet_cli_red", EXPORTER)
    db_path = tmp_path / "emerging-keywords.json"
    db_path.write_text(json.dumps(database([record()])), encoding="utf-8")

    def explode(*args, **kwargs):
        raise AssertionError("dry run must not open a worksheet")

    sys.argv = ["export_to_sheet.py", "--database", str(db_path), "--dry-run"]
    assert exporter.main(worksheet_factory=explode) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["header"] == exporter.HEADER
    assert len(printed["rows"]) == 1


def test_cli_blocks_when_credentials_are_missing(tmp_path, capsys):
    exporter = load_module("sheet_cli_blocked_red", EXPORTER)
    db_path = tmp_path / "emerging-keywords.json"
    db_path.write_text(json.dumps(database([record()])), encoding="utf-8")

    sys.argv = ["export_to_sheet.py", "--database", str(db_path), "--sheet-id", "abc"]
    assert exporter.main(worksheet_factory=lambda *a, **k: FakeWorksheet()) == 2
    assert "BLOCKED" in capsys.readouterr().err


def test_record_without_keyword_is_rejected():
    exporter = load_module("sheet_keyword_red", EXPORTER)
    with pytest.raises(ValueError):
        exporter.build_rows(database([{"domain": "wedding", "keyword": "  "}]))


def test_tilde_paths_are_expanded(monkeypatch, tmp_path):
    # Credential and database paths are typed by hand as ~/... . gspread and
    # pathlib do not expand it, so an unexpanded path fails as "file not found".
    exporter = load_module("sheet_tilde_red", EXPORTER)
    monkeypatch.setenv("HOME", str(tmp_path))
    expanded = exporter.expand_path("~/.config/seo-sheets/service-account.json")

    assert "~" not in expanded
    assert expanded == str(tmp_path / ".config/seo-sheets/service-account.json")


def test_cli_reads_a_tilde_database_path(monkeypatch, tmp_path, capsys):
    exporter = load_module("sheet_tilde_cli_red", EXPORTER)
    home = tmp_path / "home"
    (home / "runs").mkdir(parents=True)
    db_path = home / "runs" / "emerging-keywords.json"
    db_path.write_text(json.dumps(database([record()])), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    sys.argv = ["export_to_sheet.py", "--database", "~/runs/emerging-keywords.json", "--dry-run"]
    assert exporter.main(worksheet_factory=lambda *a, **k: FakeWorksheet()) == 0
    assert len(json.loads(capsys.readouterr().out)["rows"]) == 1
