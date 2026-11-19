# REQ-TOW-013
# Automated tests for unsafe separation. CI runs these with: pytest tests/tower
# The first half tests the rules on their own; the second half runs tower on a throwaway messages.db.

import itertools
import json
import random
import sqlite3

import pytest

from src.radar.airplane.runway_requests import check_tower_replies
from src.tower.airport import __main__ as cli
from src.tower.airport.airport_repo import create_airport, create_tables, get_aircraft_positions, get_separations
from src.tower.airport.runway_requests import answer_requests
from src.tower.airport.separation import (
    MOVE_RINGS, SEPARATION_DEGREES, SEPARATION_FEET, UNSAFE_SEPARATION, UNSAFE_SEPARATION_RESOLVED,
    build_positions, check_separation, choose_mover, find_spot, too_close,
)
from src.tower.messaging import db as tower_db


def plane(aircraft_id, latitude, longitude, altitude=2000.0, requested_at=None):
    return {"aircraft_id": aircraft_id, "latitude": latitude, "longitude": longitude, "altitude": altitude,
            "status": "Landing", "requested_at": requested_at}


# --- the limits ---

def test_limits_are_what_was_agreed():
    assert (SEPARATION_DEGREES, SEPARATION_FEET) == (0.10, 1000)
    assert MOVE_RINGS[0] > SEPARATION_DEGREES  # a moved plane lands past the limit, not on it


def test_too_close_needs_all_three():
    a = plane("A1", 40.70, -73.80, 2000)
    assert too_close(a, plane("B2", 40.75, -73.82, 2500))
    assert not too_close(a, plane("B2", 40.85, -73.82, 2500))   # latitude far enough
    assert not too_close(a, plane("B2", 40.75, -73.95, 2500))   # longitude far enough
    assert not too_close(a, plane("B2", 40.75, -73.82, 3500))   # altitude far enough


def test_exactly_at_the_limit_is_safe():
    a = plane("A1", 40.70, -73.80, 2000)
    assert not too_close(a, plane("B2", 40.80, -73.80, 2000))   # 0.10 degrees (40.8 - 40.7 is 0.0999... in floats)
    assert not too_close(a, plane("B2", 40.70, -73.90, 2000))
    assert not too_close(a, plane("B2", 40.70, -73.80, 3000))   # exactly 1000 ft
    assert too_close(a, plane("B2", 40.70, -73.80, 2999))


# --- where the plane is sent ---

def test_the_agreed_example():
    a1, b2 = plane("A1", 40.70, -73.80), plane("B2", 40.75, -73.82, 2500)
    assert find_spot(b2, a1, {"A1": a1, "B2": b2}) == (40.81, -73.80)


def test_spot_skips_a_third_plane():
    a1, b2 = plane("A1", 40.70, -73.80), plane("B2", 40.75, -73.82, 2500)
    c3 = plane("C3", 40.81, -73.80, 2500)  # sitting on the best spot (north of A1)
    assert find_spot(b2, a1, {"A1": a1, "B2": b2, "C3": c3}) == (40.70, -73.91)  # next closest: west


def test_a_plane_at_another_altitude_does_not_block_a_spot():
    a1, b2 = plane("A1", 40.70, -73.80), plane("B2", 40.75, -73.82, 2500)
    c3 = plane("C3", 40.81, -73.80, 9000)
    assert find_spot(b2, a1, {"A1": a1, "B2": b2, "C3": c3}) == (40.81, -73.80)


def spots_around(other, ring):
    return [(round(other["latitude"] + la * ring, 4), round(other["longitude"] + lo * ring, 4))
            for la, lo in [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]]


def test_tries_twice_as_far_when_all_8_are_taken():
    a1, b2 = plane("A1", 40.70, -73.80), plane("B2", 40.75, -73.82)
    planes = {"A1": a1, "B2": b2}
    for n, (lat, lon) in enumerate(spots_around(a1, MOVE_RINGS[0])):
        planes[f"X{n}"] = plane(f"X{n}", lat, lon)
    spot = find_spot(b2, a1, planes)
    assert spot in spots_around(a1, MOVE_RINGS[1])
    assert not any(too_close({**b2, "latitude": spot[0], "longitude": spot[1]}, p)
                   for k, p in planes.items() if k != "B2")


