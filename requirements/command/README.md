# Team Command

## R1 Visibility: REQ-OPS-001 through REQ-OPS-006

From the repository root, using Python 3.12:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn src.command.dashboard:app --reload
```

Open `http://localhost:8000/`. Stop the server with Control-C.
On a Mac with Homebrew Python, `/opt/homebrew/bin/python3.12` can be used for the first command.

### Shared local database

The agreed midterm setup runs all subsystems on one computer. Tower owns `tower.db`;
Command opens it read-only and never creates, seeds, migrates, or changes its tables.
Have Tower initialize its airport through its normal startup flow first. On current
`main`, its existing `python -m src.tower.airport runways` command initializes the
airport when needed. Run Tower from the demo checkout root so it writes the same
`tower.db` that Command reads.

The default airport is `DEMO-001`. To use a different database or airport:

```bash
export COMMAND_TOWER_DB=/absolute/path/to/demo/b-sharp/tower.db
export COMMAND_AIRPORT_ID=DEMO-001
python -m uvicorn src.command.dashboard:app --reload
```

The default airport database path is this checkout's root, even if Command starts
from another directory. Tower's existing message service still resolves
`messages.db` from the working directory, so launch the demo from the root.

### What this increment provides

- One page with a square airport schematic, 10 runway boxes, airport coordinates, perimeter, runway count, availability, and timestamps.
- Recorded Radar aircraft positions around the centered airport schematic. Each marker shows ID, altitude (feet), and latitude / longitude; the list below adds the position timestamp, Radar status, and any matching Tower assignment. Select a marker or record to highlight it. Identical coordinates share a marker that cycles through aircraft when selected.
- A north-up local coordinate plot with a fixed 10 km span. Outside-range aircraft remain in the list. The runway drawing is schematic, not geographically scaled; use **Runway detail** to expand it. Aircraft labels near the airport move beside the drawing with connector lines, or into the extra labels below the map when space is limited, so icons and labels never cover the runways. Coordinates in the records remain exact. No external map service or internet connection is needed.
- Actual airport and runway data from Tower, including aircraft IDs in both the runway cards and schematic. No Command demo airport is substituted when Tower is unavailable.
- Both database contracts are supported: the original layout stores aircraft IDs in `runways`; the new layout uses `runway_assignments`. If the new table exists, it owns aircraft occupancy even when empty, so old aircraft IDs are ignored. The runway's own availability is still respected: an unassigned runway marked `Not Available` is not displayed as free.
- Assignment labels distinguish landing assigned, landed, and takeoff assigned. Legacy data is labeled as having no aircraft phase information. Command displays the stored phase and does not repair or simulate Tower's transitions.
- Tower stores perimeter as a single number without specifying a unit. Command shows the value as-is and makes no conversion or geographic-scale claim.
- Tower's record timestamps are displayed exactly as supplied. `assigned_at` is labeled "Assigned", not "Updated", because the proposed Tower implementation does not refresh it on a phase change. No `Z` is appended to timestamps with an unspecified timezone. A separate `observed_at` value records Command's read time in UTC; a successful read is not proof that the Tower process is running.
- A Command inbox and send form backed by the existing `messages.db`. Sending still uses Tower's `POST /messages`; the browser reads Command's non-consuming `/api/command-messages` history snapshot. It includes both unread `command` and consumed `command-READ` entries, without changing their recipients. The latest 100 are returned and the page shows the latest 12.
- Five-second refreshes with bounded reads and no overlapping refreshes. Airport or Radar failures leave the last snapshot visibly stale, or show an initial unavailable state. Recovery replaces it with the current state. Messaging failures remain independent.

### Aircraft coordinates

Radar owns `radar.db`; Command reads it without changing its schema or records.
Start Radar from the same checkout root. To select another local Radar store, set
`COMMAND_RADAR_DB=/absolute/path/to/radar.db` before starting Command.

Aircraft move on the map only when Radar updates their stored coordinates. A
landing / takeoff request alone does not change their recorded location. An
aircraft at the airport's coordinates uses an offset callout beside the centered
runway drawing so it stays readable; use coordinates around the airport to
demonstrate incoming and outgoing aircraft.
For the default airport center `(40.6413, -73.7781)`, `(40.6650, -73.8000)` is
northwest of the airport and `(40.6200, -73.7500)` is southeast. Create aircraft
through Radar's normal `python -m src.radar.airplane create` flow.

Invalid coordinates are omitted and counted. Radar currently retains aircraft
rows after departure, so Command reads explicit Radar lifecycle reports from
`messages.db` without marking them read. The latest `DEPARTED` report hides that
retained record; a later Radar request or new telemetry makes it visible again.
If lifecycle history is unavailable, stored positions remain visible with a
warning. Empty Tower assignments never imply departure or a runway refusal.

### Completing the integration check

1. Initialize Tower's database in the demo checkout.
2. Start the Command server and verify that all Tower runways appear.
3. Use Radar and Tower's own commands to create an aircraft, request a runway, and process the request. Command should display that aircraft at its assigned runway on the next refresh.
4. With the new assignments schema, verify each phase transition and a departure. Deleting the departed aircraft's assignment should remove its label while leaving the runway visible.
5. Temporarily point `COMMAND_TOWER_DB` to a missing path to check the initial unavailable state. Command must not create that file.

Tests use temporary databases for both schema contracts. No Tower source or tests
are changed. Tower owns assignment phase transitions; Command displays their stored values.

### Verify with Tower's existing terminal utility

In a second terminal, activate the same environment and run from the same repository root:

```bash
python -m src.tower.messaging send
```

Enter `tower` for sender, `command` for recipient, then a message. It appears in the dashboard within five seconds.
Send a reply from the dashboard, then run:

```bash
python -m src.tower.messaging inbox
```

Enter `tower` to see Command's reply. Running from the same root matters because Tower resolves `messages.db` relative to the working directory.

### Automated checks

```bash
python -m pip install pytest
python -m pytest tests/command
bash scripts/validate-requirements.sh command
```

Tests use temporary databases and do not change your local messages. CI installs pytest and runs these checks for Command changes.

### Remaining Tower contracts

`runway_assignments` contains assigned aircraft only. Missing rows do not reveal
whether an aircraft departed, is parked, or was refused a runway. A separate Tower
contract is needed to display no-runway results. Geographic positions come from
Radar and remain separate from the runway schematic. Command polls the databases; it does not
run Tower's request processor or advance the simulation.
