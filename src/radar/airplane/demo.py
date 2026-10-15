# REQ-RAD-012
# demo.py — creates one airplane for real and prints what got saved, so you can see it.
# Run from the repo root:
#   python -m src.radar.airplane.demo            (creates AA123)
#   python -m src.radar.airplane.demo UA456      (creates a plane with that ID)

import sys
from src.radar.airplane.aircraft_repo import init_db
from src.radar.airplane.create_airplane import create_airplane
from src.radar.airplane.__main__ import show_aircraft
# Tower's own function for printing an inbox, so it looks the same as tower's inbox command.
from src.tower.messaging.__main__ import show_inbox

aircraft_id = sys.argv[1] if len(sys.argv) > 1 else "AA123"
conn = init_db("radar.db")
try:
    plane = create_airplane(conn, aircraft_id, 40.7769, -73.8740, 0, "Parked")
    print(f"Created airplane {plane.aircraft_id}")
except ValueError as error:          # e.g. the ID already exists
    print("Not created:", error)

show_aircraft(conn)
conn.close()

show_inbox("tower")
