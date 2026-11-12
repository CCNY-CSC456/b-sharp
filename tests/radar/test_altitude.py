# REQ-RAD-015
# Automated tests for changing an airplane's altitude.

# NOTE (*1): This test shouldn't really even exist, because it's reading directly
# from Tower's messages, which is a big fat no no and hard red line
# NOTE (*2): this also shouldn't be doing this, no checking other service's
# message boxes slash queues; fundementally need to refactor

import json
from datetime import datetime

import pytest
from src.radar.airplane.aircraft_repo import create_aircraft, get_aircraft, init_db, update_altitude
from src.radar.airplane.models import AircraftTelemetry, AircraftShim
from src.tower.messaging import db as tower_db


HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_1 = AircraftShim(
  aircraft_id="AA123",
  latitude=40.7769,
  longitude=-73.8740,
  altitude=0,
  status="Departing",
  timestamp=datetime(2026, 1, 1, 12, 0, 0),
)


def test_update_altitude():
    conn = init_db(":memory:")
    create_aircraft(conn, HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_1)
    update_altitude(conn, "AA123", 3000)
    plane = get_aircraft(conn, "AA123")
    assert plane.altitude == 3000.0
    assert plane.timestamp > datetime(2026, 1, 1, 12, 0, 0)  # timestamp was refreshed


def test_update_altitude_unknown_plane():
    conn = init_db(":memory:")
    with pytest.raises(ValueError):
        update_altitude(conn, "NOPE", 3000)


def test_update_altitude_negative_rejected():
    conn = init_db(":memory:")
    create_aircraft(conn, HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_1)
    with pytest.raises(ValueError):
        update_altitude(conn, "AA123", -10)
    assert get_aircraft(conn, "AA123").altitude == 0.0  # nothing changed


# --- Refactored Service Handler Test (Replacing the CLI text-scraping test) ---

# NOTE in monkey patchers
# def test_execute_set_altitude_handler(tmp_path, monkeypatch): # NOTE needs tower running & setup or something (?) (*1)
#     """Directly tests the decoupled service workflow for updating altitude and syncing tower."""
#     monkeypatch.setattr(tower_db, "DB", str(tmp_path / "test.db"))
#     conn = init_db(":memory:")
#     create_aircraft(conn, HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_1)
#
#     # Simulating what the decoupled service handler executes programmatically:
#     update_altitude(conn, "AA123", 3000.0)
#
#     # Verify local database state update
#     plane = get_aircraft(conn, "AA123")
#     assert plane.altitude == 3000.0
#
#     # Verify outgoing tower message payload directly from the database buffer
#     messages = tower_db.get_messages("tower")
#     assert len(messages) == 1
#     sent = json.loads(messages[0]["content"])
#     assert sent["type"] == "AIRCRAFT_INFO"
#     assert sent["aircraft_id"] == "AA123"
#     assert sent["altitude"] == 3000.0

# NOTE in monkey patchers
# def test_execute_set_altitude_unknown_plane_handler(tmp_path, monkeypatch): # NOTE: (*2)
#     """Verifies that updating an unknown plane raises a ValueError and sends nothing."""
#     monkeypatch.setattr(tower_db, "DB", str(tmp_path / "test.db"))
#     conn = init_db(":memory:")
#
#     with pytest.raises(ValueError):
#         update_altitude(conn, "NOPE", 3000.0)
#
#     tower_db.init_db()  # create the empty messages table so we can check it
#     assert tower_db.get_messages("tower") == []  # nothing sent to tower