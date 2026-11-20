# REQ-RAD-012
# __main__.py — CLI for creating and inspecting airplanes and talking to tower.
#
# Supports:
#   1. Positional args in prompt order:
#        python -m src.radar.airplane create AA123 40.6413 -73.7781 35000 Departing
#   2. Named flags / keywords:
#        python -m src.radar.airplane create --aircraft-id AA123 --lat 40.6413 --lon -73.7781 --alt 35000 --status Departing
#   3. Raw JSON:
#        python -m src.radar.airplane create --json '{"aircraft_id":"AA123","latitude":40.6413,"longitude":-73.7781,"altitude":35000,"status":"Departing"}'
#        python -m src.radar.airplane create '{"aircraft_id":"AA123",...}'
#        python -m src.radar.airplane create --json '["AA123", 40.6413, -73.7781, 35000, "Departing"]'
#        python -m src.radar.airplane create '["AA123", 40.6413, -73.7781, 35000, "Departing"]'
#   4. JSON file via @path/to/file.json:
#        python -m src.radar.airplane create @plane.json
#        python -m src.radar.airplane create --json @plane.json
#   5. Optional interactive fallback when args are omitted or -i/--interactive is passed:
#        python -m src.radar.airplane create -i
#
# R1 + R2 commands supported:
#   create, list, set-altitude, set-position, send-info,
#   request-landing, request-takeoff, check-replies, fake-tower-reply,
#   report-landed, report-departed, report-parked,
#   run [--once], report-conflict, conflicts,
#   fake-unsafe-separation, fake-conflict-resolved

# NOTE: Claude, please review `test_cli.py` in Radar's tests before modifying this file.

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from src.radar.airplane.aircraft_repo import get_aircraft, init_db, update_altitude, update_position
from src.radar.airplane.conflicts import (
    CONFLICT_REASONS,
    fake_conflict_resolved,
    get_conflict,
    get_conflicts,
    open_conflict,
)
from src.radar.airplane.create_airplane import create_airplane
from src.radar.airplane.monitor import run
from src.radar.airplane.runway_requests import (
    check_tower_replies,
    fake_tower_reply,
    report_departed,
    report_landed,
    report_parked,
    request_landing,
    request_takeoff,
    send_aircraft_info,
)
from src.radar.airplane.separation import fake_unsafe_separation
from src.tower.messaging.query_fetch import load_queries

QUERIES = load_queries("queries.sql")
STATUSES = ["Parked", "Departing", "Landing"]
STATUS_MAP = {s.lower(): s for s in STATUSES}


class RadarArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that also expands @file.json tokens when passed as standalone positional args."""

    def convert_arg_line_to_args(self, arg_line: str) -> list[str]:
        stripped = arg_line.strip()
        if not stripped or stripped.startswith("#"):
            return []
        # Support a JSON object/array file used with argparse's @file mechanism.
        if stripped.startswith("{") or stripped.startswith("["):
            return [stripped]
        return super().convert_arg_line_to_args(arg_line)


def normalize_status(value: str) -> str:
    key = value.strip().lower()
    if key not in STATUS_MAP:
        raise argparse.ArgumentTypeError(
            f"Invalid status '{value}'. Expected one of: {', '.join(STATUSES)}"
        )
    return STATUS_MAP[key]


def normalize_conflict_reason(value: str) -> str:
    reasons = list(CONFLICT_REASONS)
    cleaned = value.strip()
    if cleaned.isdigit():
        idx = int(cleaned) - 1
        if 0 <= idx < len(reasons):
            return reasons[idx]
    upper = cleaned.upper()
    if upper in CONFLICT_REASONS:
        return upper
    raise argparse.ArgumentTypeError(
        f"Invalid conflict reason '{value}'. Expected 1-{len(reasons)} or one of: {', '.join(reasons)}"
    )


COMMAND_ARRAY_KEYS: dict[str, list[str]] = {
    "create": ["aircraft_id", "latitude", "longitude", "altitude", "status"],
    "set-altitude": ["aircraft_id", "altitude"],
    "set-position": ["aircraft_id", "latitude", "longitude"],
    "send-info": ["aircraft_id"],
    "request-landing": ["aircraft_id"],
    "request-takeoff": ["aircraft_id"],
    "report-landed": ["aircraft_id"],
    "report-departed": ["aircraft_id"],
    "report-parked": ["aircraft_id"],
    "fake-tower-reply": ["aircraft_id", "runway_id"],
    "report-conflict": ["aircraft_id", "reason"],
    "fake-unsafe-separation": ["aircraft_id", "latitude", "longitude"],
    "fake-conflict-resolved": ["conflict_id"],
}


def load_json_source(
    source: str,
    label: str = "JSON",
    array_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Load a JSON object—or a JSON array mapped by positional order—from raw JSON or @file."""
    raw = source.strip()
    if raw.startswith("@"):
        file_path = Path(raw[1:]).expanduser()
        try:
            text = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"Could not read {label} file '{file_path}': {exc}") from exc
    else:
        text = raw

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid {label}: {exc}") from exc

    if isinstance(data, dict):
        return data

    if isinstance(data, list):
        if not array_keys:
            raise ValueError(f"{label} array is not supported for this command")
        if len(data) > len(array_keys):
            raise ValueError(
                f"{label} array has {len(data)} items, expected at most {len(array_keys)} "
                f"({', '.join(array_keys)})"
            )
        return dict(zip(array_keys, data))

    raise ValueError(f"{label} must be a JSON object or array, got {type(data).__name__}")


