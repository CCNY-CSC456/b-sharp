# REQ-RAD-012
# create_airplane.py — creates one airplane, saves it, and tells tower about it.
# Planes do NOT move yet. This only creates them.

# Tower's messaging functions, used exactly as tower wrote them.
from src.tower.messaging.db import init_db as init_messages_db, save_message

from src.radar.airplane.aircraft_repo import create_aircraft, now
from src.radar.airplane.models import AircraftTelemetry, AircraftShim

from dataclasses import asdict

from datetime import datetime
import json


def send_to_tower(plane):
    """Put the plane's data in tower's inbox using the messaging service.

    Run from the repo root, the same as tower, so both use the same messages.db file.
    """
    init_messages_db()  # makes sure the messages table exists (safe to call every time)
    # A message's content is text, so the plane is sent as JSON, like:
    # {"aircraft_id":"AA123","latitude":40.7,...,"timestamp":"2026-10-08T14:30:00"}
    #save_message("radar", "tower", plane.model_dump_json())

    match plane:
      case AircraftTelemetry():
        payload = plane.model_dump_json()
      case AircraftShim(): # as name suggests, interim shim, so leave ugly!
        payload = json.dumps(asdict(plane), default=lambda obj: obj.isoformat() if isinstance(obj, datetime) else str(obj))
      case _:
        raise TypeError(f"Unsupported airplane type: {type(plane)}")

    save_message("radar", "tower", payload)


def create_airplane(conn, aircraft_id, latitude, longitude, altitude, status, send=send_to_tower):
    """Build an airplane, save it in radar's database, send it to tower, and return it.

    conn comes from aircraft_repo.init_db().
    Raises ValueError for a bad status or an aircraft_id that already exists.
    `send` is only there so tests can swap in a fake instead of the real messaging service.
    """
    plane = AircraftTelemetry(
        aircraft_id=aircraft_id,
        latitude=latitude,
        longitude=longitude,
        altitude=altitude,
        status=status,
        timestamp=now(),
    )
    create_aircraft(conn, plane)  # if this fails, nothing is sent to tower
    send(plane)
    return plane
