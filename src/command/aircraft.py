"""REQ-OPS-006: read recorded aircraft coordinates without changing Radar data."""

from contextlib import closing
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sqlite3

from src.command.airport import REPOSITORY_ROOT
from src.tower.messaging import db


def finite_number(value):
    """SQLite may contain missing, malformed, or non-finite telemetry."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def latest_lifecycle(aircraft_ids):
    """Read Radar's explicit lifecycle reports, including consumed messages.

    Radar retains aircraft rows after departure. Only an explicit DEPARTED
    report hides a record; missing Tower assignments never imply departure.
    A later request or telemetry message makes the aircraft visible again.
    """
    events = {}
    path = Path(db.DB).expanduser().resolve()
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1)) as conn:
            rows = conn.execute(
                "SELECT content FROM messages WHERE sender = 'radar' "
                "AND recipient IN ('tower', 'tower-READ') ORDER BY rowid DESC"
            )
            for (content,) in rows:
                try:
                    message = json.loads(content)
                except (TypeError, ValueError):
                    continue
                if not isinstance(message, dict):
                    continue
                aircraft_id = message.get("aircraft_id")
                if not isinstance(aircraft_id, str) or aircraft_id not in aircraft_ids or aircraft_id in events:
                    continue
                event = message.get("type")
                if event in ("DEPARTED", "LANDED", "REQUEST_LANDING", "REQUEST_TAKEOFF"):
                    events[aircraft_id] = event
                elif event is None and "latitude" in message and "longitude" in message:
                    events[aircraft_id] = "TELEMETRY"
                if len(events) == len(aircraft_ids):
                    break
    except sqlite3.Error:
        return {}, False
    return events, True


def get_aircraft_state():
    """Return Radar's last recorded positions, not simulated flight movement."""
    path = Path(os.environ.get("COMMAND_RADAR_DB", str(REPOSITORY_ROOT / "radar.db"))).expanduser().resolve()
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT aircraft_id, latitude, longitude, altitude, status, timestamp "
            "FROM aircraft ORDER BY aircraft_id"
        ).fetchall()

    events, lifecycle_available = latest_lifecycle({row["aircraft_id"] for row in rows})
    aircraft = []
    invalid_coordinates = departed = 0
    for row in rows:
        if events.get(row["aircraft_id"]) == "DEPARTED":
            departed += 1
            continue
        latitude, longitude = finite_number(row["latitude"]), finite_number(row["longitude"])
        if latitude is None or longitude is None or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            invalid_coordinates += 1
            continue
        aircraft.append(dict(
            aircraft_id=row["aircraft_id"], latitude=latitude, longitude=longitude,
            altitude=finite_number(row["altitude"]), status=row["status"], timestamp=row["timestamp"],
        ))
    return dict(
        aircraft=aircraft, invalid_coordinate_count=invalid_coordinates,
        departed_count=departed, lifecycle_available=lifecycle_available,
        observed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
