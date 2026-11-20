# b-sharp

## Open the Command dashboard

Open a terminal in your local `b-sharp` folder. Python 3.12 must be installed.

Get the latest code from main (save/commit your current work first):

```bash
git fetch origin
git switch main
git pull --ff-only origin main
```

**Windows — PowerShell**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m src.radar.airplane list
.\.venv\Scripts\python.exe -m src.tower.airport answer-requests
.\.venv\Scripts\python.exe -m uvicorn src.command.dashboard:app --port 8000
```

**Mac — Terminal**

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m src.radar.airplane list
python -m src.tower.airport answer-requests
python -m uvicorn src.command.dashboard:app --port 8000
```

Open **http://localhost:8000** and click **Test sound**. Leave that terminal running.

Run Radar/Tower commands in a **second terminal in the same folder**. For example, on Windows:

```powershell
.\.venv\Scripts\python.exe -m src.radar.airplane create
.\.venv\Scripts\python.exe -m src.tower.airport answer-requests
```

On Mac, run `source .venv/bin/activate` in the second terminal and use `python` instead of the Windows Python path.

The dashboard refreshes automatically. **Refresh now** only updates the display; it does not run Tower processing. A full R2 demo also needs the Radar/Tower implementations in the same checkout.
