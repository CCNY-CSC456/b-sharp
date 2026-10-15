# REQ-RAD-012
# __main__.py — the easy way to create and view airplanes from the terminal.
# Run from the repo root:
#   python -m src.radar.airplane create    (asks for each detail, saves it, sends it to tower)
#   python -m src.radar.airplane list      (shows every airplane in radar.db)
# Python runs a file named __main__.py when you use "python -m" on its folder.

import sys

from src.radar.airplane.aircraft_repo import init_db
from src.radar.airplane.create_airplane import create_airplane

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


def show_aircraft(conn):
    """Print every airplane in radar.db as a table with lined-up columns."""
    rows = conn.execute("SELECT * FROM aircraft").fetchall()
    if not rows:
        print("\nNo airplanes in radar.db yet.")
        return
    print(f"\nAirplanes in radar.db ({len(rows)})")
    # In the {} below, < means left-aligned, > means right-aligned, and the number is the width.
    print(f"{'ID':<8}{'Latitude':>10}{'Longitude':>12}{'Altitude':>11}  {'Status':<11}Timestamp")
    print("-" * 73)
    for aircraft_id, latitude, longitude, altitude, status, timestamp in rows:
        print(f"{aircraft_id:<8}{latitude:>10.4f}{longitude:>12.4f}{altitude:>11.1f}  {status:<11}{timestamp}")


def main():
    # sys.argv is what was typed after "python -m src.radar.airplane".
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command not in ("create", "list"):
        print("Usage: python -m src.radar.airplane create")
        print("       python -m src.radar.airplane list")
        return
    conn = init_db("radar.db")
    try:
        if command == "create":
            create(conn)
        else:
            show_aircraft(conn)
    except (KeyboardInterrupt, EOFError):  # Ctrl+C or Ctrl+D while it's asking
        print("\nCancelled.")
    finally:
        conn.close()  # always close the database, even if something went wrong


if __name__ == "__main__":
    main()
