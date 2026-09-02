import importlib.util
import json
import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parents[1]
EXPORTER = SKILL_ROOT / "scripts" / "export_to_sheet.py"


def load_exporter(name="discovery_sheet_exporter"):
    spec = importlib.util.spec_from_file_location(name, EXPORTER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def handoff(batch_id="batch-1", keywords=None):
    return {
        "batch_id": batch_id,
        "status": "PASS",
        "coverage_status": "PASS",
        "coverage_receipt_ref": "evidence/coverage.receipt.json",
        "keywords": keywords
        or [
            {
                "candidate_id": "c1",
                "keyword": "perfume finder by notes",
                "source": "google_serp_expansions",
                "source_seed": "perfume finder",
                "evidence_receipt_ref": "evidence/expansions.receipt.json",
            },
            {
                "candidate_id": "c2",
                "keyword": "perfume finder quiz",
                "source": "google_autocomplete",
                "source_seed": "perfume finder",
                "evidence_receipt_ref": "evidence/autocomplete.receipt.json",
                "volume": 90,
                "kd": 18,
            },
        ],
    }


class FakeWorksheet:
    def __init__(self, values=None, drop_last_append=False):
        self.values = [list(row) for row in (values or [])]
        self.drop_last_append = drop_last_append

    def get_all_values(self):
        return [list(row) for row in self.values]

    def update(self, range_name, values):
        row_number = int(range_name.split(":", 1)[0][1:])
        while len(self.values) < row_number:
            self.values.append([])
        self.values[row_number - 1] = list(values[0])

    def append_rows(self, values):
        rows = [list(row) for row in values]
        if self.drop_last_append and rows:
            rows = rows[:-1]
        self.values.extend(rows)


def test_default_worksheet_is_keyword_discovery():
    exporter = load_exporter("sheet_default")
    assert exporter.DEFAULT_WORKSHEET == "keyword_discovery"


def test_rows_preserve_provenance_and_unknown_metrics():
    exporter = load_exporter("sheet_rows")
    rows = exporter.build_rows(handoff())
    assert len(rows) == 2
    first = rows[0]
    assert first[exporter.HEADER.index("Batch ID")] == "batch-1"
    assert first[exporter.HEADER.index("Candidate ID")] == "c1"
    assert first[exporter.HEADER.index("Keyword")] == "perfume finder by notes"
    assert first[exporter.HEADER.index("Source")] == "google_serp_expansions"
    assert first[exporter.HEADER.index("Source Seed")] == "perfume finder"
    assert first[exporter.HEADER.index("Volume")] == "unknown"
    assert first[exporter.HEADER.index("KD")] == "unknown"


def test_export_writes_then_reads_back_exact_batch():
    exporter = load_exporter("sheet_round_trip")
    sheet = FakeWorksheet()
    result = exporter.export(sheet, handoff())
    assert result["status"] == "PASS"
    assert result["record_count"] == 2
    assert result["verified_count"] == 2
    assert sheet.values[0] == exporter.HEADER


def test_second_export_updates_same_batch_candidate_without_duplicate():
    exporter = load_exporter("sheet_upsert")
    sheet = FakeWorksheet()
    exporter.export(sheet, handoff())
    changed = handoff(
        keywords=[
            dict(handoff()["keywords"][0], keyword="perfume finder by scent notes"),
            handoff()["keywords"][1],
        ]
    )
    exporter.export(sheet, changed)
    current = [row for row in sheet.values[1:] if row and row[0] == "batch-1"]
    assert len(current) == 2
    assert any("scent notes" in row[2] for row in current)


def test_different_batches_are_preserved():
    exporter = load_exporter("sheet_batches")
    sheet = FakeWorksheet()
    exporter.export(sheet, handoff("batch-1"))
    exporter.export(sheet, handoff("batch-2"))
    assert {row[0] for row in sheet.values[1:] if row} == {"batch-1", "batch-2"}
    assert len(sheet.values[1:]) == 4


def test_partial_google_write_is_blocked_by_readback_verification():
    exporter = load_exporter("sheet_partial")
    sheet = FakeWorksheet(drop_last_append=True)
    with pytest.raises(RuntimeError, match="verification"):
        exporter.export(sheet, handoff())


def test_extra_row_for_current_batch_is_blocked():
    exporter = load_exporter("sheet_extra")
    sheet = FakeWorksheet()
    exporter.export(sheet, handoff())
    sheet.values.append([
        "batch-1",
        "unexpected",
        "invented keyword",
        "unknown",
        "unknown",
        "unknown",
        "unknown",
        "unknown",
    ])
    with pytest.raises(RuntimeError, match="verification"):
        exporter.verify_batch(sheet, handoff())


def test_handoff_must_be_formal_pass():
    exporter = load_exporter("sheet_handoff_gate")
    bad = handoff()
    bad["coverage_status"] = "BLOCKED"
    with pytest.raises(ValueError):
        exporter.build_rows(bad)


def test_handoff_binding_ignores_only_delivery_ref_and_changes_with_keywords():
    exporter = load_exporter("sheet_binding")
    original = handoff()
    digest = exporter.handoff_binding_sha256(original)
    decorated = dict(original, sheet_delivery_receipt_ref="evidence/sheet.receipt.json")
    assert exporter.handoff_binding_sha256(decorated) == digest
    changed = handoff(keywords=[dict(original["keywords"][0], keyword="changed keyword"), original["keywords"][1]])
    assert exporter.handoff_binding_sha256(changed) != digest


def test_successful_cli_writes_bound_receipt_and_decorates_handoff(tmp_path, capsys, monkeypatch):
    exporter = load_exporter("sheet_receipt")
    path = tmp_path / "handoff.json"
    path.write_text(json.dumps(handoff()), encoding="utf-8")
    sheet = FakeWorksheet()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "export_to_sheet.py",
            "--handoff",
            str(path),
            "--sheet-id",
            "sheet-123",
            "--credentials",
            "credentials.json",
        ],
    )

    assert exporter.main(worksheet_factory=lambda *a, **k: sheet) == 0

    output = json.loads(capsys.readouterr().out)
    decorated = json.loads(path.read_text(encoding="utf-8"))
    receipt_path = Path(decorated["sheet_delivery_receipt_ref"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert output["sheet_delivery_receipt_ref"] == str(receipt_path)
    assert receipt["schema"] == "seo-discovery-sheet-delivery/v1"
    assert receipt["status"] == "PASS"
    assert receipt["batch_id"] == "batch-1"
    assert receipt["worksheet"] == "keyword_discovery"
    assert receipt["sheet_id"] == "sheet-123"
    assert receipt["record_count"] == 2
    assert receipt["verified_count"] == 2
    assert receipt["handoff_binding_sha256"] == exporter.handoff_binding_sha256(decorated)
    assert receipt["exporter_source_sha256"] == exporter.file_sha256(EXPORTER)


def test_cli_dry_run_needs_no_google_credentials(tmp_path, capsys, monkeypatch):
    exporter = load_exporter("sheet_dry_run")
    path = tmp_path / "handoff.json"
    path.write_text(json.dumps(handoff()), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["export_to_sheet.py", "--handoff", str(path), "--dry-run"])
    assert exporter.main(worksheet_factory=lambda *a, **k: (_ for _ in ()).throw(AssertionError())) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["worksheet"] == "keyword_discovery"
    assert len(payload["rows"]) == 2
    assert "sheet_delivery_receipt_ref" not in json.loads(path.read_text(encoding="utf-8"))


def test_cli_requires_sheet_and_credentials_without_dry_run(tmp_path, capsys, monkeypatch):
    exporter = load_exporter("sheet_credentials")
    path = tmp_path / "handoff.json"
    path.write_text(json.dumps(handoff()), encoding="utf-8")
    monkeypatch.delenv("SEO_KEYWORD_SHEET_ID", raising=False)
    monkeypatch.delenv("SEO_SHEETS_CREDENTIALS", raising=False)
    monkeypatch.setattr(sys, "argv", ["export_to_sheet.py", "--handoff", str(path)])
    assert exporter.main(worksheet_factory=lambda *a, **k: FakeWorksheet()) == 2
    assert "BLOCKED" in capsys.readouterr().err
