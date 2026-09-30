# Messaging (REQ-TOW-002)

A barebones server that lets radar, tower, and command send messages to each other.
FastAPI + SQLite, no frontend. A message has 3 fields: `sender`, `recipient`, `content`.

## Endpoints
| Endpoint | What it does |
|---|---|
| `POST /messages` | Send a message (JSON body with sender, recipient, content) |
| `GET /messages?recipient=tower` | Get every message sent to tower |

## Setup (once per computer)
From the repo root:
```
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt pytest
```

## Run the tests (no server needed)
```
pytest tests/tower -v
```

## Run it for real
**Terminal 1**, start the server and leave it running:
```
uvicorn src.tower.messaging.main:app --reload
```

**Terminal 2**, try it one of these ways:
- **Browser (easiest):** open http://localhost:8000/docs and use "Try it out"
- **Demo script:** `bash scripts/test-messaging.sh` (Mac/Linux, or Git Bash on Windows)
- **Curl by hand:**
```
  curl -X POST localhost:8000/messages -H "Content-Type: application/json" -d '{"sender":"radar","recipient":"tower","content":"AA123 at 5000ft"}'
  curl "localhost:8000/messages?recipient=tower"
```

Ctrl+C in Terminal 1 stops the server. Messages are saved in `messages.db` (git-ignored).

## Files
| File | Job |
|---|---|
| `models.py` | Defines what a message is |
| `db.py` | The only file that touches the database |
| `send.py` | `POST /messages` |
| `inbox.py` | `GET /messages` |
| `main.py` | Creates the server and plugs in the endpoints |