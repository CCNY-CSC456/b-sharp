# REQ-TOW-008, REQ-TOW-011
# __main__.py — answer radar's runway requests from the terminal.
# Run from the repo root:
#   python -m src.tower.airport answer-requests   (reads tower's inbox, assigns and frees runways, replies to radar)
#   python -m src.tower.airport runways           (shows every runway in tower.db)
# Python runs a file named __main__.py when you use "python -m" on its folder.

import sqlite3
import sys

from src.tower.airport.airport_repo import create_airport, create_tables
from src.tower.airport.runway_requests import FREED, NO_RUNWAY, REQUEST_TAKEOFF, answer_requests

# The airport tower runs. Same ID and numbers as Command's dashboard (src/command/airport.py).
AIRPORT_ID = "DEMO-001"


def open_airport():
    """Open tower.db, creating the airport and its runways the first time."""
    conn = sqlite3.connect("tower.db")
    create_tables(conn)
    create_airport(conn, AIRPORT_ID, 21000, 40.6413, -73.7781)  # returns False if it already exists
    return conn


def answer(conn):
    results = answer_requests(conn, AIRPORT_ID)
    if not results:
        print("Nothing new to answer.")
    for result in results:
        plane = result["aircraft_id"]
        if result["type"] == FREED:
            print(f"{plane}: departed, runway {result['runway_id']} freed")
        elif result["type"] == NO_RUNWAY:
            print(f"{plane}: no runway available")
        elif result["request"] == REQUEST_TAKEOFF:
            print(f"{plane}: cleared for takeoff on runway {result['runway_id']}")
        else:
            print(f"{plane}: cleared to land on runway {result['runway_id']}")


def show_runways(conn):
    print(f"{'Runway':<8}{'Status':<16}{'Airplane':<10}Updated")
    rows = conn.execute(
        "SELECT runway_id, status, aircraft_id, timestamp FROM runways WHERE airport_id = ? ORDER BY runway_id",
        (AIRPORT_ID,),
    )
    for runway_id, status, aircraft_id, timestamp in rows:
        print(f"{runway_id:<8}{status:<16}{aircraft_id or '-':<10}{timestamp}")


def main():
    # sys.argv is what was typed after "python -m src.tower.airport".
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
        conn.close()  # always close the database, even if something went wrong


if __name__ == "__main__":
    main()
