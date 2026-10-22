# Airplane commands (REQ-RAD-012, REQ-RAD-013, REQ-RAD-014)

Run everything from the repo root (the `b-sharp` folder), with the venv on:
```
source venv/bin/activate
```

## Airplanes (radar)
```
python -m src.radar.airplane create              # asks ID, latitude, longitude, altitude, status
python -m src.radar.airplane list                # table of every plane in radar.db
```

## Runways (radar <-> tower)
```
python -m src.radar.airplane request-landing     # ask tower for a runway to land
python -m src.radar.airplane request-takeoff     # ask tower for a runway to take off
python -m src.radar.airplane fake-tower-reply    # TESTING: answer as tower (empty runway = no runway)
python -m src.radar.airplane check-replies       # read tower's answers, save any runway
```

## Done with the runway (REQ-RAD-014)
```
python -m src.radar.airplane report-landed       # tell tower the plane landed (plane stays in radar.db)
python -m src.radar.airplane report-departed     # tell tower the plane left (plane stays in radar.db)
```
- Both ask for the aircraft ID. Tower uses these to free the plane's runway.
- If radar has no plane with that ID, you get `Not sent: aircraft a1 does not exist` and nothing is sent.

## Messages (tower's messaging)
```
python -m src.tower.messaging send               # asks sender, recipient, message
python -m src.tower.messaging inbox              # asks whose inbox, then lists it
```

## Full walkthrough
```
python -m src.radar.airplane create              # e.g. a1, 40.77, -73.87, 2000, Landing
python -m src.radar.airplane request-landing     # a1
python -m src.tower.messaging inbox              # tower -> see REQUEST_LANDING
python -m src.radar.airplane fake-tower-reply    # a1, R1
python -m src.radar.airplane check-replies       # a1: runway R1 assigned
python -m src.radar.airplane list                # Runway column shows R1
```

## Walkthrough: land, then depart (REQ-RAD-014)
```
python -m src.radar.airplane create              # a1, 40.77, -73.87, 2000, Landing
python -m src.radar.airplane request-landing     # a1
python -m src.radar.airplane fake-tower-reply    # a1, R1
python -m src.radar.airplane check-replies       # a1: runway R1 assigned
python -m src.radar.airplane report-landed       # a1  ->  Told tower a1 has landed.
python -m src.tower.messaging inbox              # tower -> last message is LANDED
python -m src.radar.airplane list                # a1 is still there
python -m src.radar.airplane report-departed     # a1  ->  Told tower a1 has departed.
python -m src.tower.messaging inbox              # tower -> last message is DEPARTED
python -m src.radar.airplane list                # a1 is still there, runway R1
python -m src.radar.airplane check-replies       # a1: already on runway R1
```
The last step shows the old "R1" reply is harmless: it just sets the same runway again.

## Viewing the databases
Nice formatting:
```
python -m src.radar.airplane list                # radar.db: every plane (with runway)
python -m src.tower.messaging inbox              # messages.db: one inbox (radar, tower, or command)
```

Raw rows, everything at once (read-only, changes nothing):
```
python -c "import sqlite3; [print(r) for r in sqlite3.connect('file:radar.db?mode=ro', uri=True).execute('SELECT * FROM aircraft')]"
python -c "import sqlite3; [print(r) for r in sqlite3.connect('file:messages.db?mode=ro', uri=True).execute('SELECT * FROM messages')]"
```
- `mode=ro` opens the file read-only: it can't change anything, and if the database doesn't exist yet
  it gives an error instead of creating an empty file.
- The messages one shows every message (sender, recipient, content), not just one inbox.

## Tests
```
pytest tests/radar -v
pytest tests/radar/test_landed_departed.py -v   # just the LANDED/DEPARTED tests
pytest tests/tower -v
```

## Good to know
- IDs must match exactly: `a1` and `A1` are different planes.
- Fresh start: `rm radar.db messages.db` (both git-ignored; recreated automatically).
- After pulling the runway update, delete your old `radar.db` once. It has no `runway_id` column.
- Replying by hand without the helper: `python -m src.tower.messaging send`, with sender `tower`,
  recipient `radar`, and message `{"type": "RUNWAY_ASSIGNED", "aircraft_id": "a1", "runway_id": "R1"}`.
- `python -m src.radar.airplane.demo B45` still works: it creates a plane and prints both databases.
