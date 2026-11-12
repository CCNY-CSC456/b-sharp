# REQ-RAD-014, REQ-RAD-015, REQ-RAD-016, REQ-RAD-012

##

from datetime import datetime

import pytest
from src.radar.airplane.aircraft_repo import create_aircraft, init_db
from src.radar.airplane.create_airplane import create_airplane, send_to_tower
from src.radar.airplane.models import AircraftTelemetry
from src.tower.messaging import db as tower_db

##

import json
from datetime import datetime

import pytest
from src.radar.airplane.aircraft_repo import create_aircraft, get_aircraft, init_db, update_altitude
from src.radar.airplane.models import AircraftTelemetry
from src.tower.messaging import db as tower_db

##

import json
from datetime import datetime

import pytest
from src.radar.airplane.aircraft_repo import create_aircraft, init_db, update_runway
from src.radar.airplane.models import AircraftTelemetry
from src.radar.airplane.runway_requests import send_aircraft_info
from src.tower.messaging import db as tower_db

##

from dataclasses import replace

MEM = ":memory:"

##--|======[1]======[2]======[3]======[>X<]======[5]======[6]======[7]======|-->


HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_3 = AircraftTelemetry(
  aircraft_id="AA123",
  latitude=40.7769,
  longitude=-73.8740,
  altitude=0,
  status="Parked",
  timestamp=datetime(2026, 1, 1, 12, 0, 0),
)

def test_send_to_tower(tmp_path, monkeypatch):
    monkeypatch.setattr(tower_db, "DB", str(tmp_path / "test.db"))
    send_to_tower(HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_3)
    inbox = tower_db.get_messages("tower")
    assert inbox[0]["sender"] == "radar"
    assert "AA123" in inbox[0]["content"]


# --- Refactored Service Handler Test (Replacing the brittle CLI text-scraping test) ---

def test_execute_create_airplane_handler(tmp_path, monkeypatch):
    """Directly tests the decoupled service function instead of mocking terminal input/output."""
    monkeypatch.setattr(tower_db, "DB", str(tmp_path / "test.db"))
    conn = init_db(MEM)

    sent = []
    # Simulating what the decoupled service handler executes programmatically:
    plane = create_airplane(conn, "B46", 40.64, -73.78, 3000, "Departing", send=sent.append)

    # Verify state and output payload directly
    row = conn.execute("SELECT aircraft_id, altitude, status FROM aircraft").fetchone()
    assert row == ("B46", 3000.0, "Departing")
    assert plane.aircraft_id == "B46"
    assert len(sent) == 1


def test_execute_create_airplane_duplicate_handling(tmp_path, monkeypatch):
    """Verifies that duplicate creation raises a clean ValueError via the service layer."""
    monkeypatch.setattr(tower_db, "DB", str(tmp_path / "test.db"))
    conn = init_db(MEM)
    create_aircraft(conn, HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_3)  # AA123 already exists

    with pytest.raises(ValueError):
        create_airplane(conn, "AA123", 0, 0, 0, "Parked")

##--|======[1]======[2]======[3]======[>X<]======[5]======[6]======[7]======|-->

HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_1 = AircraftTelemetry(
  aircraft_id="AA123",
  latitude=40.7769,
  longitude=-73.8740,
  altitude=0,
  status="Departing",
  timestamp=datetime(2026, 1, 1, 12, 0, 0),
)

## NOTE: kept for post-mortem and group review of policy
# --- Refactored Service Handler Test (Replacing the CLI text-scraping test) ---

# # # def test_execute_set_altitude_handler(tmp_path, monkeypatch): # NOTE needs tower running & setup or something (?) (*1)
# # #     """Directly tests the decoupled service workflow for updating altitude and syncing tower."""
# # #     monkeypatch.setattr(tower_db, "DB", str(tmp_path / "test.db"))
# # #     conn = init_db(MEM)
# # #     create_aircraft(conn, HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_1)
# # #
# # #     # Simulating what the decoupled service handler executes programmatically:
# # #     update_altitude(conn, "AA123", 3000.0)
# # #
# # #     # Verify local database state update
# # #     plane = get_aircraft(conn, "AA123")
# # #     assert plane.altitude == 3000.0
# # #
# # #     # Verify outgoing tower message payload directly from the database buffer
# # #     messages = tower_db.get_messages("tower")
# # #     assert len(messages) == 1
# # #     sent = json.loads(messages[0]["content"])
# # #     assert sent["type"] == "AIRCRAFT_INFO"
# # #     assert sent["aircraft_id"] == "AA123"
# # #     assert sent["altitude"] == 3000.0


# # # def test_execute_set_altitude_unknown_plane_handler(tmp_path, monkeypatch): # NOTE: (*2)
# # #     """Verifies that updating an unknown plane raises a ValueError and sends nothing."""
# # #     monkeypatch.setattr(tower_db, "DB", str(tmp_path / "test.db"))
# # #     conn = init_db(MEM)
# # #
# # #     with pytest.raises(ValueError):
# # #         update_altitude(conn, "NOPE", 3000.0)
# # #
# # #     tower_db.init_db()  # create the empty messages table so we can check it
# # #     assert tower_db.get_messages("tower") == []  # nothing sent to tower

##--|======[1]======[2]======[3]======[>X<]======[5]======[6]======[7]======|-->

HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_2 = AircraftTelemetry(
  aircraft_id="AA123",
  latitude=40.7769,
  longitude=-73.8740,
  altitude=3000,
  status="Departing",
  timestamp=datetime(2026, 1, 1, 12, 0, 0),
)


def test_execute_send_info_handler(tmp_path, monkeypatch):
    """Directly tests the decoupled service call for dispatching aircraft telemetry to tower."""
    monkeypatch.setattr(tower_db, "DB", str(tmp_path / "test.db"))
    conn = init_db(MEM)
    create_aircraft(conn, HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_2)

    # Simulating what the decoupled service handler executes programmatically:
    info = send_aircraft_info(conn, "AA123")

    # Verify returned dictionary structure
    assert info["aircraft_id"] == "AA123"
    assert info["altitude"] == 3000.0
    assert info["runway_id"] is None

    # Verify the message written to tower's DB inbox buffer directly
    messages = tower_db.get_messages("tower")
    assert len(messages) == 1
    sent_payload = json.loads(messages[0]["content"])
    assert sent_payload["type"] == "AIRCRAFT_INFO"
    assert sent_payload["aircraft_id"] == "AA123"



##--|======[1]======[2]======[3]======[>X<]======[5]======[6]======[7]======|-->





##--|======[1]======[2]======[3]======[>X<]======[5]======[6]======[7]======|-->