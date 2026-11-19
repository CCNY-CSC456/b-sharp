# Command R2 UI: teammate testing

Run from the b-sharp checkout root. Use Python 3.12. The UI needs the committed Command changes, including src/command/alerts.py; pulling a branch without those changes will not include the alerts panel.

## Windows PowerShell setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

No environment activation or execution-policy change is needed. Open two PowerShell terminals in the same checkout root.

## Test the UI independently

This creates separate rehearsal databases and leaves the checkout's databases alone. Unsafe detection uses real Tower code; the helper supplies simulated Radar movement/acknowledgement and sample queue-conflict messages. It tests Command's UI, not completion of the other teams' workflows.

Terminal 1:

```powershell
$demo = Join-Path $env:TEMP "b-sharp-command-r2-01"
.\.venv\Scripts\python.exe scripts\demo-command-alerts.py --directory "$demo" init
$env:COMMAND_ALERT_SOUND_EVERY = "10"
.\.venv\Scripts\python.exe scripts\demo-command-alerts.py --directory "$demo" serve
```

Open http://127.0.0.1:8010. Sounds are enabled by default; browsers require a click or keypress on the page before audio can play. Click **Test sound** to verify the speaker. That test tone does not advance the incident counter. The toggle should say **Mute alert sounds**.

Terminal 2:

```powershell
$demo = Join-Path $env:TEMP "b-sharp-command-r2-01"
.\.venv\Scripts\python.exe scripts\demo-command-alerts.py --directory "$demo" unsafe
```

Show the severity-1 red alert and both aircraft highlighted. Try **View Aircraft** and **Contact Tower**; Contact Tower prepares a draft for manual sending and preserves an existing draft.

Run each remaining command separately and click **Refresh now** between steps:

```powershell
.\.venv\Scripts\python.exe scripts\demo-command-alerts.py --directory "$demo" conflict
.\.venv\Scripts\python.exe scripts\demo-command-alerts.py --directory "$demo" resolve
.\.venv\Scripts\python.exe scripts\demo-command-alerts.py --directory "$demo" resolve-conflict
```

Expected sequence:

1. Severity-2 conflict appears below severity 1; B2 stays red because unsafe separation has higher severity.
2. Unsafe incident clears and the simulated Radar position changes. A1 returns to normal; B2 becomes yellow because its conflict remains.
3. Conflict clears and B2 returns to normal. Recently cleared lists the completed incidents.

For the default ten-incident sound check, reload the page, click **Test sound**, and verify 0/10. Then run:

```powershell
.\.venv\Scripts\python.exe scripts\demo-command-alerts.py --directory "$demo" burst
```

Ten distinct sample conflicts should cause one automatic tone. Refreshing again does not replay the sound. To hear a tone for every new incident instead, restart Terminal 1 with COMMAND_ALERT_SOUND_EVERY set to "1", then reload the page.

If init reports existing databases, choose a new suffix in BOTH terminals. Use a new directory to repeat the fixed-ID opening/resolution walkthrough from scratch. Historical incidents load silently. Muting does not queue sounds for later playback.

## Use the team's real workflow

Both terminals must use the same checkout and databases. Stop the rehearsal server first if switching demos. On Windows:

```powershell
.\.venv\Scripts\python.exe -m src.radar.airplane list
.\.venv\Scripts\python.exe -m src.tower.airport answer-requests
$env:COMMAND_ALERT_SOUND_EVERY = "10"
.\.venv\Scripts\python.exe -m uvicorn src.command.dashboard:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. Use the real Radar/Tower commands in the second terminal. Command refreshes every five seconds; **Refresh now** only reads data and does not process Tower or move aircraft.

## Mac equivalents

From the checkout root:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
DEMO="${TMPDIR:-/tmp}/b-sharp-command-r2-01"
python scripts/demo-command-alerts.py --directory "$DEMO" init
COMMAND_ALERT_SOUND_EVERY=10 python scripts/demo-command-alerts.py --directory "$DEMO" serve
```

In a second terminal, activate the same environment and set the same DEMO value. Use `python scripts/demo-command-alerts.py --directory "$DEMO" unsafe` and the other actions above. For the live workflow, initialize Radar/Tower as above using `python`, then run `COMMAND_ALERT_SOUND_EVERY=10 python -m uvicorn src.command.dashboard:app --port 8000`.

## Message contract and integration status

Reviewed November 19 at main `3a6336d`, Radar branch RMP_R2 `4e7b0d7`, and Tower branch IL_SCHEDULER `125778b`.

- Command reads alert messages whose sender is tower and recipient is command (or command-READ). The content is JSON text.
- UNSAFE_SEPARATION / UNSAFE_SEPARATION_RESOLVED use separation_id and aircraft_id. Radar's new check-separation command is compatible: it updates Radar coordinates, acknowledges Tower, and sends fresh aircraft information. Once that Radar work is integrated, the real order is Tower answer-requests → Radar check-separation → Tower answer-requests. Main alone does not yet include that Radar command.
- Queue conflicts need CONFLICT / CONFLICT_RESOLVED from Tower with a stable conflict_id. Radar currently sends CONFLICT without an ID; Tower's scheduler expects PRIORITY_LOW/MEDIUM/HIGH and does not yet produce Command's conflict messages. Tower has since proposed Command's matching contract: CONFLICT carries conflict_id, severity 2, aircraft_id, reason and timestamp; CONFLICT_RESOLVED carries the same conflict_id/aircraft_id plus reason, queue_position and timestamp. The producer still needs integration; Command must not guess that Radar messages are Tower decisions.
- Tower's added consumed/kind columns do not change Command's alert query. Upgrading an existing messages.db to that schema remains a Tower migration issue; a fresh database works with the new schema.
- Aircraft map/database migration and latency enforcement remain deferred. Command does not execute queue decisions or move aircraft itself.

Tower's proposed queue incident (producer still in progress):

```json
{"type":"CONFLICT","conflict_id":"fuel-A1-1","severity":2,"aircraft_id":"A1","reason":"Low on gas (non-emergency)","timestamp":"2026-11-19T14:00:00"}
```

Resolution:

```json
{"type":"CONFLICT_RESOLVED","conflict_id":"fuel-A1-1","aircraft_id":"A1","reason":"Low on gas (non-emergency)","queue_position":1,"timestamp":"2026-11-19T14:01:00"}
```

The extra resolution fields are accepted; the full payload is visible in Tower messages. A new incident needs a new ID. Repeated reports update one incident. Resolving one incident leaves any other active incident for that aircraft visible. Sound counts distinct new incident openings after the initial page snapshot; the default threshold is 10, configurable with COMMAND_ALERT_SOUND_EVERY (1–1000; invalid settings fall back to 10).

## Developer checks

```bash
python -m pytest tests -q
bash scripts/validate-requirements.sh command
```

For browser checks, use an environment with Playwright installed and run `node tests/command/browser_alerts.cjs`. BROWSER_EXECUTABLE may point to a local Chrome executable. These checks use controlled API responses, do not touch live databases, and save screenshots in the system temporary directory. On Windows, the Bash validation command requires Git Bash; it is not needed to start the UI.
