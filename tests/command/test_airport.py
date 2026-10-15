"""REQ-OPS-001: verify the airport snapshot against Tower's current contract."""

from datetime import datetime
import sqlite3

from src.command.airport import get_airport_state
from src.tower.airport.airport_repo import TIME_FORMAT, create_airport, create_tables


def test_demo_matches_tower_airport_fields_and_runway_count():
    demo = get_airport_state()
    with sqlite3.connect(":memory:") as conn:
        conn.row_factory = sqlite3.Row
        assert create_tables(conn)
        assert create_airport(conn, demo["airport_id"], demo["perimeter"], demo["latitude"], demo["longitude"])
        airport = dict(conn.execute("SELECT * FROM airport").fetchone())
        runways = conn.execute("SELECT * FROM runways ORDER BY runway_id").fetchall()
    assert airport == {field: demo[field] for field in airport}
    assert demo["number_of_runways"] == len(demo["runways"]) == len(runways)
    assert [runway["runway_id"] for runway in demo["runways"]] == [row["runway_id"] for row in runways]
    for runway in demo["runways"]:
        assert runway["status"] in {"Available", "Not Available"}
        datetime.strptime(runway["timestamp"], TIME_FORMAT)


def test_callers_cannot_modify_the_shared_demo():
    first = get_airport_state()
    original = get_airport_state()
    first["perimeter"] = -1
    first["runways"][0]["status"] = "Not Available"
    first["runways"].clear()
    assert get_airport_state() == original
