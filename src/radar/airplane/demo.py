# REQ-RAD-012
# demo.py — creates one airplane for real and prints what got saved, so you can see it.
# Run from the repo root:
#   python -m src.radar.airplane.demo            (creates AA123)
#   python -m src.radar.airplane.demo UA456      (creates a plane with that ID)

import sys
from src.radar.airplane.aircraft_repo import init_db
from src.radar.airplane.create_airplane import create_airplane
from src.tower.messaging.db import get_messages

aircraft_id = sys.argv[1] if len(sys.argv) > 1 else "AA123"
conn = init_db("radar.db")
try:
    plane = create_airplane(conn, aircraft_id, 40.7769, -73.8740, 0, "Parked")
    print("Created:", plane)
except ValueError as error:          # e.g. the ID already exists
    print("Not created:", error)

print("\n--- radar.db (aircraft table) ---")
for row in conn.execute("SELECT * FROM aircraft"):
    print(row)
conn.close()

print("\n--- tower's inbox (messages.db) ---")
for message in get_messages("tower"):
    print(message)
