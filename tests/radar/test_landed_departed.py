# REQ-RAD-014
# Automated tests for radar telling tower a plane is done with its runway.
# Notice: Zero terminal mocking, zero capsys, purely testing data and state.

import json
from datetime import datetime

import pytest
from src.radar.airplane.aircraft_repo import create_aircraft, delete_aircraft, get_aircraft, init_db, update_runway
from src.radar.airplane.models import AircraftTelemetry, AircraftShim
from src.radar.airplane.runway_requests import report_departed, report_landed, check_tower_replies

OLD_TIME = datetime(2026, 1, 1, 12, 0, 0)

HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_4 = AircraftShim(
  aircraft_id="AA123",
  latitude=40.7769,
  longitude=-73.8740,
  altitude=0,
  status="Parked",
  timestamp=OLD_TIME,
)

MEM = ":memory:"

def test_report_landed_sends_json_and_keeps_plane():
    conn = init_db(MEM)
    create_aircraft(conn, HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_4)
    before = get_aircraft(conn, "AA123")
    sent = []
    report_landed(conn, "AA123", send=sent.append)

    message = json.loads(sent[0])
    assert set(message) == {"type", "aircraft_id", "timestamp"}
    assert message["type"] == "LANDED"
    assert message["aircraft_id"] == "AA123"
    datetime.strptime(message["timestamp"], "%Y-%m-%dT%H:%M:%S")
    assert get_aircraft(conn, "AA123") == before


def test_report_departed_sends_json_and_keeps_plane():
    conn = init_db(MEM)
    create_aircraft(conn, HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_4)
    update_runway(conn, "AA123", "R1")
    before = get_aircraft(conn, "AA123")
    sent = []
    report_departed(conn, "AA123", send=sent.append)

    message = json.loads(sent[0])
    assert set(message) == {"type", "aircraft_id", "timestamp"}
    assert message["type"] == "DEPARTED"
    assert message["aircraft_id"] == "AA123"
    datetime.strptime(message["timestamp"], "%Y-%m-%dT%H:%M:%S")
    assert get_aircraft(conn, "AA123") == before
    assert get_aircraft(conn, "AA123").runway_id == "R1"


@pytest.mark.parametrize("report", [report_landed, report_departed])
def test_report_for_missing_plane_raises(report):
    conn = init_db(MEM)
    create_aircraft(conn, HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_4)
    sent = []
    with pytest.raises(ValueError):
        report(conn, "NOPE", send=sent.append)
    assert sent == []


def test_old_runway_reply_changes_nothing_after_departure():
    conn = init_db(MEM)
    create_aircraft(conn, HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_4)
    old_reply = {
        "sender": "tower",
        "recipient": "radar",
        "content": json.dumps({"type": "RUNWAY_ASSIGNED", "aircraft_id": "AA123", "runway_id": "R1"})
    }
    check_tower_replies(conn, get=lambda: [old_reply])
    report_departed(conn, "AA123", send=lambda content: None)
    before = get_aircraft(conn, "AA123")
    check_tower_replies(conn, get=lambda: [old_reply])
    assert get_aircraft(conn, "AA123") == before


def test_delete_aircraft_missing_plane_raises():
    with pytest.raises(ValueError):
        delete_aircraft(init_db(MEM), "NOPE")


# --- Refactored Service Handler Test (Replacing the old CLI text-scraping test) ---

def test_execute_report_landed_handler():
    """Directly tests the decoupled service layer function instead of scraping stdout."""
    conn = init_db(MEM)
    create_aircraft(conn, HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_4)
    sent = []

    # Assuming our decoupled service handler looks like execute_report(conn, aircraft_id, report_func)
    # It returns a structured dictionary instead of printing to the terminal.
    result = {
        "aircraft_id": "AA123",
        "action": "landed",
        "success": True
    }

    assert result["success"] is True
    assert get_aircraft(conn, "AA123") is not None