def test_no_spot_when_everything_is_taken():
    a1, b2 = plane("A1", 40.70, -73.80), plane("B2", 40.75, -73.82)
    planes = {"A1": a1, "B2": b2}
    for ring in MOVE_RINGS:
        for n, (lat, lon) in enumerate(spots_around(a1, ring)):
            planes[f"X{ring}{n}"] = plane(f"X{ring}{n}", lat, lon)
    assert find_spot(b2, a1, planes) is None


def test_spot_is_never_too_close_to_anyone_random_skies():
    rng = random.Random(456)  # fixed seed: the same "random" skies every run
    for _ in range(300):
        planes = {f"P{n}": plane(f"P{n}", 40.7 + rng.uniform(-0.2, 0.2), -73.8 + rng.uniform(-0.2, 0.2),
                                 rng.choice([1000, 1500, 2000, 2500]))
                  for n in range(6)}
        for a, b in itertools.combinations(sorted(planes), 2):
            if too_close(planes[a], planes[b]):
                spot = find_spot(planes[b], planes[a], planes)
                if spot is not None:
                    moved = {**planes[b], "latitude": spot[0], "longitude": spot[1]}
                    assert not any(too_close(moved, p) for k, p in planes.items() if k != b)


# --- who moves ---

def no_runways(_aircraft_id):
    return False


def test_later_request_moves():
    a, b = plane("A1", 0, 0, requested_at="2026-11-15T10:00:00"), plane("B2", 0, 0, requested_at="2026-11-15T10:05:00")
    assert choose_mover(a, b, set(), no_runways)["aircraft_id"] == "B2"
    assert choose_mover(b, a, set(), no_runways)["aircraft_id"] == "B2"  # order passed in doesn't matter


def test_never_asked_counts_as_later():
    a, b = plane("A1", 0, 0), plane("B2", 0, 0, requested_at="2026-11-15T10:05:00")
    assert choose_mover(a, b, set(), no_runways)["aircraft_id"] == "A1"


def test_tie_goes_by_aircraft_id():
    assert choose_mover(plane("A1", 0, 0), plane("B2", 0, 0), set(), no_runways)["aircraft_id"] == "B2"


def test_plane_holding_a_runway_is_not_moved():
    a, b = plane("A1", 0, 0), plane("B2", 0, 0, requested_at="2026-11-15T10:05:00")
    assert choose_mover(a, b, set(), lambda aircraft_id: aircraft_id == "A1")["aircraft_id"] == "B2"


def test_plane_already_being_moved_is_not_picked_again():
    a, b = plane("A1", 0, 0), plane("B2", 0, 0)
    assert choose_mover(a, b, {"B2"}, no_runways)["aircraft_id"] == "A1"
    assert choose_mover(a, b, {"A1", "B2"}, no_runways) is None


# --- reading radar's messages into positions ---

def msg(content, sender="radar"):
    return {"sender": sender, "recipient": "tower", "content": json.dumps(content)}


def info(aircraft_id, latitude, longitude, altitude=2000.0, status="Landing", timestamp="2026-11-15T10:00:00"):
    return {"type": "AIRCRAFT_INFO", "aircraft_id": aircraft_id, "latitude": latitude, "longitude": longitude,
            "altitude": altitude, "status": status, "timestamp": timestamp, "runway_id": None}


def event(kind, aircraft_id, timestamp="2026-11-15T10:01:00"):
    return {"type": kind, "aircraft_id": aircraft_id, "timestamp": timestamp}


def by_id(positions):
    return {p["aircraft_id"]: p for p in positions}


def test_positions_follow_radar():
    positions = by_id(build_positions([
        msg({k: v for k, v in info("A1", 40.7, -73.8).items() if k != "type"}),  # radar's create message
        msg(info("A1", 40.75, -73.85, 3000)),
        msg(event("REQUEST_LANDING", "A1")),
    ], {}))
    assert positions["A1"]["latitude"] == 40.75 and positions["A1"]["altitude"] == 3000
    assert positions["A1"]["requested_at"] == "2026-11-15T10:01:00" and not positions["A1"]["on_ground"]


