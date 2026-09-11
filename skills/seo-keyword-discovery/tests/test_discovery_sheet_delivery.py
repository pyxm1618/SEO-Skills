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


def handoff(batch_id="batch-1", keywords=None, **overrides):
    payload = {
        "batch_id": batch_id,
        "market": "US",
        "language": "en",
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
            },
        ],
    }
    payload.update(overrides)
    return payload


def duplicate_keyword_handoff():
    return handoff(
        keywords=[
            {
                "candidate_id": "c1",
                "keyword": "AI Logo Generator",
                "source": "google_autocomplete",
                "source_seed": "ai logo",
                "evidence_receipt_ref": "evidence/autocomplete.json",
            },
            {
                "candidate_id": "c2",
                "keyword": " ai   logo generator ",
                "source": "semrush_ideas",
                "source_seed": "logo generator",
                "evidence_receipt_ref": "evidence/semrush.json",
            },
        ]
    )


def col_index(letters):
    value = 0
    for char in letters:
        value = value * 26 + (ord(char) - ord("A") + 1)
    return value - 1


class FakeWorksheet:
    def __init__(self, values=None, drop_last_append=False):
        self.values = [list(row) for row in (values or [])]
        self.drop_last_append = drop_last_append
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
        rows = [list(map(str, row)) for row in values]
        if self.drop_last_append and rows:
            rows = rows[:-1]
        self.values.extend(rows)

    def hide_columns(self, start, end):
        self.hidden.append((start, end))


def header_map(sheet):
    return {name: index for index, name in enumerate(sheet.values[0])}


def test_default_worksheet_is_unified_keyword_library():
    exporter = load_exporter("sheet_default_v2")
    assert exporter.DEFAULT_WORKSHEET == "关键词库"
    assert exporter.DELIVERY_SCHEMA == "seo-discovery-sheet-delivery/v2"


def test_identity_context_must_be_explicit_and_is_not_guessed():
    exporter = load_exporter("sheet_identity_context_v2")
    payload = handoff()
    payload.pop("market")
    payload.pop("language")
    with pytest.raises(ValueError, match="market"):
        exporter.export(FakeWorksheet(), payload)


def test_multiple_discovery_candidates_can_resolve_to_one_stable_row_without_losing_provenance():
    exporter = load_exporter("sheet_many_candidates_one_row_v2")
    sheet = FakeWorksheet()
    payload = duplicate_keyword_handoff()

    result = exporter.export(sheet, payload)

    assert result["candidate_count"] == 2
    assert result["verified_candidate_count"] == 2
    assert result["stable_row_count"] == 1
    assert result["verified_stable_row_count"] == 1
    assert len(sheet.values) == 2
    assert len(result["candidate_bindings"]) == 2
    assert {item["candidate_id"] for item in result["candidate_bindings"]} == {"c1", "c2"}
    assert len({item["stable_key"] for item in result["candidate_bindings"]}) == 1

    mapping = header_map(sheet)
    provenance = json.loads(sheet.values[1][mapping["discovery_provenance"]])
    assert {item["candidate_id"] for item in provenance} == {"c1", "c2"}
    assert {item["evidence_receipt_ref"] for item in provenance} == {
        "evidence/autocomplete.json",
        "evidence/semrush.json",
    }


def test_discovery_rerun_reuses_stable_rows_instead_of_appending_batch_rows():
    exporter = load_exporter("sheet_rerun_v2")
    sheet = FakeWorksheet()
    exporter.export(sheet, handoff("batch-1"))
    exporter.export(sheet, handoff("batch-2"))
    assert len(sheet.values) == 3
    mapping = header_map(sheet)
    assert {row[mapping["stable_keyword_key"]] for row in sheet.values[1:]} == {
        "perfume finder by notes | US | en",
        "perfume finder quiz | US | en",
    }


def test_missing_stable_row_is_blocked_by_readback_verification():
    exporter = load_exporter("sheet_missing_row_v2")
    sheet = FakeWorksheet()
    payload = handoff()
    result = exporter.export(sheet, payload)
    sheet.values.pop()
    with pytest.raises(RuntimeError, match="missing stable row|verification"):
        exporter.verify_delivery(sheet, payload, result["candidate_bindings"])


def test_duplicate_stable_row_is_blocked_by_readback_verification():
    exporter = load_exporter("sheet_duplicate_row_v2")
    sheet = FakeWorksheet()
    payload = handoff()
    result = exporter.export(sheet, payload)
    sheet.values.append(list(sheet.values[1]))
    with pytest.raises(RuntimeError, match="duplicate stable"):
        exporter.verify_delivery(sheet, payload, result["candidate_bindings"])