def pick_value(
    flag_val: Any,
    pos_val: Any,
    json_data: dict[str, Any],
    json_keys: list[str],
    interactive: bool,
    prompt_fn,
    cast_fn=lambda x: x,
    required: bool = True,
) -> Any:
    """Resolve a field using precedence: explicit flag > positional arg > JSON > interactive prompt."""
    if flag_val is not None:
        return cast_fn(flag_val)
    if pos_val is not None:
        return cast_fn(pos_val)
    for key in json_keys:
        if key in json_data and json_data[key] is not None:
            return cast_fn(json_data[key])
    if interactive:
        return prompt_fn()
    if required:
        raise ValueError(
            f"Missing required value (tried flags, positionals, and JSON keys: {', '.join(json_keys)})"
        )
    return None


def ask_text(question: str) -> str:
    while True:
        answer = input(f"{question}: ").strip()
        if answer:
            return answer
        print("  This can't be empty.")


def ask_number(question: str) -> float:
    while True:
        answer = input(f"{question}: ").strip()
        try:
            return float(answer)
        except ValueError:
            print("  Please type a number.")


def ask_status() -> str:
    while True:
        answer = input(f"Status ({', '.join(STATUSES)}): ").strip()
        try:
            return normalize_status(answer)
        except argparse.ArgumentTypeError as exc:
            print(f"  {exc}")


def ask_reason() -> str:
    """Keep asking until the answer is a reason's number or name, e.g. '3' or 'LOW_FUEL'."""
    reasons = list(CONFLICT_REASONS)
    for number, reason in enumerate(reasons, start=1):
        print(f"  {number}. {reason:<9} (plane {CONFLICT_REASONS[reason]})")
    while True:
        answer = input("Reason (number or name): ").strip()
        try:
            return normalize_conflict_reason(answer)
        except argparse.ArgumentTypeError as exc:
            print(f"  {exc}")


def _extract_json_blob(
    pos_first: str | None,
    json_flag: str | None,
    command: str,
) -> dict[str, Any]:
    """Handle --json <raw | @file> or a raw JSON / @file.json passed as the first positional arg."""
    keys = COMMAND_ARRAY_KEYS.get(command)
    if json_flag is not None:
        return load_json_source(json_flag, "--json", array_keys=keys)
    if pos_first is not None:
        stripped = pos_first.strip()
        if stripped.startswith("@") or stripped.startswith("{") or stripped.startswith("["):
            return load_json_source(stripped, "JSON argument", array_keys=keys)
    return {}


def _is_json_or_file_token(val: str | None) -> bool:
    if val is None:
        return False
    s = val.strip()
    return s.startswith("@") or s.startswith("{") or s.startswith("[")


