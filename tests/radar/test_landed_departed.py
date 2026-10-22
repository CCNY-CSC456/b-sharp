# REQ-RAD-014
# Automated tests for radar telling tower a plane is done with its runway. CI runs these with: pytest tests/radar
# Every test uses an in-memory database and fake messaging, so tower doesn't need to run.

import json
from datetime import datetime

import pytest
from src.radar.airplane.aircraft_repo import create_aircraft, delete_aircraft, get_aircraft, init_db
from src.radar.airplane.models import AircraftTelemetry
from src.radar.airplane.runway_requests import check_tower_replies, report_departed, report_landed

OLD_TIME = datetime(2026, 1, 1, 12, 0, 0)


def setup_plane(aircraft_id="AA123"):
    conn = init_db(":memory:")
    create_aircraft(conn, AircraftTelemetry(
        aircraft_id=aircraft_id, latitude=40.7769, longitude=-73.8740,
        altitude=0, status="Parked", timestamp=OLD_TIME,
    ))
    return conn


def test_report_landed_sends_json_and_keeps_plane():
    conn = setup_plane()
    before = get_aircraft(conn, "AA123")
    sent = []
    report_landed(conn, "AA123", send=sent.append)
    message = json.loads(sent[0])
    assert set(message) == {"type", "aircraft_id", "timestamp"}
    assert message["type"] == "LANDED"
    assert message["aircraft_id"] == "AA123"
    datetime.strptime(message["timestamp"], "%Y-%m-%dT%H:%M:%S")  # fails if the format is wrong
    assert get_aircraft(conn, "AA123") == before  # plane unchanged


def test_report_departed_sends_json_and_deletes_plane():
    conn = setup_plane()
    sent = []
    report_departed(conn, "AA123", send=sent.append)
    message = json.loads(sent[0])
    assert set(message) == {"type", "aircraft_id", "timestamp"}
    assert message["type"] == "DEPARTED"
    assert message["aircraft_id"] == "AA123"
    datetime.strptime(message["timestamp"], "%Y-%m-%dT%H:%M:%S")
    assert get_aircraft(conn, "AA123") is None


@pytest.mark.parametrize("report", [report_landed, report_departed])
def test_report_for_missing_plane_raises(report):
    conn = setup_plane()
    sent = []
    with pytest.raises(ValueError):
        report(conn, "NOPE", send=sent.append)
    assert sent == []  # nothing was sent to tower


def test_departed_send_failure_keeps_plane():
    conn = setup_plane()

    def broken_send(content):
        raise RuntimeError("messaging is down")

    with pytest.raises(RuntimeError):
        report_departed(conn, "AA123", send=broken_send)
    assert get_aircraft(conn, "AA123") is not None  # kept so it can be retried


def test_old_runway_reply_ignored_after_departure():
    conn = setup_plane()
    old_reply = {"sender": "tower", "recipient": "radar",
                 "content": json.dumps({"type": "RUNWAY_ASSIGNED", "aircraft_id": "AA123", "runway_id": "R1"})}
    check_tower_replies(conn, get=lambda: [old_reply])
    report_departed(conn, "AA123", send=lambda content: None)
    assert check_tower_replies(conn, get=lambda: [old_reply]) == []  # the same old reply comes back
    assert get_aircraft(conn, "AA123") is None  # and the plane is not brought back


def test_delete_aircraft_missing_plane_raises():
    with pytest.raises(ValueError):
        delete_aircraft(init_db(":memory:"), "NOPE")