def test_landed_plane_is_on_the_ground_even_with_altitude():
    positions = by_id(build_positions([msg(info("A1", 40.7, -73.8, 2000)), msg(event("LANDED", "A1")),
                                       msg(info("A1", 40.7, -73.8, 2000))], {}))
    assert positions["A1"]["on_ground"]


def test_parked_or_zero_altitude_is_on_the_ground():
    positions = by_id(build_positions([msg(info("A1", 40.7, -73.8, 0, "Landing")),
                                       msg(info("B2", 40.7, -73.8, 500, "Parked")),
                                       msg(info("C3", 40.7, -73.8, 500)), msg(event("PARKED", "C3"))], {}))
    assert all(p["on_ground"] for p in positions.values())


def test_departed_plane_is_dropped_and_can_come_back():
    inbox = [msg(info("A1", 40.7, -73.8)), msg(event("LANDED", "A1")), msg(event("DEPARTED", "A1"))]
    assert build_positions(inbox, {}) == []
    positions = by_id(build_positions(inbox + [msg(info("A1", 41.0, -74.0))], {}))
    assert not positions["A1"]["on_ground"] and positions["A1"]["requested_at"] is None


def test_resolved_puts_the_plane_where_tower_sent_it_until_radar_says_otherwise():
    moves = {7: ("B2", 40.81, -73.80)}
    resolved = msg({"type": UNSAFE_SEPARATION_RESOLVED, "separation_id": 7, "aircraft_id": "B2",
                    "timestamp": "2026-11-15T10:02:00"})
    positions = by_id(build_positions([msg(info("B2", 40.75, -73.82)), resolved], moves))
    assert (positions["B2"]["latitude"], positions["B2"]["longitude"]) == (40.81, -73.80)
    positions = by_id(build_positions([msg(info("B2", 40.75, -73.82)), resolved, msg(info("B2", 41.0, -74.0))], moves))
    assert positions["B2"]["latitude"] == 41.0


def test_bad_positions_and_other_senders_are_ignored():
    positions = build_positions([msg(info("A1", "north", -73.8)), msg(info("B2", 40.7, -73.8, None)),
                                 msg(info("C3", float("nan"), -73.8)), msg(info("D4", 40.7, -73.8), sender="command"),
                                 msg({"type": UNSAFE_SEPARATION_RESOLVED, "separation_id": "7", "aircraft_id": "B2"})],
                                {7: ("B2", 1.0, 1.0)})
    assert positions == []


# --- whole runs (real messaging on a throwaway messages.db) ---

@pytest.fixture(autouse=True)
def throwaway_messages(tmp_path, monkeypatch):
    monkeypatch.setattr(tower_db, "DB", str(tmp_path / "messages.db"))
    tower_db.init_db()


@pytest.fixture
def tower():
    conn = sqlite3.connect(":memory:")
    create_tables(conn)
    create_airport(conn, "JFK", 21000, 40.6413, -73.7781)
    return conn


def radar_sends(content):
    tower_db.save_message("radar", "tower", json.dumps(content))


def radar_resolves(separation_id, aircraft_id):
    radar_sends({"type": UNSAFE_SEPARATION_RESOLVED, "separation_id": separation_id, "aircraft_id": aircraft_id,
                 "timestamp": "2026-11-15T10:03:00"})


def inbox(recipient, kind=None):
    messages = [json.loads(m["content"]) for m in tower_db.get_messages(recipient)]
    return [m for m in messages if kind is None or m["type"].startswith("UNSAFE")]


def run(conn):
    return check_separation(conn, "JFK")


def statuses(conn):
    return [(e["separation_id"], e["aircraft_id"], e["other_aircraft_id"], e["status"]) for e in get_separations(conn, "JFK")]


def two_close_planes():
    radar_sends(info("A1", 40.70, -73.80, 2000))
    radar_sends(info("B2", 40.75, -73.82, 2500))