def _resolve_single_aircraft_id(args: argparse.Namespace, prompt_label: str = "Aircraft ID") -> str:
    json_data = _extract_json_blob(args.pos_aircraft_id, args.json_payload, args.command)
    pos_id = None if _is_json_or_file_token(args.pos_aircraft_id) else args.pos_aircraft_id
    interactive = args.interactive or (not json_data and args.aircraft_id is None and pos_id is None)
    return pick_value(
        args.aircraft_id,
        pos_id,
        json_data,
        ["aircraft_id", "id"],
        interactive,
        lambda: ask_text(prompt_label),
        str,
    )


def cmd_create(conn, args: argparse.Namespace) -> None:
    json_data = _extract_json_blob(args.pos_aircraft_id, args.json_payload, args.command)
    pos_id = None if _is_json_or_file_token(args.pos_aircraft_id) else args.pos_aircraft_id

    interactive = args.interactive or (
        not json_data
        and args.aircraft_id is None
        and pos_id is None
        and args.latitude is None
        and args.pos_latitude is None
        and args.longitude is None
        and args.pos_longitude is None
        and args.altitude is None
        and args.pos_altitude is None
        and args.status is None
        and args.pos_status is None
    )

    aircraft_id = pick_value(
        args.aircraft_id,
        pos_id,
        json_data,
        ["aircraft_id", "id"],
        interactive,
        lambda: ask_text("Aircraft ID"),
        str,
    )
    latitude = pick_value(
        args.latitude,
        pos_latitude := args.pos_latitude,
        json_data,
        ["latitude", "lat"],
        interactive,
        lambda: ask_number("Latitude"),
        float,
    )
    longitude = pick_value(
        args.longitude,
        pos_longitude := args.pos_longitude,
        json_data,
        ["longitude", "lon", "lng"],
        interactive,
        lambda: ask_number("Longitude"),
        float,
    )
    altitude = pick_value(
        args.altitude,
        pos_altitude := args.pos_altitude,
        json_data,
        ["altitude", "alt"],
        interactive,
        lambda: ask_number("Altitude (feet)"),
        float,
    )
    status = pick_value(
        args.status,
        args.pos_status,
        json_data,
        ["status"],
        interactive,
        ask_status,
        normalize_status,
    )
    _ = (pos_latitude, pos_longitude, pos_altitude)

    create_airplane(conn, aircraft_id, latitude, longitude, altitude, status)
    print(f"\nCreated airplane {aircraft_id} and sent it to tower.")


def cmd_set_altitude(conn, args: argparse.Namespace) -> None:
    json_data = _extract_json_blob(args.pos_aircraft_id, args.json_payload, args.command)
    pos_id = None if _is_json_or_file_token(args.pos_aircraft_id) else args.pos_aircraft_id
    interactive = args.interactive or (
        not json_data
        and args.aircraft_id is None
        and pos_id is None
        and args.altitude is None
        and args.pos_altitude is None
    )

    aircraft_id = pick_value(
        args.aircraft_id,
        pos_id,
        json_data,
        ["aircraft_id", "id"],
        interactive,
        lambda: ask_text("Aircraft ID"),
        str,
    )
    altitude = pick_value(
        args.altitude,
        args.pos_altitude,
        json_data,
        ["altitude", "alt", "new_altitude"],
        interactive,
        lambda: ask_number("New altitude (feet)"),
        float,
    )

    update_altitude(conn, aircraft_id, altitude)
    send_aircraft_info(conn, aircraft_id)
    print(f"\nSet {aircraft_id} altitude to {altitude} feet and sent the update to tower.")


def cmd_set_position(conn, args: argparse.Namespace) -> None:
    json_data = _extract_json_blob(args.pos_aircraft_id, args.json_payload, args.command)
    pos_id = None if _is_json_or_file_token(args.pos_aircraft_id) else args.pos_aircraft_id
    interactive = args.interactive or (
        not json_data
        and args.aircraft_id is None
        and pos_id is None
        and args.latitude is None
        and args.pos_latitude is None
        and args.longitude is None
        and args.pos_longitude is None
    )

    aircraft_id = pick_value(
        args.aircraft_id,
        pos_id,
        json_data,
        ["aircraft_id", "id"],
        interactive,
        lambda: ask_text("Aircraft ID"),
        str,
    )
    latitude = pick_value(
        args.latitude,
        args.pos_latitude,
        json_data,
        ["latitude", "lat"],
        interactive,
        lambda: ask_number("New latitude"),
        float,
    )
    longitude = pick_value(
        args.longitude,
        args.pos_longitude,
        json_data,
        ["longitude", "lon", "lng"],
        interactive,
        lambda: ask_number("New longitude"),
        float,
    )

    update_position(conn, aircraft_id, latitude, longitude)
    send_aircraft_info(conn, aircraft_id)
    print(f"\nMoved {aircraft_id} to ({latitude}, {longitude}) and sent the update to tower.")


