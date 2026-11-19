"""Isolated R2 rehearsal. Uses only the directory explicitly supplied; never the checkout DBs.

The unsafe/resolved scenarios call real Tower processing. Conflict/burst messages
are sample Tower events for UI rehearsal until Tower's severity-2 producer is merged.
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.tower.messaging import db
from src.tower.airport.airport_repo import create_tables, create_airport
from src.tower.airport.separation import check_separation
from src.radar.airplane.aircraft_repo import init_db as init_radar

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--directory', type=Path, required=True)
parser.add_argument('action', choices=['init', 'serve', 'unsafe', 'resolve', 'conflict', 'resolve-conflict', 'burst'])
parser.add_argument('--port', type=int, default=8010)
args = parser.parse_args()
folder = args.directory.expanduser().resolve()
repo = Path(__file__).resolve().parents[1]
if folder == repo:
    parser.error('Use a separate rehearsal directory, not the repository root.')
db.DB = str(folder / 'messages.db')
now = datetime.now().isoformat(timespec='seconds')
def send(sender, recipient, payload):
    db.save_message(sender, recipient, json.dumps(payload))

if args.action == 'init':
    if any((folder / name).exists() for name in ['messages.db', 'tower.db', 'radar.db']):
        parser.error('Rehearsal databases already exist. Use a new directory to start fresh.')
    folder.mkdir(parents=True, exist_ok=True)
    db.init_db()
    with sqlite3.connect(folder / 'tower.db') as conn:
        create_tables(conn); create_airport(conn, 'DEMO-001', 21000, 40.6413, -73.7781)
    conn = init_radar(str(folder / 'radar.db'))
    for ident, lat, lon in [('A1', 40.70, -73.80), ('B2', 40.75, -73.82)]:
        conn.execute('INSERT INTO aircraft VALUES (?, ?, ?, ?, ?, ?, ?)', (ident, lat, lon, 2000, 'Landing', now, None))
        send('radar', 'tower', dict(type='AIRCRAFT_INFO', aircraft_id=ident, latitude=lat, longitude=lon,
                                  altitude=2000, status='Landing', timestamp=now))
    conn.commit(); conn.close()
    print(f'Rehearsal initialized in {folder}. No checkout databases were changed.')
else:
    if not all((folder / name).exists() for name in ['messages.db', 'tower.db', 'radar.db']):
        parser.error('Run init for this separate directory first.')
    if args.action == 'serve':
        import uvicorn
        os.environ['COMMAND_TOWER_DB'] = str(folder / 'tower.db')
        os.environ['COMMAND_RADAR_DB'] = str(folder / 'radar.db')
        os.environ['COMMAND_AIRPORT_ID'] = 'DEMO-001'
        uvicorn.run('src.command.dashboard:app', host='127.0.0.1', port=args.port)
    elif args.action in ('unsafe', 'resolve'):
        with sqlite3.connect(folder / 'tower.db') as conn:
            if args.action == 'resolve':
                for sep, aircraft, lat, lon in conn.execute("SELECT separation_id, aircraft_id, move_to_latitude, move_to_longitude FROM separations WHERE status = 'OPEN'").fetchall():
                    # Simulated Radar acknowledgement and actual stored position, for this rehearsal only.
                    with sqlite3.connect(folder / 'radar.db') as radar:
                        radar.execute('UPDATE aircraft SET latitude=?, longitude=?, timestamp=? WHERE aircraft_id=?', (lat, lon, now, aircraft))
                    send('radar', 'tower', dict(type='UNSAFE_SEPARATION_RESOLVED', separation_id=sep, aircraft_id=aircraft, timestamp=now))
            print(json.dumps(check_separation(conn, 'DEMO-001'), indent=2))
    else:
        count = 10 if args.action == 'burst' else 1
        for n in range(count):
            ident = f'rehearsal-{now}-{n}' if args.action == 'burst' else 'rehearsal-fuel'
            send('tower', 'command', dict(type='CONFLICT_RESOLVED' if args.action == 'resolve-conflict' else 'CONFLICT',
                                         conflict_id=ident, aircraft_id='B2', reason='Low on gas (non-emergency)', timestamp=now))
        print(f'Sent {count} sample Tower event(s) to the isolated rehearsal database.')
