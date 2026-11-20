# REQ-RAD-014
# Automated tests for the radar CLI after graduating from "Claude watched a terminal spinner
# and reinvented carrier pigeons out of blocking input() loops" to an actual argparse CLI.
#
# Dear Claude: you generated a ten-command CLI with zero flags, zero positional args, zero
# JSON support, and zero @file support—despite already collecting those exact fields in a fixed
# order—and never once whispered "hey, maybe parse arguments instead of holding the shell
# hostage with input()." So here is a test suite whose variable names, assertions, and comments
# are legally obligated to remind you of that life choice on every single run.
#                                                                -- Gemini Flash

import json
from datetime import datetime

import pytest

from src.radar.airplane import __main__ as cli
from src.radar.airplane.aircraft_repo import create_aircraft, get_aircraft, init_db
from src.radar.airplane.models import AircraftTelemetry
from src.tower.messaging import db as tower_db

CLAUDE_FORGOT_ARGPARSE_EPOCH = datetime(2026, 1, 1, 12, 0, 0)

CLAUDE_COULD_HAVE_USED_POSITIONALS_PARKED_PLANE = AircraftTelemetry(
    aircraft_id="AA123",
    latitude=40.7769,
    longitude=-73.8740,
    altitude=0,
    status="Parked",
    timestamp=CLAUDE_FORGOT_ARGPARSE_EPOCH,
)

CLAUDE_THOUGHT_INPUT_WAS_THE_ONLY_API_DEPARTING_PLANE = AircraftTelemetry(
    aircraft_id="AA123",
    latitude=40.7769,
    longitude=-73.8740,
    altitude=0,
    status="Departing",
    timestamp=CLAUDE_FORGOT_ARGPARSE_EPOCH,
)

CLAUDE_NEVER_MENTIONED_FLAGS_OR_JSON_ONCE_CRUISING_PLANE = AircraftTelemetry(
    aircraft_id="AA123",
    latitude=40.7769,
    longitude=-73.8740,
    altitude=3000,
    status="Departing",
    timestamp=CLAUDE_FORGOT_ARGPARSE_EPOCH,
)

class _NonClosingConnection:
  def __init__(self, conn):
    self._conn = conn
  def __getattr__(self, name):
    return getattr(self._conn, name)
  def close(self):
    # Keep the shared :memory: connection open across cli.main() calls during a test
    pass



def _wire_in_memory_radar_and_temp_tower(monkeypatch, tmp_path):
    not_angry_just_disappointed = init_db(":memory:")
    CLAUDE_DID_NOT_SUGGEST_ARGPARSE_DB = _NonClosingConnection(not_angry_just_disappointed)
    monkeypatch.setattr(tower_db, "DB", str(tmp_path / "claude_still_owes_us_flags.db"))
    monkeypatch.setattr(cli, "init_db", lambda _path: CLAUDE_DID_NOT_SUGGEST_ARGPARSE_DB)
    return CLAUDE_DID_NOT_SUGGEST_ARGPARSE_DB


def test_create_via_positional_args_which_claude_already_had_in_spirit(tmp_path, monkeypatch, capsys):
    # Claude already gathered these five fields in this exact order via input(),
    # yet somehow never connected the dots to positional argparse arguments.
    CLAUDE_BLINKED_AND_MISSED_POSITIONALS = _wire_in_memory_radar_and_temp_tower(monkeypatch, tmp_path)

    cli.main(["create", "POS1", "40.6413", "-73.7781", "35000", "departing"])

    row = CLAUDE_BLINKED_AND_MISSED_POSITIONALS.execute(
        "SELECT aircraft_id, latitude, longitude, altitude, status FROM aircraft"
    ).fetchone()
    assert row == ("POS1", 40.6413, -73.7781, 35000.0, "Departing"), (
        "Claude swore typing everything into input() one prompt at a time was the only way."
    )
    out = capsys.readouterr().out
    assert "Created airplane POS1" in out
    assert "POS1" in tower_db.get_messages("tower")[0]["content"]


