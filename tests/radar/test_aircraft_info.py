# REQ-RAD-016
# Automated tests for sending one plane's current data to tower.
# Notice: Zero terminal input mocking, zero capsys terminal output assertions—pure data contracts

# NOTE (*1): once again, shouldn't exist, no peeping other services inboxes, EVER

import json
from datetime import datetime

import pytest
from src.radar.airplane.aircraft_repo import create_aircraft, init_db, update_runway
from src.radar.airplane.models import AircraftTelemetry, AircraftShim
from src.radar.airplane.runway_requests import send_aircraft_info
from src.tower.messaging import db as tower_db

HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_2 = AircraftShim(
  aircraft_id="AA123",
  latitude=40.7769,
  longitude=-73.8740,
  altitude=3000,
  status="Departing",
  timestamp=datetime(2026, 1, 1, 12, 0, 0),
)

MEM = ":memory:"


def test_sends_the_plane_data():
    conn = init_db(MEM)
    create_aircraft(conn, HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_2)
    sent = []  # a fake "messaging service" that just remembers what it was given
    send_aircraft_info(conn, "AA123", send=sent.append)
    assert json.loads(sent[0]) == {
        "type": "AIRCRAFT_INFO",
        "aircraft_id": "AA123",
        "latitude": 40.7769,
        "longitude": -73.8740,
        "altitude": 3000.0,
        "status": "Departing",
        "runway_id": None,
        "timestamp": "2026-01-01T12:00:00",
    }


def test_sends_the_runway_once_assigned():
    conn = init_db(MEM)
    create_aircraft(conn, HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_2)
    update_runway(conn, "AA123", "R1")
    sent = []
    send_aircraft_info(conn, "AA123", send=sent.append)
    assert json.loads(sent[0])["runway_id"] == "R1"


def test_unknown_plane_sends_nothing():
    conn = init_db(MEM)
    sent = []
    with pytest.raises(ValueError):
        send_aircraft_info(conn, "NOPE", send=sent.append)
    assert sent == []


# --- Refactored Service Handler Test (Replacing the CLI text-scraping test) ---

# NOTE in monkeypatchers
# def test_execute_send_info_handler(tmp_path, monkeypatch): # NOTE: shouldn't exist (*1)
#     """Directly tests the decoupled service call for dispatching aircraft telemetry to tower."""
#     monkeypatch.setattr(tower_db, "DB", str(tmp_path / "test.db"))
#     conn = init_db(MEM)
#     create_aircraft(conn, HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_2)
#
#     # Simulating what the decoupled service handler executes programmatically:
#     info = send_aircraft_info(conn, "AA123")
#
#     # Verify returned dictionary structure
#     assert info["aircraft_id"] == "AA123"
#     assert info["altitude"] == 3000.0
#     assert info["runway_id"] is None
#
#     # Verify the message written to tower's DB inbox buffer directly
#     messages = tower_db.get_messages("tower")
#     assert len(messages) == 1
#     sent_payload = json.loads(messages[0]["content"])
#     assert sent_payload["type"] == "AIRCRAFT_INFO"
#     assert sent_payload["aircraft_id"] == "AA123"


def test_execute_send_info_unknown_plane_handler(): # NOTE: had unused monkeypatch param
    """Verifies that requesting info for an unknown plane raises a ValueError."""
    conn = init_db(MEM)

    with pytest.raises(ValueError):
        send_aircraft_info(conn, "NOPE")