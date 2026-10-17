# REQ-RAD-012
# __main__.py — the easy way to create and view airplanes from the terminal.
# Run from the repo root:
#   python -m src.radar.airplane create    (asks for each detail, saves it, sends it to tower)
#   python -m src.radar.airplane list      (shows every airplane in radar.db)
#   python -m src.radar.airplane request-landing    (asks tower for a runway to land)
#   python -m src.radar.airplane request-takeoff    (asks tower for a runway to take off)
#   python -m src.radar.airplane check-replies      (reads tower's answers and saves any runway)
#   python -m src.radar.airplane fake-tower-reply   (TESTING: pretend to be tower and answer radar)
# Python runs a file named __main__.py when you use "python -m" on its folder.

import sys

from src.radar.airplane.aircraft_repo import get_aircraft, init_db
from src.radar.airplane.create_airplane import create_airplane
from src.radar.airplane.runway_requests import (
    check_tower_replies, fake_tower_reply, request_landing, request_takeoff,
)

STATUSES = ["Parked", "Departing", "Landing"]


def ask_text(question):
    """Keep asking until the answer isn't empty."""
    while True:
        answer = input(f"{question}: ").strip()
        if answer:
            return answer
        print("  This can't be empty.")


def ask_number(question):
    """Keep asking until the answer is a number, like 40.64 or -73.78."""
    while True:
        answer = input(f"{question}: ").strip()
        try:
            return float(answer)
        except ValueError:
            print("  Please type a number.")


def ask_status():
    """Keep asking until the answer is Parked, Departing, or Landing (any capitals)."""
    while True:
        answer = input(f"Status ({', '.join(STATUSES)}): ").strip().capitalize()  # "departing" -> "Departing"
        if answer in STATUSES:
            return answer
        print(f"  Please type one of: {', '.join(STATUSES)}")


def create(conn):
    aircraft_id = ask_text("Aircraft ID")
    latitude = ask_number("Latitude")
    longitude = ask_number("Longitude")
    altitude = ask_number("Altitude (feet)")
    status = ask_status()
    try:
        create_airplane(conn, aircraft_id, latitude, longitude, altitude, status)
    except ValueError as error:  # e.g. the ID already exists
        print(f"\nNot created: {error}")
        return
    print(f"\nCreated airplane {aircraft_id} and sent it to tower.")


def request(conn, ask_tower, kind):
    """Ask tower for a runway. ask_tower is request_landing or request_takeoff (REQ-RAD-013)."""
    aircraft_id = ask_text("Aircraft ID")
    try:
        ask_tower(conn, aircraft_id)
    except ValueError as error:  # e.g. no plane with that ID
        print(f"\nNot sent: {error}")
        return
    print(f"\nSent {kind} request for {aircraft_id} to tower.")


def check_replies(conn):
    """Read tower's answers and print what happened (REQ-RAD-013)."""
    results = check_tower_replies(conn)
    if not results:
        print("No replies from tower about radar's planes.")
    for line in results:
        print(line)


def fake_reply(conn):
    """TESTING ONLY: send radar a runway reply as if tower sent it, so you don't type JSON."""
    aircraft_id = ask_text("Aircraft ID")
    if get_aircraft(conn, aircraft_id) is None:  # IDs must match exactly, e.g. "a1" is not "A1"
        print(f"\nNot sent: radar has no aircraft {aircraft_id}")
        return
    runway_id = input("Runway (leave empty for no runway): ").strip()
    fake_tower_reply(aircraft_id, runway_id)
    answer = f"runway {runway_id}" if runway_id else "no runway"
    print(f"\nTower replied: {answer} for {aircraft_id} (test reply). Run check-replies to read it.")


def show_aircraft(conn):
    """Print every airplane in radar.db as a table with lined-up columns."""
    rows = conn.execute(
        "SELECT aircraft_id, latitude, longitude, altitude, status, timestamp, runway_id FROM aircraft"
    ).fetchall()
    if not rows:
        print("\nNo airplanes in radar.db yet.")
        return
    print(f"\nAirplanes in radar.db ({len(rows)})")
    # In the {} below, < means left-aligned, > means right-aligned, and the number is the width.
    print(f"{'ID':<8}{'Latitude':>10}{'Longitude':>12}{'Altitude':>11}  {'Status':<11}{'Runway':<8}Timestamp")
    print("-" * 81)
    for aircraft_id, latitude, longitude, altitude, status, timestamp, runway_id in rows:
        runway = runway_id or "-"  # "-" when tower hasn't assigned one yet
        print(f"{aircraft_id:<8}{latitude:>10.4f}{longitude:>12.4f}{altitude:>11.1f}  {status:<11}{runway:<8}{timestamp}")


def main():
    # sys.argv is what was typed after "python -m src.radar.airplane".
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    commands = ("create", "list", "request-landing", "request-takeoff", "check-replies", "fake-tower-reply")
    if command not in commands:
        for number, name in enumerate(commands):
            start = "Usage:" if number == 0 else "      "
            print(f"{start} python -m src.radar.airplane {name}")
        return
    conn = init_db("radar.db")
    try:
        if command == "create":
            create(conn)
        elif command == "list":
            show_aircraft(conn)
        elif command == "request-landing":
            request(conn, request_landing, "landing")
        elif command == "request-takeoff":
            request(conn, request_takeoff, "takeoff")
        elif command == "check-replies":
            check_replies(conn)
        else:
            fake_reply(conn)
    except (KeyboardInterrupt, EOFError):  # Ctrl+C or Ctrl+D while it's asking
        print("\nCancelled.")
    finally:
        conn.close()  # always close the database, even if something went wrong


if __name__ == "__main__":
    main()