def cmd_send_info(conn, args: argparse.Namespace) -> None:
    aircraft_id = _resolve_single_aircraft_id(args)
    info = send_aircraft_info(conn, aircraft_id)
    print(f"\nSent {aircraft_id} to tower:")
    print(f"  Latitude:  {info['latitude']:.4f}")
    print(f"  Longitude: {info['longitude']:.4f}")
    print(f"  Altitude:  {info['altitude']:.1f} ft")
    print(f"  Status:    {info['status']}")
    print(f"  Runway:    {info['runway_id'] or '-'}")
    print(f"  Updated:   {info['timestamp']}")


def cmd_request(conn, args: argparse.Namespace, ask_tower, kind: str) -> None:
    aircraft_id = _resolve_single_aircraft_id(args)
    ask_tower(conn, aircraft_id)
    print(f"\nSent {kind} request for {aircraft_id} to tower.")


def cmd_report(conn, args: argparse.Namespace, tell_tower, done: str) -> None:
    aircraft_id = _resolve_single_aircraft_id(args)
    tell_tower(conn, aircraft_id)
    print(f"\nTold tower {aircraft_id} {done}.")


def cmd_check_replies(conn, args: argparse.Namespace) -> None:
    results = check_tower_replies(conn)
    if not results:
        print("No replies from tower about radar's planes.")
        return
    for line in results:
        print(line)


def cmd_fake_reply(conn, args: argparse.Namespace) -> None:
    json_data = _extract_json_blob(args.pos_aircraft_id, args.json_payload, args.command)
    pos_id = None if _is_json_or_file_token(args.pos_aircraft_id) else args.pos_aircraft_id
    pos_runway = None if _is_json_or_file_token(args.pos_aircraft_id) else args.pos_runway_id

    interactive = args.interactive or (
        not json_data
        and args.aircraft_id is None
        and pos_id is None
        and args.runway_id is None
        and pos_runway is None
    )

    aircraft_id = pick_value(
        args.aircraft_id,
        pos_id,
        json_data,
        ["aircraft_id", "id"],
        interactive,
        lambda: ask_text("Aircraft ID"),
        str,
    )
    if get_aircraft(conn, aircraft_id) is None:
        raise ValueError(f"radar has no aircraft {aircraft_id}")

    runway_id = pick_value(
        args.runway_id,
        pos_runway,
        json_data,
        ["runway_id", "runway"],
        interactive,
        lambda: input("Runway (leave empty for no runway): ").strip(),
        lambda v: "" if v is None else str(v).strip(),
        required=False,
    )
    if runway_id is None:
        runway_id = ""

    fake_tower_reply(aircraft_id, runway_id)
    answer = f"runway {runway_id}" if runway_id else "no runway"
    print(f"\nTower replied: {answer} for {aircraft_id} (test reply). Run check-replies to read it.")


def cmd_list(conn, args: argparse.Namespace) -> None:
    rows = conn.execute(QUERIES.RDR_B_06).fetchall()
    if not rows:
        print("\nNo airplanes in radar.db yet.")
        return
    print(f"\nAirplanes in radar.db ({len(rows)})")
    print(f"{'ID':<8}{'Latitude':>10}{'Longitude':>12}{'Altitude':>11}  {'Status':<11}{'Runway':<8}Timestamp")
    print("-" * 81)
    for aircraft_id, latitude, longitude, altitude, status, timestamp, runway_id in rows:
        runway = runway_id or "-"
        print(
            f"{aircraft_id:<8}{latitude:>10.4f}{longitude:>12.4f}{altitude:>11.1f}  "
            f"{status:<11}{runway:<8}{timestamp}"
        )


