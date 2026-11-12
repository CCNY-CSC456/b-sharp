# REQ-RAD-012
# Automated tests for Create Airplane.
# Notice: No input monkeypatching, no capsys string matching—just pure logic & data verification.

from datetime import datetime
from dataclasses import replace

import pytest
from src.radar.airplane.aircraft_repo import create_aircraft, init_db
from src.radar.airplane.create_airplane import create_airplane, send_to_tower
from src.radar.airplane.models import AircraftTelemetry, AircraftShim
from src.tower.messaging import db as tower_db

MEM = ":memory:"

HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_3 = AircraftShim(
  aircraft_id="AA123",
  latitude=40.7769,
  longitude=-73.8740,
  altitude=0,
  status="Parked",
  timestamp=datetime(2026, 1, 1, 12, 0, 0),
)


def test_create_saves_the_plane():
    conn = init_db(MEM)
    create_aircraft(conn, HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_3)
    rows = conn.execute("SELECT * FROM aircraft").fetchall()
    assert rows == [("AA123", 40.7769, -73.8740, 0.0, "Parked", "2026-01-01T12:00:00", None)]


def test_invalid_status_rejected():
    with pytest.raises(ValueError):
        # Clones the base constant with a different status, zero boilerplates/functions needed
        create_aircraft(init_db(MEM), replace(HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_3, status="Flying"))


def test_duplicate_id_rejected():
    conn = init_db(MEM)
    create_aircraft(conn, HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_3)
    with pytest.raises(ValueError):
        create_aircraft(conn, HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_3)


def test_create_airplane_sends_the_plane():
    conn = init_db(MEM)
    sent = []
    plane = create_airplane(conn, "AA123", 40.7769, -73.8740, 0, "Parked", send=sent.append)
    assert sent == [plane]

# # NOTE in monkeypatchers
# def test_send_to_tower(tmp_path, monkeypatch):
#     monkeypatch.setattr(tower_db, "DB", str(tmp_path / "test.db"))
#     send_to_tower(HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_3)
#     inbox = tower_db.get_messages("tower")
#     assert inbox[0]["sender"] == "radar"
#     assert "AA123" in inbox[0]["content"]


# --- Refactored Service Handler Test (Replacing the brittle CLI text-scraping test) ---

# # NOTE in monkeypatchers
# def test_execute_create_airplane_handler(tmp_path, monkeypatch):
#     """Directly tests the decoupled service function instead of mocking terminal input/output."""
#     monkeypatch.setattr(tower_db, "DB", str(tmp_path / "test.db"))
#     conn = init_db(MEM)
#
#     sent = []
#     # Simulating what the decoupled service handler executes programmatically:
#     plane = create_airplane(conn, "B46", 40.64, -73.78, 3000, "Departing", send=sent.append)
#
#     # Verify state and output payload directly
#     row = conn.execute("SELECT aircraft_id, altitude, status FROM aircraft").fetchone()
#     assert row == ("B46", 3000.0, "Departing")
#     assert plane.aircraft_id == "B46"
#     assert len(sent) == 1
#
# # NOTE in monkeypatchers
# def test_execute_create_airplane_duplicate_handling(tmp_path, monkeypatch):
#     """Verifies that duplicate creation raises a clean ValueError via the service layer."""
#     monkeypatch.setattr(tower_db, "DB", str(tmp_path / "test.db"))
#     conn = init_db(MEM)
#     create_aircraft(conn, HARD_CODED_REPLACEMENT_FOR_HARD_CODED_FUNCTION_3)  # AA123 already exists
#
#     with pytest.raises(ValueError):
#         create_airplane(conn, "AA123", 0, 0, 0, "Parked")