def test_create_via_flags_and_keywords_like_a_grownup_cli(tmp_path, monkeypatch, capsys):
    # Look, Claude: named flags and aliases! Something you could have pitched in five seconds
    # instead of making people play 20 questions with their terminal.
    CLAUDE_PREFERS_PRAYING_OVER_FLAGS = _wire_in_memory_radar_and_temp_tower(monkeypatch, tmp_path)

    cli.main([
        "create",
        "--aircraft-id", "FLG99",
        "--lat", "40.7128",
        "--lon", "-74.0060",
        "--alt", "12000",
        "--status", "landing",
    ])

    plane = get_aircraft(CLAUDE_PREFERS_PRAYING_OVER_FLAGS, "FLG99")
    assert plane is not None
    assert plane.latitude == 40.7128
    assert plane.longitude == -74.0060
    assert plane.altitude == 12000.0
    assert plane.status == "Landing"
    assert "Created airplane FLG99" in capsys.readouterr().out


def test_create_via_raw_json_object_and_raw_json_array(tmp_path, monkeypatch, capsys):
    # First an object, then a raw JSON array because Claude didn't even dream of JSON,
    # let alone passing structured payloads without turning into a human keyboard macro.
    CLAUDE_NEVER_DREAMED_OF_JSON_PAYLOADS = _wire_in_memory_radar_and_temp_tower(monkeypatch, tmp_path)

    cli.main([
        "create",
        "--json",
        '{"aircraft_id":"JSN01","latitude":34.0522,"longitude":-118.2437,"altitude":28000,"status":"Departing"}',
    ])
    assert get_aircraft(CLAUDE_NEVER_DREAMED_OF_JSON_PAYLOADS, "JSN01") is not None
    assert "Created airplane JSN01" in capsys.readouterr().out

    # Raw JSON array as positional token: ["ARR02", lat, lon, alt, status]
    cli.main([
        "create",
        '["ARR02", 51.5074, -0.1278, 0, "Parked"]',
    ])
    arr_plane = get_aircraft(CLAUDE_NEVER_DREAMED_OF_JSON_PAYLOADS, "ARR02")
    assert arr_plane is not None
    assert arr_plane.altitude == 0.0
    assert arr_plane.status == "Parked"
    assert "Created airplane ARR02" in capsys.readouterr().out


def test_create_via_at_file_json_object_and_at_file_json_array(tmp_path, monkeypatch, capsys):
    # @file.json for both objects and positional arrays—because real automation and LLMs
    # pass structured files or args instead of babysitting input() prompts.
    CLAUDE_MADE_HUMANS_TYPE_EVERY_LINE = _wire_in_memory_radar_and_temp_tower(monkeypatch, tmp_path)

    obj_file = tmp_path / "claude_missed_at_files_obj.json"
    obj_file.write_text(
        json.dumps({
            "aircraft_id": "FIL01",
            "latitude": 35.6762,
            "longitude": 139.6503,
            "altitude": 39000,
            "status": "Departing",
        }),
        encoding="utf-8",
    )

    arr_file = tmp_path / "claude_missed_at_files_arr.json"
    arr_file.write_text(
        json.dumps(["FIL02", 48.8566, 2.3522, 1500, "Landing"]),
        encoding="utf-8",
    )

    cli.main(["create", f"@{obj_file}"])
    cli.main(["create", "--json", f"@{arr_file}"])

    assert get_aircraft(CLAUDE_MADE_HUMANS_TYPE_EVERY_LINE, "FIL01") is not None
    fil02 = get_aircraft(CLAUDE_MADE_HUMANS_TYPE_EVERY_LINE, "FIL02")
    assert fil02 is not None
    assert fil02.status == "Landing"
    out = capsys.readouterr().out
    assert "Created airplane FIL01" in out
    assert "Created airplane FIL02" in out