def cmd_run(conn, args: argparse.Namespace) -> None:
    run(conn, ticks=1 if args.once else None)


def cmd_report_conflict(conn, args: argparse.Namespace) -> None:
    json_data = _extract_json_blob(args.pos_aircraft_id, args.json_payload, args.command)
    pos_id = None if _is_json_or_file_token(args.pos_aircraft_id) else args.pos_aircraft_id
    interactive = args.interactive or (
        not json_data
        and args.aircraft_id is None
        and pos_id is None
        and args.reason is None
        and args.pos_reason is None
    )

    aircraft_id = pick_value(
        args.aircraft_id,
        pos_id,
        json_data,
        ["aircraft_id", "id"],
        interactive,
        lambda: ask_text("Aircraft ID"),
        str,
    )
    reason = pick_value(
        args.reason,
        args.pos_reason,
        json_data,
        ["reason"],
        interactive,
        ask_reason,
        normalize_conflict_reason,
    )

    conflict = open_conflict(conn, aircraft_id, reason)
    print(f"\nConflict {reason} opened for {aircraft_id} (id {conflict['conflict_id']}).")
    print("`python -m src.radar.airplane run` sends it to tower every second until tower resolves it.")


def cmd_conflicts(conn, args: argparse.Namespace) -> None:
    conflicts = get_conflicts(conn)
    if not conflicts:
        print("\nNo conflicts in radar.db yet.")
        return
    print(f"\n{'Aircraft':<10}{'Reason':<10}{'Status':<10}{'Opened':<21}{'Resolved':<21}ID")
    print("-" * 100)
    for c in conflicts:
        print(
            f"{c['aircraft_id']:<10}{c['reason']:<10}{c['status']:<10}{c['opened_at']:<21}"
            f"{c['resolved_at'] or '-':<21}{c['conflict_id']}"
        )


def cmd_fake_unsafe_separation(conn, args: argparse.Namespace) -> None:
    json_data = _extract_json_blob(args.pos_aircraft_id, args.json_payload, args.command)
    pos_id = None if _is_json_or_file_token(args.pos_aircraft_id) else args.pos_aircraft_id
    interactive = args.interactive or (
        not json_data
        and args.aircraft_id is None
        and pos_id is None
        and args.latitude is None
        and args.pos_latitude is None
        and args.longitude is None
        and args.pos_longitude is None
    )

    aircraft_id = pick_value(
        args.aircraft_id,
        pos_id,
        json_data,
        ["aircraft_id", "id"],
        interactive,
        lambda: ask_text("Aircraft ID"),
        str,
    )
    if get_aircraft(conn, aircraft_id) is None:
        raise ValueError(f"radar has no aircraft {aircraft_id}")

    latitude = pick_value(
        args.latitude,
        args.pos_latitude,
        json_data,
        ["latitude", "lat"],
        interactive,
        lambda: ask_number("Move to latitude"),
        float,
    )
    longitude = pick_value(
        args.longitude,
        args.pos_longitude,
        json_data,
        ["longitude", "lon", "lng"],
        interactive,
        lambda: ask_number("Move to longitude"),
        float,
    )

    fake_unsafe_separation(aircraft_id, latitude, longitude)
    print(
        f"\nTower told radar to move {aircraft_id} to ({latitude}, {longitude}) (test message). "
        "Run `run --once` to handle it."
    )


def cmd_fake_conflict_resolved(conn, args: argparse.Namespace) -> None:
    json_data = _extract_json_blob(args.pos_conflict_id, args.json_payload, args.command)
    pos_cid = None if _is_json_or_file_token(args.pos_conflict_id) else args.pos_conflict_id
    interactive = args.interactive or (
        not json_data and args.conflict_id is None and pos_cid is None
    )

    open_conflicts = get_conflicts(conn, "OPEN")
    if interactive and open_conflicts:
        open_ids = [c["conflict_id"] for c in open_conflicts]
        print("Open conflicts: " + ", ".join(open_ids))

    conflict_id = pick_value(
        args.conflict_id,
        pos_cid,
        json_data,
        ["conflict_id", "id"],
        interactive,
        lambda: ask_text("Conflict ID"),
        str,
    )
    conflict = get_conflict(conn, conflict_id)
    if conflict is None or conflict["status"] != "OPEN":
        raise ValueError(f"no open conflict with ID {conflict_id}")

    fake_conflict_resolved(conflict)
    print(
        f"\nTower resolved {conflict['conflict_id']} (test message). "
        "Run `run --once` to handle it."
    )