def test_missing_candidate_provenance_is_blocked_even_when_stable_row_exists():
    exporter = load_exporter("sheet_missing_candidate_provenance_v2")
    sheet = FakeWorksheet()
    payload = duplicate_keyword_handoff()
    result = exporter.export(sheet, payload)
    mapping = header_map(sheet)
    provenance = json.loads(sheet.values[1][mapping["discovery_provenance"]])
    sheet.values[1][mapping["discovery_provenance"]] = json.dumps([provenance[0]])
    with pytest.raises(RuntimeError, match="candidate|provenance"):
        exporter.verify_delivery(sheet, payload, result["candidate_bindings"])


def test_other_skill_owned_fields_do_not_cause_discovery_receipt_mismatch():
    exporter = load_exporter("sheet_other_owner_fields_v2")
    sheet = FakeWorksheet()
    payload = handoff()
    result = exporter.export(sheet, payload)
    mapping = header_map(sheet)
    sheet.values[1][mapping["CPC"]] = "9.99"
    sheet.values[1][mapping["出生窗口"]] = "2026-08"
    assert exporter.verify_delivery(sheet, payload, result["candidate_bindings"])["verified_candidate_count"] == 2


def test_handoff_must_still_be_formal_pass():
    exporter = load_exporter("sheet_handoff_gate_v2")
    bad = handoff(coverage_status="BLOCKED")
    with pytest.raises(ValueError):
        exporter.export(FakeWorksheet(), bad)


def test_handoff_binding_ignores_only_delivery_ref_and_changes_with_keywords():
    exporter = load_exporter("sheet_binding_v2")
    original = handoff()
    digest = exporter.handoff_binding_sha256(original)
    decorated = dict(original, sheet_delivery_receipt_ref="evidence/sheet.receipt.json")
    assert exporter.handoff_binding_sha256(decorated) == digest
    changed = handoff(keywords=[dict(original["keywords"][0], keyword="changed keyword"), original["keywords"][1]])
    assert exporter.handoff_binding_sha256(changed) != digest


def test_successful_cli_writes_v2_receipt_with_candidate_and_stable_counts(tmp_path, capsys, monkeypatch):
    exporter = load_exporter("sheet_receipt_v2")
    payload = duplicate_keyword_handoff()
    path = tmp_path / "handoff.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
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
    assert receipt["schema"] == "seo-discovery-sheet-delivery/v2"
    assert receipt["worksheet"] == "关键词库"
    assert receipt["sheet_id"] == "sheet-123"
    assert receipt["candidate_count"] == 2
    assert receipt["verified_candidate_count"] == 2
    assert receipt["stable_row_count"] == 1
    assert receipt["verified_stable_row_count"] == 1
    assert len(receipt["candidate_bindings"]) == 2
    assert receipt["handoff_binding_sha256"] == exporter.handoff_binding_sha256(decorated)
    assert receipt["exporter_source_sha256"] == exporter.file_sha256(EXPORTER)


def test_cli_dry_run_resolves_stable_bindings_without_google_credentials(tmp_path, capsys, monkeypatch):
    exporter = load_exporter("sheet_dry_run_v2")
    path = tmp_path / "handoff.json"
    path.write_text(json.dumps(duplicate_keyword_handoff()), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["export_to_sheet.py", "--handoff", str(path), "--dry-run"])
    assert exporter.main(worksheet_factory=lambda *a, **k: (_ for _ in ()).throw(AssertionError())) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["worksheet"] == "关键词库"
    assert payload["candidate_count"] == 2
    assert payload["stable_row_count"] == 1
    assert "sheet_delivery_receipt_ref" not in json.loads(path.read_text(encoding="utf-8"))


def test_cli_explicit_delivery_context_can_supply_missing_handoff_identity(tmp_path, capsys, monkeypatch):
    exporter = load_exporter("sheet_explicit_context_v2")
    payload = handoff()
    payload.pop("market")
    payload.pop("language")
    path = tmp_path / "handoff.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["export_to_sheet.py", "--handoff", str(path), "--market", "US", "--language", "en", "--dry-run"],
    )
    assert exporter.main(worksheet_factory=lambda *a, **k: (_ for _ in ()).throw(AssertionError())) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["stable_row_count"] == 2


def test_cli_requires_sheet_and_credentials_without_dry_run(tmp_path, capsys, monkeypatch):
    exporter = load_exporter("sheet_credentials_v2")
    path = tmp_path / "handoff.json"
    path.write_text(json.dumps(handoff()), encoding="utf-8")
    monkeypatch.delenv("SEO_KEYWORD_SHEET_ID", raising=False)
    monkeypatch.delenv("SEO_SHEETS_CREDENTIALS", raising=False)
    monkeypatch.setattr(sys, "argv", ["export_to_sheet.py", "--handoff", str(path)])
    assert exporter.main(worksheet_factory=lambda *a, **k: FakeWorksheet()) == 2
    assert "BLOCKED" in capsys.readouterr().err