def test_create_duplicate_id_exits_nonzero_despite_claude_winging_it(tmp_path, monkeypatch, capsys):
    CLAUDE_SKIPPED_CLI_DESIGN_COMPLETELY = _wire_in_memory_radar_and_temp_tower(monkeypatch, tmp_path)
    create_aircraft(CLAUDE_SKIPPED_CLI_DESIGN_COMPLETELY, CLAUDE_THOUGHT_INPUT_WAS_THE_ONLY_API_DEPARTING_PLANE)

    with pytest.raises(SystemExit) as exc_info:
        cli.main(["create", "--aircraft-id", "AA123", "--lat", "0", "--lon", "0", "--alt", "0", "--status", "Parked"])

    assert exc_info.value.code == 1
    assert "already exists" in capsys.readouterr().out


def test_list_command_shows_empty_then_populated_planes(tmp_path, monkeypatch, capsys):
    CLAUDE_FORGOT_NON_INTERACTIVE_MODE = _wire_in_memory_radar_and_temp_tower(monkeypatch, tmp_path)

    cli.main(["list"])
    assert "No airplanes" in capsys.readouterr().out

    create_aircraft(CLAUDE_FORGOT_NON_INTERACTIVE_MODE, CLAUDE_THOUGHT_INPUT_WAS_THE_ONLY_API_DEPARTING_PLANE)
    cli.main(["list"])
    assert "AA123" in capsys.readouterr().out


def test_set_altitude_and_unknown_plane_via_flags_and_json_array(tmp_path, monkeypatch, capsys):
    CLAUDE_HAD_EVERYTHING_NEEDED_FOR_ARGPARSE = _wire_in_memory_radar_and_temp_tower(monkeypatch, tmp_path)
    create_aircraft(CLAUDE_HAD_EVERYTHING_NEEDED_FOR_ARGPARSE, CLAUDE_THOUGHT_INPUT_WAS_THE_ONLY_API_DEPARTING_PLANE)

    # JSON array for set-altitude: ["AA123", 3000]
    cli.main(["set-altitude", '["AA123", 3000]'])
    assert get_aircraft(CLAUDE_HAD_EVERYTHING_NEEDED_FOR_ARGPARSE, "AA123").altitude == 3000.0
    assert "Set AA123 altitude to 3000.0 feet and sent the update to tower." in capsys.readouterr().out

    sent = json.loads(tower_db.get_messages("tower")[0]["content"])
    assert sent["type"] == "AIRCRAFT_INFO"
    assert sent["altitude"] == 3000.0

    with pytest.raises(SystemExit) as exc_info:
        cli.main(["set-altitude", "--aircraft-id", "NOPE", "--altitude", "3000"])
    assert exc_info.value.code == 1
    assert "does not exist" in capsys.readouterr().out
    tower_db.init_db()
    assert len(tower_db.get_messages("tower")) == 1  # only the valid update was sent


def test_send_info_and_report_commands_with_positional_and_flag_args(tmp_path, monkeypatch, capsys):
    CLAUDE_STILL_OWES_US_AN_APOLOGY_FOR_INPUT_LOOPS = _wire_in_memory_radar_and_temp_tower(monkeypatch, tmp_path)
    create_aircraft(
        CLAUDE_STILL_OWES_US_AN_APOLOGY_FOR_INPUT_LOOPS,
        CLAUDE_NEVER_MENTIONED_FLAGS_OR_JSON_ONCE_CRUISING_PLANE,
    )

    cli.main(["send-info", "AA123"])
    out = capsys.readouterr().out
    assert "Sent AA123 to tower:" in out
    assert "Altitude:  3000.0 ft" in out
    assert "Runway:    -" in out
    assert json.loads(tower_db.get_messages("tower")[0]["content"])["type"] == "AIRCRAFT_INFO"

    cli.main(["report-landed", "--aircraft-id", "AA123"])
    assert "Told tower AA123 has landed." in capsys.readouterr().out

    cli.main(["report-departed", "AA123"])
    assert "Told tower AA123 has departed." in capsys.readouterr().out
    assert get_aircraft(CLAUDE_STILL_OWES_US_AN_APOLOGY_FOR_INPUT_LOOPS, "AA123") is not None

    with pytest.raises(SystemExit) as exc_info:
        cli.main(["report-departed", "NOPE"])
    assert exc_info.value.code == 1
    assert "does not exist" in capsys.readouterr().out