def _add_common_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json",
        dest="json_payload",
        metavar="JSON_OR_@FILE",
        help="Raw JSON string or @path/to/file.json supplying command fields",
    )
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Prompt interactively for any missing fields",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = RadarArgumentParser(
        prog="python -m src.radar.airplane",
        description="Radar airplane CLI — supports positional args, named flags, raw JSON, and @file.json.",
        fromfile_prefix_chars="@",
    )
    parser.add_argument(
        "--db",
        default="radar.db",
        help="Path to SQLite database (default: radar.db)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # create
    p_create = subparsers.add_parser("create", help="Create an airplane and notify tower")
    _add_common_flags(p_create)
    p_create.add_argument("pos_aircraft_id", nargs="?", metavar="AIRCRAFT_ID_OR_@JSON")
    p_create.add_argument("pos_latitude", nargs="?", type=float, metavar="LATITUDE")
    p_create.add_argument("pos_longitude", nargs="?", type=float, metavar="LONGITUDE")
    p_create.add_argument("pos_altitude", nargs="?", type=float, metavar="ALTITUDE")
    p_create.add_argument("pos_status", nargs="?", type=normalize_status, metavar="STATUS")
    p_create.add_argument("--aircraft-id", "--id", dest="aircraft_id")
    p_create.add_argument("--latitude", "--lat", dest="latitude", type=float)
    p_create.add_argument("--longitude", "--lon", "--lng", dest="longitude", type=float)
    p_create.add_argument("--altitude", "--alt", dest="altitude", type=float)
    p_create.add_argument("--status", dest="status", type=normalize_status)
    p_create.set_defaults(func=cmd_create)

    # list
    p_list = subparsers.add_parser("list", help="List all airplanes in radar.db")
    p_list.add_argument("--db", dest="db", default=argparse.SUPPRESS)
    p_list.set_defaults(func=cmd_list)

    # set-altitude
    p_alt = subparsers.add_parser("set-altitude", help="Update an airplane's altitude and notify tower")
    _add_common_flags(p_alt)
    p_alt.add_argument("pos_aircraft_id", nargs="?", metavar="AIRCRAFT_ID_OR_@JSON")
    p_alt.add_argument("pos_altitude", nargs="?", type=float, metavar="ALTITUDE")
    p_alt.add_argument("--aircraft-id", "--id", dest="aircraft_id")
    p_alt.add_argument("--altitude", "--alt", dest="altitude", type=float)
    p_alt.set_defaults(func=cmd_set_altitude)

    # set-position
    p_pos = subparsers.add_parser("set-position", help="Update an airplane's position and notify tower")
    _add_common_flags(p_pos)
    p_pos.add_argument("pos_aircraft_id", nargs="?", metavar="AIRCRAFT_ID_OR_@JSON")
    p_pos.add_argument("pos_latitude", nargs="?", type=float, metavar="LATITUDE")
    p_pos.add_argument("pos_longitude", nargs="?", type=float, metavar="LONGITUDE")
    p_pos.add_argument("--aircraft-id", "--id", dest="aircraft_id")
    p_pos.add_argument("--latitude", "--lat", dest="latitude", type=float)
    p_pos.add_argument("--longitude", "--lon", "--lng", dest="longitude", type=float)
    p_pos.set_defaults(func=cmd_set_position)

    # single-ID commands
    for cmd_name, help_text, handler in [
        ("send-info", "Send an airplane's current telemetry to tower", cmd_send_info),
        (
            "request-landing",
            "Request a landing runway from tower",
            lambda conn, a: cmd_request(conn, a, request_landing, "landing"),
        ),
        (
            "request-takeoff",
            "Request a takeoff runway from tower",
            lambda conn, a: cmd_request(conn, a, request_takeoff, "takeoff"),
        ),
        (
            "report-landed",
            "Report to tower that an airplane has landed",
            lambda conn, a: cmd_report(conn, a, report_landed, "has landed"),
        ),
        (
            "report-departed",
            "Report to tower that an airplane has departed",
            lambda conn, a: cmd_report(conn, a, report_departed, "has departed"),
        ),
        (
            "report-parked",
            "Report to tower that a landed airplane has parked",
            lambda conn, a: cmd_report(conn, a, report_parked, "has parked"),
        ),
    ]:
        p_single = subparsers.add_parser(cmd_name, help=help_text)
        _add_common_flags(p_single)
        p_single.add_argument("pos_aircraft_id", nargs="?", metavar="AIRCRAFT_ID_OR_@JSON")
        p_single.add_argument("--aircraft-id", "--id", dest="aircraft_id")
        p_single.set_defaults(func=handler)

    # check-replies
    p_replies = subparsers.add_parser("check-replies", help="Read tower replies and update runways")
    p_replies.set_defaults(func=cmd_check_replies)

    # fake-tower-reply
    p_fake = subparsers.add_parser("fake-tower-reply", help="TESTING: simulate a runway reply from tower")
    _add_common_flags(p_fake)
    p_fake.add_argument("pos_aircraft_id", nargs="?", metavar="AIRCRAFT_ID_OR_@JSON")
    p_fake.add_argument("pos_runway_id", nargs="?", metavar="RUNWAY_ID")
    p_fake.add_argument("--aircraft-id", "--id", dest="aircraft_id")
    p_fake.add_argument("--runway-id", "--runway", dest="runway_id")
    p_fake.set_defaults(func=cmd_fake_reply)

    # run
    p_run = subparsers.add_parser("run", help="Run the R2 radar monitoring loop")
    p_run.add_argument("--once", action="store_true", help="Run a single loop tick and exit")
    p_run.set_defaults(func=cmd_run)

    # report-conflict
    p_conflict = subparsers.add_parser("report-conflict", help="Open a conflict for an aircraft")
    _add_common_flags(p_conflict)
    p_conflict.add_argument("pos_aircraft_id", nargs="?", metavar="AIRCRAFT_ID_OR_@JSON")
    p_conflict.add_argument("pos_reason", nargs="?", metavar="REASON")
    p_conflict.add_argument("--aircraft-id", "--id", dest="aircraft_id")
    p_conflict.add_argument("--reason", dest="reason")
    p_conflict.set_defaults(func=cmd_report_conflict)

    # conflicts
    p_conflicts = subparsers.add_parser("conflicts", help="List conflicts in radar.db")
    p_conflicts.set_defaults(func=cmd_conflicts)

    # fake-unsafe-separation
    p_sep = subparsers.add_parser(
        "fake-unsafe-separation",
        help="TESTING: simulate an UNSAFE_SEPARATION message from tower",
    )
    _add_common_flags(p_sep)
    p_sep.add_argument("pos_aircraft_id", nargs="?", metavar="AIRCRAFT_ID_OR_@JSON")
    p_sep.add_argument("pos_latitude", nargs="?", type=float, metavar="LATITUDE")
    p_sep.add_argument("pos_longitude", nargs="?", type=float, metavar="LONGITUDE")
    p_sep.add_argument("--aircraft-id", "--id", dest="aircraft_id")
    p_sep.add_argument("--latitude", "--lat", dest="latitude", type=float)
    p_sep.add_argument("--longitude", "--lon", "--lng", dest="longitude", type=float)
    p_sep.set_defaults(func=cmd_fake_unsafe_separation)

    # fake-conflict-resolved
    p_resolved = subparsers.add_parser(
        "fake-conflict-resolved",
        help="TESTING: simulate a CONFLICT_RESOLVED message from tower",
    )
    _add_common_flags(p_resolved)
    p_resolved.add_argument("pos_conflict_id", nargs="?", metavar="CONFLICT_ID_OR_@JSON")
    p_resolved.add_argument("--conflict-id", "--id", dest="conflict_id")
    p_resolved.set_defaults(func=cmd_fake_conflict_resolved)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    conn = init_db(args.db)
    try:
        args.func(conn, args)
    except ValueError as error:
        print(f"\nError: {error}")
        sys.exit(1)
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        sys.exit(130)
    finally:
        conn.close()


if __name__ == "__main__":
    main()