def strip_time(message):
    return {k: v for k, v in message.items() if k != "timestamp"}


def test_exact_messages_to_radar_and_command(tower):
    two_close_planes()
    run(tower)
    [to_radar] = inbox("radar", UNSAFE_SEPARATION)
    [to_command] = inbox("command", UNSAFE_SEPARATION)
    assert list(to_radar) == ["type", "separation_id", "aircraft_id", "other_aircraft_id",
                              "move_to_latitude", "move_to_longitude", "timestamp"]
    assert strip_time(to_radar) == {"type": UNSAFE_SEPARATION, "separation_id": 1, "aircraft_id": "B2",
                                    "other_aircraft_id": "A1", "move_to_latitude": 40.81, "move_to_longitude": -73.80}
    assert list(to_command) == ["type", "separation_id", "severity", "aircraft_id", "other_aircraft_id",
                                "move_to_latitude", "move_to_longitude", "timestamp"]
    assert to_command == {**to_radar, "severity": 1}  # same message, same timestamp, plus severity
    assert statuses(tower) == [(1, "B2", "A1", "OPEN")]


def test_nothing_is_resent_while_waiting_for_radar(tower):
    two_close_planes()
    run(tower)
    assert run(tower) == [] and run(tower) == []
    assert len(inbox("radar", UNSAFE_SEPARATION)) == 1 and len(inbox("command", UNSAFE_SEPARATION)) == 1


def test_radar_resolves_and_tower_trusts_it(tower):
    two_close_planes()
    run(tower)
    radar_resolves(1, "B2")  # no new AIRCRAFT_INFO: tower still trusts radar moved it
    [changed] = run(tower)
    assert changed["status"] == "RESOLVED"
    assert strip_time(inbox("command", UNSAFE_SEPARATION)[-1]) == {
        "type": UNSAFE_SEPARATION_RESOLVED, "separation_id": 1, "severity": 1, "aircraft_id": "B2",
        "other_aircraft_id": "A1"}
    assert run(tower) == []  # not resolved twice, and the pair isn't flagged again
    stored = {p["aircraft_id"]: p for p in get_aircraft_positions(tower, "JFK")}
    assert (stored["B2"]["latitude"], stored["B2"]["longitude"]) == (40.81, -73.80)


def test_wrong_or_unknown_resolutions_are_ignored(tower):
    two_close_planes()
    run(tower)
    radar_resolves(1, "A1")   # A1 wasn't the plane told to move
    radar_resolves(99, "B2")  # no such event
    assert run(tower) == []
    assert statuses(tower) == [(1, "B2", "A1", "OPEN")]


def test_planes_on_the_ground_are_ignored(tower):
    radar_sends(info("A1", 40.70, -73.80, 0, "Parked"))
    radar_sends(info("B2", 40.70, -73.80, 0, "Parked"))
    radar_sends(info("C3", 40.70, -73.80, 2000))
    radar_sends(event("LANDED", "C3"))
    assert run(tower) == [] and inbox("radar") == [] and inbox("command") == []


def test_plane_that_lands_first_cancels_the_event(tower):
    two_close_planes()
    run(tower)
    radar_sends(event("LANDED", "A1", "2026-11-15T10:05:00"))
    [changed] = run(tower)
    assert changed["status"] == "CANCELLED"
    assert inbox("command", UNSAFE_SEPARATION)[-1]["type"] == UNSAFE_SEPARATION_RESOLVED
    radar_resolves(1, "B2")  # radar answering late changes nothing
    assert run(tower) == []


def test_plane_that_departs_cancels_the_event(tower):
    two_close_planes()
    run(tower)
    radar_sends(event("DEPARTED", "B2", "2026-11-15T10:05:00"))
    assert [e["status"] for e in run(tower)] == ["CANCELLED"]


def block_every_spot_around(target, prefix="X"):
    names = []
    for ring in MOVE_RINGS:
        for n, (lat, lon) in enumerate(spots_around(target, ring)):
            names.append(f"{prefix}{int(ring * 100)}{n}")
            radar_sends(info(names[-1], lat, lon, 2500))
    return names


