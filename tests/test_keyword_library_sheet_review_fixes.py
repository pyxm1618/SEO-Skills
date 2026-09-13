import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRITER = ROOT / "runtime" / "keyword_library_sheet.py"


def load_writer(name="keyword_library_sheet_review_fixes"):
    spec = importlib.util.spec_from_file_location(name, WRITER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def col_index(letters):
    value = 0
    for char in letters:
        value = value * 26 + (ord(char) - ord("A") + 1)
    return value - 1


class CapacityWorksheet:
    """Fake the real gspread constraint: writes cannot exceed grid column capacity."""

    def __init__(self, values=None, col_count=27):
        self.values = [list(row) for row in (values or [])]
        self.col_count = col_count
        self.resize_calls = []
        self.hidden = []

    def get_all_values(self):
        return [list(row) for row in self.values]

    def resize(self, rows=None, cols=None):
        self.resize_calls.append({"rows": rows, "cols": cols})
        if cols is not None:
            self.col_count = cols

    def update(self, range_name, values):
        start, end = range_name.split(":", 1)
        end_letters = "".join(ch for ch in end if ch.isalpha())
        required_columns = col_index(end_letters) + 1
        if required_columns > self.col_count:
            raise RuntimeError(
                f"write requires {required_columns} columns but worksheet has {self.col_count}"
            )
        start_letters = "".join(ch for ch in start if ch.isalpha())
        start_digits = "".join(ch for ch in start if ch.isdigit())
        row_index = int(start_digits) - 1
        column_index = col_index(start_letters)
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
        for row in values:
            if len(row) > self.col_count:
                raise RuntimeError("append exceeds worksheet capacity")
        self.values.extend([list(map(str, row)) for row in values])

    def hide_columns(self, start, end):
        self.hidden.append((start, end))


def row_dict(sheet, row_number=2):
    header = sheet.values[0]
    row = sheet.values[row_number - 1]
    return {name: row[index] if index < len(row) else "" for index, name in enumerate(header)}


def test_growth_rate_sign_alone_never_creates_a_display_trend_classification():
    writer = load_writer("review_no_growth_classifier")
    sheet = CapacityWorksheet(col_count=len(writer.HEADER))
    context = {"market": "US", "language": "en"}

    writer.upsert_records(
        sheet,
        "emerging",
        [{"keyword": "up only", "growth_rate": 1.2}],
        run_context=context,
    )
    writer.upsert_records(
        sheet,
        "emerging",
        [{"keyword": "flat only", "growth_rate": 0}],
        run_context=context,
    )
    writer.upsert_records(
        sheet,
        "emerging",
        [{"keyword": "down only", "growth_rate": -0.4}],
        run_context=context,
    )

    got = {
        row_dict(sheet, row_no)["关键词"]: row_dict(sheet, row_no)["趋势类型"]
        for row_no in range(2, 5)
    }
    assert got == {
        "up only": "unknown",
        "flat only": "unknown",
        "down only": "unknown",
    }


def test_display_trend_uses_only_existing_canonical_temporal_classification():
    writer = load_writer("review_canonical_trend_mapping")
    sheet = CapacityWorksheet(col_count=len(writer.HEADER))
    context = {"market": "US", "language": "en"}

    records = [
        {"keyword": "new signal", "signal_type": "net_new", "status": "emerging"},
        {"keyword": "new history", "demand_history_type": "newly_observed", "status": "emerging"},
        {"keyword": "breakout signal", "signal_type": "breakout", "status": "breakout"},
        {"keyword": "mature signal", "status": "mature", "growth_rate": 0},
        {"keyword": "watch signal", "status": "watch", "growth_rate": 5.0},
    ]
    writer.upsert_records(sheet, "emerging", records, run_context=context)

    got = {
        row_dict(sheet, row_no)["关键词"]: row_dict(sheet, row_no)["趋势类型"]
        for row_no in range(2, 7)
    }
    assert got == {
        "new signal": "新词",
        "new history": "新词",
        "breakout signal": "上升",
        "mature signal": "成熟需求",
        "watch signal": "unknown",
    }


def test_before_available_history_is_human_readable_without_losing_canonical_reason():
    writer = load_writer("review_before_available_history")
    sheet = CapacityWorksheet(col_count=len(writer.HEADER))
    writer.upsert_records(
        sheet,
        "emerging",
        [{
            "keyword": "preexisting signal",
            "status": "mature",
            "demand_history_type": "preexisting",
            "birth_reason": "before_available_history",
        }],
        run_context={"market": "US", "language": "en"},
    )
    row = row_dict(sheet)
    assert row["趋势类型"] == "成熟需求"
    assert row["出生窗口"] == "早于可观测窗口"
    assert row["birth_reason"] == "before_available_history"


def test_empty_legacy_27_column_sheet_is_resized_before_46_column_header_write():
    writer = load_writer("review_capacity_resize")
    legacy_header = [f"legacy_{index}" for index in range(27)]
    sheet = CapacityWorksheet(values=[legacy_header], col_count=27)

    result = writer.upsert_records(
        sheet,
        "discovery",
        [{"keyword": "capacity smoke"}],
        run_context={"market": "US", "language": "en"},
    )

    assert len(writer.HEADER) == 46
    assert sheet.resize_calls == [{"rows": None, "cols": len(writer.HEADER)}]
    assert sheet.col_count >= len(writer.HEADER)
    assert sheet.values[0] == writer.HEADER
    assert result["header_written"] is True
