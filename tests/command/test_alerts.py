"""REQ-OPS-007: real Tower events, repeat safety and alert history projection."""
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient
from src.command.alerts import get_alert_snapshot, project_alerts
from src.command.dashboard import app
from src.tower.messaging import db
from src.tower.airport.airport_repo import create_tables, create_airport
from src.tower.airport.separation import check_separation


def opening(id=1, **extra):
    return dict(type='UNSAFE_SEPARATION', separation_id=id, aircraft_id='B2', other_aircraft_id='A1',
                move_to_latitude=40.81, move_to_longitude=-73.8, timestamp='2026-11-19T10:00:00', **extra)


def projection(*events):
    return project_alerts([(i, json.dumps(e)) for i, e in enumerate(events, 1)])


def resolution(id=1):
    return dict(type='UNSAFE_SEPARATION_RESOLVED', separation_id=id, aircraft_id='B2')


def test_waiting_move_and_repeats_share_an_incident():
    waiting = {**opening(), 'move_to_latitude': None, 'move_to_longitude': None}
    assert projection(waiting)['active'][0]['status'] == 'waiting'
    state = projection(waiting, opening(), opening())
    assert state['opened_count'] == 1
    assert len(state['active']) == 1
    assert state['active'][0]['status'] == 'instructed'


def test_severity_order_and_independent_resolution():
    conflict = dict(type='CONFLICT', conflict_id='fuel-1', aircraft_id='B2', reason='Low on gas')
    state = projection(conflict, opening(), opening(2))
    assert [a['severity'] for a in state['active']] == [1, 1, 2]
    after = projection(conflict, opening(), opening(2), resolution())
    assert [a['key'] for a in after['active']] == ['separation:2', 'conflict:fuel-1']
    assert after['recent'][0]['status'] == 'resolved'


def test_repeated_opening_after_resolution_does_not_reopen_old_id():
    state = projection(opening(), resolution(), opening(), opening(2))
    assert [a['key'] for a in state['active']] == ['separation:2']
    assert state['opened_count'] == 2


def test_unknown_or_wrong_aircraft_resolution_cannot_clear_incident():
    state = projection(opening(), resolution(99), {**resolution(), 'aircraft_id': 'WRONG'})
    assert len(state['active']) == 1


def test_conflict_requires_id_and_unmatched_resolution_cannot_clear_it():
    c = dict(type='CONFLICT', conflict_id='delay-1', aircraft_id='A1', reason='Late by 2 hours')
    state = projection(c, {**c, 'type': 'CONFLICT_RESOLVED', 'conflict_id': None})
    assert len(state['active']) == 1
    assert state['ignored_alert_count'] == 1
    assert projection({**c, 'conflict_id': None})['active'] == []
    assert projection(c, {**c, 'type': 'CONFLICT_RESOLVED'})['active'] == []


@pytest.mark.parametrize('bad', [None, [], {'type': []}, {'type': 'UNSAFE_SEPARATION'},
    {**opening(), 'separation_id': []}, {**opening(), 'aircraft_id': {}},
    {**opening(), 'separation_id': True}])
def test_malformed_events_do_not_break_good_alerts(bad):
    assert len(projection(bad, opening())['active']) == 1


def test_null_or_invalid_target_remains_waiting():
    assert projection({**opening(), 'move_to_latitude': float('nan')})['active'][0]['status'] == 'waiting'


@pytest.fixture
def message_db(tmp_path, monkeypatch):
    path = tmp_path / 'messages.db'
    monkeypatch.setattr(db, 'DB', str(path))
    db.init_db()
    return path


def test_only_tower_to_command_events_and_full_history_are_used(message_db):
    db.save_message('radar', 'tower', json.dumps(opening(99)))
    db.save_message('tower', 'radar', json.dumps(opening(98)))
    db.save_message('tower', 'command-READ', json.dumps(opening()))
    for n in range(150):
        db.save_message('tower', 'command', json.dumps({'type': 'AIRCRAFT_POSITION', 'aircraft_id': str(n)}))
    before = message_db.read_bytes()
    assert [a['key'] for a in get_alert_snapshot()['active']] == ['separation:1']
    assert get_alert_snapshot()['opened_count'] == 1
    assert message_db.read_bytes() == before


def test_real_tower_separation_open_and_resolved(message_db):
    conn = sqlite3.connect(':memory:')
    create_tables(conn); create_airport(conn, 'DEMO-001', 21000, 40.6413, -73.7781)
    for name, lat in [('A1', 40.70), ('B2', 40.75)]:
        db.save_message('radar', 'tower', json.dumps(dict(type='AIRCRAFT_INFO', aircraft_id=name,
            latitude=lat, longitude=-73.8, altitude=2000, status='Landing', timestamp='2026-11-19T10:00:00')))
    check_separation(conn, 'DEMO-001')
    state = get_alert_snapshot()
    assert state['active'][0]['aircraft_ids'] == ['B2', 'A1']
    assert state['active'][0]['severity'] == 1
    db.save_message('radar', 'tower', json.dumps(resolution()))
    check_separation(conn, 'DEMO-001')
    assert get_alert_snapshot()['active'] == []
    assert len(get_alert_snapshot()['recent']) == 1
    conn.close()


def test_api_and_configured_sound_threshold(message_db, monkeypatch):
    monkeypatch.setenv('COMMAND_ALERT_SOUND_EVERY', '3')
    db.save_message('tower', 'command', json.dumps(opening()))
    with TestClient(app) as client:
        result = client.get('/api/alerts')
        assert result.status_code == 200
        assert result.json()['sound_every'] == 3
        assert len(result.json()['active']) == 1


@pytest.mark.parametrize('value', ['0', '-1', 'bad', '1001'])
def test_invalid_sound_setting_uses_default(message_db, monkeypatch, value):
    monkeypatch.setenv('COMMAND_ALERT_SOUND_EVERY', value)
    assert get_alert_snapshot()['sound_every'] == 10


def test_missing_database_returns_503_without_creating_it(tmp_path, monkeypatch):
    missing = tmp_path / 'missing.db'
    with TestClient(app) as client:
        monkeypatch.setattr(db, 'DB', str(missing))
        assert client.get('/api/alerts').status_code == 503
        assert client.get('/').status_code == 200
    assert not missing.exists()


def test_tower_queue_contract_with_resolution_details(message_db):
    """REQ-OPS-007: Tower's proposed payload clears only its matching incident."""
    reported = dict(type='CONFLICT', conflict_id='fuel-A1-1', severity=2,
                    aircraft_id='A1', reason='Low on gas', timestamp='2026-11-19T14:00:00')
    resolved = dict(type='CONFLICT_RESOLVED', conflict_id='fuel-A1-1', aircraft_id='A1',
                    reason='Low on gas', queue_position=1, timestamp='2026-11-19T14:01:00')
    with TestClient(app) as client:
        for payload in [reported, reported, opening()]:
            db.save_message('tower', 'command', json.dumps(payload))
        before = client.get('/api/alerts').json()
        assert [item['severity'] for item in before['active']] == [1, 2]
        assert before['opened_count'] == 2
        db.save_message('tower', 'command', json.dumps(resolved))
        after = client.get('/api/alerts').json()
        assert [item['key'] for item in after['active']] == ['separation:1']
        assert after['recent'][0]['key'] == 'conflict:fuel-A1-1'
        assert after['recent'][0]['status'] == 'resolved'
        assert after['recent'][0]['updated_at'] == resolved['timestamp']
        assert after['opened_count'] == 2