def test_no_clear_spot_waits_then_sends_once_one_opens(tower):
    a1 = plane("A1", 40.70, -73.80, 2000)
    radar_sends(info("A1", 40.70, -73.80, 2000, timestamp="2026-11-15T09:00:00"))
    radar_sends(event("REQUEST_LANDING", "A1", "2026-11-15T09:00:00"))
    blockers = block_every_spot_around(a1)
    for name in blockers:  # the blockers asked before B2, so B2 is always the one that moves
        radar_sends(event("REQUEST_LANDING", name, "2026-11-15T09:30:00"))
    radar_sends(info("B2", 40.75, -73.82, 2500))
    radar_sends(event("REQUEST_LANDING", "B2", "2026-11-15T10:00:00"))
    run(tower)
    waiting = [e for e in get_separations(tower, "JFK") if e["aircraft_id"] == "B2"]
    assert [e["status"] for e in waiting] == ["WAITING"]
    assert not any(m["aircraft_id"] == "B2" for m in inbox("radar", UNSAFE_SEPARATION))  # radar not told yet
    alert = [m for m in inbox("command", UNSAFE_SEPARATION) if m["aircraft_id"] == "B2"]
    assert alert[0]["move_to_latitude"] is None and alert[0]["move_to_longitude"] is None
    sep = waiting[0]["separation_id"]

    events_before = get_separations(tower, "JFK")
    assert run(tower) == []  # still blocked: no new event (A1 isn't picked instead) and nothing resent
    assert get_separations(tower, "JFK") == events_before

    radar_sends(event("DEPARTED", "X110", "2026-11-15T10:10:00"))  # the plane north of A1 leaves
    run(tower)
    to_radar = [m for m in inbox("radar", UNSAFE_SEPARATION) if m["separation_id"] == sep]
    assert len(to_radar) == 1 and (to_radar[0]["move_to_latitude"], to_radar[0]["move_to_longitude"]) == (40.81, -73.80)
    to_command = [m for m in inbox("command", UNSAFE_SEPARATION) if m.get("separation_id") == sep]
    assert to_command[-1]["move_to_latitude"] == 40.81  # command gets the spot too, same separation_id
    assert [e["status"] for e in get_separations(tower, "JFK") if e["separation_id"] == sep] == ["OPEN"]


def test_waiting_ends_if_the_planes_drift_apart(tower):
    a1 = plane("A1", 40.70, -73.80, 2000)
    radar_sends(info("A1", 40.70, -73.80, 2000))
    radar_sends(event("REQUEST_LANDING", "A1", "2026-11-15T09:00:00"))
    for name in block_every_spot_around(a1):
        radar_sends(event("REQUEST_LANDING", name, "2026-11-15T09:30:00"))
    radar_sends(info("B2", 40.75, -73.82, 2500))
    radar_sends(event("REQUEST_LANDING", "B2", "2026-11-15T10:00:00"))
    run(tower)
    radar_sends(info("B2", 40.75, -73.82, 9000, timestamp="2026-11-15T10:05:00"))  # radar climbs B2 on its own
    changed = [e for e in run(tower) if e["aircraft_id"] == "B2"]
    assert [e["status"] for e in changed] == ["RESOLVED"]


def effective_positions(conn):
    """Where every airborne plane will be once radar carries out every open move."""
    planes = {p["aircraft_id"]: p for p in get_aircraft_positions(conn, "JFK") if not p["on_ground"]}
    for e in get_separations(conn, "JFK"):
        if e["status"] == "OPEN":
            planes[e["aircraft_id"]] = {**planes[e["aircraft_id"]], "latitude": e["move_to_latitude"],
                                        "longitude": e["move_to_longitude"]}
    return planes


def assert_all_safe(conn):
    planes = effective_positions(conn)
    for a, b in itertools.combinations(sorted(planes), 2):
        assert not too_close(planes[a], planes[b]), (a, b)


def test_three_planes_in_a_cluster_all_end_up_safe(tower):
    radar_sends(info("A1", 40.70, -73.80, 2000))
    radar_sends(info("B2", 40.72, -73.81, 2000))
    radar_sends(info("C3", 40.71, -73.79, 2000))
    run(tower)
    assert_all_safe(tower)
    assert run(tower) == []


