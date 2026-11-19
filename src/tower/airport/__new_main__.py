# REQ-TOW-008, REQ-TOW-009, REQ-TOW-011, REQ-TOW-012, REQ-TOW-013
# main.py — answer radar's runway requests from the terminal.
# Run from the repo root:
#   python -m src.tower.airport answer-requests   (runs TowerScheduler with SQLite-backed priority
#                                                  and response queues, separation checks, and forwarding)
#   python -m src.tower.airport runways           (shows every runway in tower.db)

import sqlite3
import sys

from src.tower.airport.airport_repo import create_airport, create_tables
from src.tower.airport.runway_requests import (
    AIRCRAFT_LANDED,
    AIRCRAFT_PARKED,
    AIRCRAFT_REMOVED,
    FREED,
    NO_RUNWAY,
    PARKED,
    REQUEST_TAKEOFF,
)
from src.tower.airport.runway_status import send_runway_status
from src.tower.airport.scheduler import TowerScheduler
from src.tower.airport.separation import CANCELLED, OPEN, RESOLVED

# The airport tower runs. Same ID and numbers as Command's dashboard (src/command/airport.py).
AIRPORT_ID = "DEMO-001"


def open_airport():
    """Open tower.db, creating the airport and its runways the first time."""
    conn = sqlite3.connect("tower.db")
    create_tables(conn)
    create_airport(conn, AIRPORT_ID, 21000, 40.6413, -73.7781)  # returns False if it already exists
    return conn


def answer(conn):
    scheduler = TowerScheduler(conn, AIRPORT_ID)
    summary = scheduler.run_cycle()
    runways = send_runway_status(conn, AIRPORT_ID)

    if (
        not summary.request_replies
        and not summary.forwarded_messages
        and not summary.separation_changes
        and not runways
    ):
        print("Nothing new to answer.")

    for result in summary.request_replies:
        print(describe_result(result))
    for item in summary.forwarded_messages:
        print(describe_forwarded(item))
    for event in summary.separation_changes:
        print(describe_separation(event))
    for status in runways:
        print(describe_runway(status))

    if summary.queued_requests:
        print(f"Queued runway requests: {', '.join(summary.queued_requests)}")
    if summary.queued_responses:
        print(f"Pending queued responses: {len(summary.queued_responses)}")


def describe_result(result):
    """One line for something tower decided (a runway answer or a freed runway)."""
    plane = result["aircraft_id"]
    if result["type"] == FREED:
        how = "parked" if result.get("reason") == PARKED else "departed"
        return f"{plane}: {how}, runway {result['runway_id']} freed"
    if result["type"] == NO_RUNWAY:
        return f"{plane}: no runway available (told command)"
    if result["request"] == REQUEST_TAKEOFF:
        return f"{plane}: cleared for takeoff on runway {result['runway_id']}"
    return f"{plane}: cleared to land on runway {result['runway_id']}"


def describe_forwarded(item):
    """One line for something tower passed on to command."""
    plane = item["aircraft_id"]
    if item["type"] == AIRCRAFT_REMOVED:
        return f"{plane}: told command it departed"
    if item["type"] == AIRCRAFT_PARKED:
        return f"{plane}: told command it parked"
    if item["type"] == AIRCRAFT_LANDED:
        return f"{plane}: told command it landed"
    return f"{plane}: position sent to command (altitude {item['altitude']})"


def describe_separation(event):
    """One line for a separation event that changed."""
    name = f"Separation {event['separation_id']}"
    planes = f"{event['aircraft_id']} and {event['other_aircraft_id']}"
    if event["status"] == RESOLVED:
        return f"{name}: {planes} resolved (told command)"
    if event["status"] == CANCELLED:
        return f"{name}: {planes} cancelled, a plane left the air (told command)"
    if event["status"] == OPEN:
        spot = f"({event['move_to_latitude']}, {event['move_to_longitude']})"
        return f"{name}: {planes} too close, told radar to move {event['aircraft_id']} to {spot}"
    return f"{name}: {planes} too close, no clear spot yet (told command)"


def describe_runway(status):
    """One line for a runway change tower told command about."""
    runway = f"Runway {status['runway_id']}"
    if status["aircraft_id"] is None:
        return f"{runway}: told command it is free"
    return f"{runway}: told command {status['aircraft_id']} is {status['phase']}"


def show_runways(conn):
    print(f"{'Runway':<8}{'Status':<16}{'Airplane':<10}Updated")
    rows = conn.execute(
        "SELECT runway_id, status, aircraft_id, timestamp FROM runways WHERE airport_id = ? ORDER BY runway_id",
        (AIRPORT_ID,),
    )
    for runway_id, status, aircraft_id, timestamp in rows:
        print(f"{runway_id:<8}{status:<16}{aircraft_id or '-':<10}{timestamp}")


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command not in ("answer-requests", "runways"):
        print("Usage: python -m src.tower.airport answer-requests")
        print("       python -m src.tower.airport runways")
        return
    conn = open_airport()
    try:
        if command == "answer-requests":
            answer(conn)
        else:
            show_runways(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()