# Team Command

## R1 Visibility: REQ-OPS-001 and REQ-OPS-002

From the repository root, using Python 3.12:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn src.command.dashboard:app --reload
```

Open `http://localhost:8000/`. Stop the server with Control-C.
On a Mac with Homebrew Python, `/opt/homebrew/bin/python3.12` can be used for the first command.

### What this increment provides

- One page with a square airport schematic, 10 runway boxes, airport coordinates, perimeter, runway count, availability, and timestamps.
- Hard-coded Command demo data in `src/command/airport.py`, following Session 5's first increment. It matches Tower's existing field names and runway count. The last demo runway is unavailable to illustrate both allowed statuses.
- Tower stores perimeter as a single number without specifying a unit. Command shows the value as-is and makes no conversion or geographic-scale claim.
- Timestamps describe demo initialization in UTC. They are not live Tower updates.
- A Command inbox and a form that sends to Tower, reusing Tower's routes and `messages.db`. The page refreshes every five seconds.
- Clear error states when airport data or messaging is unavailable.

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

### Later increment

`get_airport_state()` is the replaceable read boundary. This version does not read Tower's airport database, synchronize different computers, or display Radar aircraft. Live data integration can follow once the shared read interface and deployment are defined.