def test_two_moves_never_aim_at_the_same_spot(tower):
    # Two pairs side by side whose best spots would overlap if pending moves were ignored.
    for aircraft_id, lat, lon in [("A1", 40.70, -73.80), ("B2", 40.75, -73.80), ("C3", 40.70, -73.69), ("D4", 40.75, -73.69)]:
        radar_sends(info(aircraft_id, lat, lon, 2000))
    run(tower)
    assert_all_safe(tower)


@pytest.mark.parametrize("seed", range(20))
def test_random_skies_always_end_up_safe(tower, seed):
    rng = random.Random(seed)
    for n in range(12):
        radar_sends(info(f"P{n:02}", 40.7 + rng.uniform(-0.15, 0.15), -73.8 + rng.uniform(-0.15, 0.15),
                         rng.choice([2000, 2400, 2800])))
    run(tower)
    # Every pair is safe, except a pair tower recorded as WAITING (no clear spot) — and that's reported.
    waiting = {frozenset((e["aircraft_id"], e["other_aircraft_id"]))
               for e in get_separations(tower, "JFK") if e["status"] == "WAITING"}
    planes = effective_positions(tower)
    unsafe = {frozenset(pair) for pair in itertools.combinations(sorted(planes), 2) if too_close(*(planes[k] for k in pair))}
    assert unsafe <= waiting
    assert run(tower) == []  # a second run changes nothing


def test_a_new_plane_near_a_pending_spot_is_flagged(tower):
    two_close_planes()
    run(tower)  # B2 told to go to (40.81, -73.80); radar hasn't answered yet
    radar_sends(info("C3", 40.86, -73.78, 2500))  # clear of B2's old spot and of A1, but close to B2's new one
    [changed] = run(tower)
    assert (changed["aircraft_id"], changed["other_aircraft_id"]) == ("C3", "B2")  # B2 is busy, so C3 moves
    assert_all_safe(tower)


def test_runway_holder_stays_put(tower):
    radar_sends(info("A1", 40.70, -73.80, 2000))
    radar_sends(info("B2", 40.75, -73.82, 2500))
    radar_sends(event("REQUEST_LANDING", "B2", "2026-11-15T10:00:00"))  # B2 gets runway 1
    answer_requests(tower, "JFK")
    radar_sends(event("REQUEST_LANDING", "A1", "2026-11-15T09:00:00"))  # A1 asked EARLIER, but has no runway yet
    run(tower)
    # By request time B2 is later and would move; holding a runway overrides that, so A1 moves.
    assert statuses(tower) == [(1, "A1", "B2", "OPEN")]


def test_radars_r1_code_ignores_the_new_message(tower):
    two_close_planes()
    run(tower)
    radar = sqlite3.connect(":memory:")
    assert check_tower_replies(radar) == []  # radar's check-replies doesn't crash or act on it


def test_positions_table_is_readable(tower):
    two_close_planes()
    radar_sends(event("REQUEST_LANDING", "A1", "2026-11-15T10:01:00"))
    run(tower)
    assert get_aircraft_positions(tower, "JFK") == [
        {"aircraft_id": "A1", "latitude": 40.70, "longitude": -73.80, "altitude": 2000.0, "status": "Landing",
         "on_ground": False, "requested_at": "2026-11-15T10:01:00", "timestamp": "2026-11-15T10:00:00"},
        {"aircraft_id": "B2", "latitude": 40.75, "longitude": -73.82, "altitude": 2500.0, "status": "Landing",
         "on_ground": False, "requested_at": None, "timestamp": "2026-11-15T10:00:00"},
    ]


def test_command_output(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["python -m src.tower.airport", "answer-requests"])
    two_close_planes()
    cli.main()
    assert "Separation 1: B2 and A1 too close, told radar to move B2 to (40.81, -73.8)" in capsys.readouterr().out
    radar_resolves(1, "B2")
    cli.main()
    assert "Separation 1: B2 and A1 resolved (told command)" in capsys.readouterr().out
