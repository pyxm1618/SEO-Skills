import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "runtime" / "start_live_browser.py"
DB_SCRIPT = ROOT / "skills" / "emerging-keyword-monitor" / "scripts" / "update_emerging_database.py"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- dedicated Google browser -------------------------------------------------


def test_google_browser_uses_its_own_port_and_profile():
    """The Google collector must not share the relay browser's profile.

    Sharing one profile means one Chrome process and one user-data-dir, so the
    collector cannot get a persistent context of its own and falls back to a
    fresh cookieless one per run.
    """
    launcher = load(LAUNCHER, "launcher_google")
    assert launcher.GOOGLE_PROFILE != launcher.DEFAULT_PROFILE
    assert launcher.DEFAULT_GOOGLE_PORT != launcher.DEFAULT_PORT


def test_google_browser_exports_the_dedicated_variable():
    out = subprocess.run(
        [sys.executable, str(LAUNCHER), "--google", "--help"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert out.returncode == 0
    assert "--google" in out.stdout


def test_google_browser_opens_on_ncr_not_the_relay_login():
    """A ccTLD redirect on first load would poison the profile's preference."""
    launcher = load(LAUNCHER, "launcher_ncr")
    assert launcher.GOOGLE_START_URL == "https://www.google.com/ncr"
    command = launcher.chrome_command(9224, "/tmp/p", "/bin/true", launcher.GOOGLE_START_URL)
    assert command[-1] == "https://www.google.com/ncr"
    assert launcher.chrome_command(9223, "/tmp/p", "/bin/true")[-1] == launcher.LOGIN_URL


def test_launcher_still_refuses_to_reuse_an_unknown_process():
    """The dedicated profile must not weaken the existing port-hijack guard."""
    source = LAUNCHER.read_text(encoding="utf-8")
    assert "refusing to reuse or replace it" in source
    assert "refusing to kill an unknown process" in source


# --- emerging record lifecycle ------------------------------------------------


def test_confirmed_signal_graduates():
    module = load(DB_SCRIPT, "db_graduate")
    assert module.observation_state("emerging") == "graduated"
    assert module.observation_state("breakout") == "graduated"


def test_decayed_and_settled_signals_retire():
    module = load(DB_SCRIPT, "db_retire")
    assert module.observation_state("noise") == "retired"
    assert module.observation_state("mature") == "retired"


def test_forming_signals_stay_under_observation():
    module = load(DB_SCRIPT, "db_watch")
    for status in ("new_signal", "watch", "insufficient_evidence"):
        assert module.observation_state(status) == "watching"


def test_unknown_status_is_not_treated_as_a_verdict():
    """An unrecognised status must not silently retire a record."""
    module = load(DB_SCRIPT, "db_unknown")
    assert module.observation_state("strong candidate") == "watching"
    assert module.observation_state(None) == "watching"


def test_merge_records_lifecycle_and_observation_count():
    module = load(DB_SCRIPT, "db_merge")
    first = module.merge_database(
        None,
        [{"domain": "tarot", "keyword": "kw a", "status": "new_signal"}],
        [],
        "2026-07-01T00:00:00Z",
    )
    assert first["records"][0]["observation_state"] == "watching"
    assert first["records"][0]["observation_count"] == 1

    second = module.merge_database(
        first,
        [{"domain": "tarot", "keyword": "kw a", "status": "breakout"}],
        [],
        "2026-08-01T00:00:00Z",
    )
    record = second["records"][0]
    assert record["observation_state"] == "graduated"
    assert record["observation_count"] == 2
    assert record["previous_status"] == "new_signal"


def test_carry_forward_excludes_graduated_and_retired():
    module = load(DB_SCRIPT, "db_carry")
    database = module.merge_database(
        None,
        [
            {"domain": "d", "keyword": "still watching", "status": "watch"},
            {"domain": "d", "keyword": "already sent", "status": "breakout"},
            {"domain": "d", "keyword": "decayed", "status": "noise"},
        ],
        [],
        "2026-07-01T00:00:00Z",
    )
    rows = module.carry_forward(database)
    assert [row["keyword"] for row in rows] == ["still watching"]
    assert rows[0]["previous_status"] == "watch"

    assert len(module.carry_forward(database, include_graduated=True)) == 2
    assert len(module.carry_forward(database, include_retired=True)) == 2


def test_carry_forward_cli_writes_the_next_batch(tmp_path):
    module = load(DB_SCRIPT, "db_cli")
    database = module.merge_database(
        None, [{"domain": "d", "keyword": "kw", "status": "watch"}], [], "2026-07-01T00:00:00Z"
    )
    db_path = tmp_path / "db.json"
    db_path.write_text(json.dumps(database), encoding="utf-8")
    out_path = tmp_path / "next.json"
    result = subprocess.run(
        [sys.executable, str(DB_SCRIPT), "--database", str(db_path), "--carry-forward", str(out_path)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 0, result.stderr
    rows = json.loads(out_path.read_text(encoding="utf-8"))
    assert [row["keyword"] for row in rows] == ["kw"]


def test_merge_still_requires_its_inputs(tmp_path):
    """Making --input/--routes optional for carry-forward must not weaken merge."""
    result = subprocess.run(
        [sys.executable, str(DB_SCRIPT), "--database", str(tmp_path / "db.json")],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "required when merging" in result.stderr


def test_lifecycle_script_is_not_part_of_the_attested_pipeline():
    """Hashing this script would tie replay to mutable cross-run state."""
    for path in (ROOT / "runtime" / "emerging_pipeline.py", ROOT / "runtime" / "stage_hook.py"):
        assert "update_emerging_database" not in path.read_text(encoding="utf-8")
