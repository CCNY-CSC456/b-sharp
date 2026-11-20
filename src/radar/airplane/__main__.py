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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from src.radar.airplane.aircraft_repo import init_db, update_altitude, update_position
from src.radar.airplane.conflicts import get_conflicts, open_conflict
from src.radar.airplane.create_airplane import create_airplane
from src.radar.airplane.monitor import run
from src.radar.airplane.runway_requests import (
    check_tower_replies,
    report_departed,
    report_landed,
    report_parked,
    request_landing,
    request_takeoff,
    send_aircraft_info,
)
from src.tower.messaging.query_fetch import load_queries

QUERIES = load_queries("queries.sql")
STATUSES = ["Parked", "Departing", "Landing"]
STATUS_MAP = {s.lower(): s for s in STATUSES}


@dataclass(frozen=True)
class ParamSpec:
    name: str
    flags: tuple[str, ...]
    json_keys: tuple[str, ...]
    prompt_fn: Callable[[], Any]
    cast: Callable[[Any], Any] = lambda v: v
    pos_type: Callable[[str], Any] | None = None
    flag_type: Callable[[str], Any] | None = None
    pos_metavar: str | None = None
    required: bool = True


@dataclass(frozen=True)
class CommandSpec:
    name: str
    help: str
    handler: Callable[[Any, dict[str, Any], argparse.Namespace], None]
    params: tuple[ParamSpec, ...] = ()
    primary_pos_attr: str | None = "pos_aircraft_id"
    extra_args: Callable[[argparse.ArgumentParser], None] | None = None


class RadarArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that also expands @file.json tokens when passed as standalone positional args."""

    def convert_arg_line_to_args(self, arg_line: str) -> list[str]:
        stripped = arg_line.strip()
        if not stripped or stripped.startswith("#"):
            return []
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
    from src.radar.airplane.conflicts import CONFLICT_REASONS

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


def _is_json_or_file_token(val: str | None) -> bool:
    if val is None:
        return False
    s = val.strip()
    return s.startswith("@") or s.startswith("{") or s.startswith("[")


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


def _extract_json_blob(
    pos_first: str | None,
    json_flag: str | None,
    array_keys: list[str] | None,
) -> dict[str, Any]:
    """Handle --json <raw | @file> or a raw JSON / @file.json passed as the primary positional arg."""
    if json_flag is not None:
        return load_json_source(json_flag, "--json", array_keys=array_keys)
    if _is_json_or_file_token(pos_first):
        assert pos_first is not None
        return load_json_source(pos_first.strip(), "JSON argument", array_keys=array_keys)
    return {}


def pick_value(
    flag_val: Any,
    pos_val: Any,
    json_data: dict[str, Any],
    json_keys: list[str] | tuple[str, ...],
    interactive: bool,
    prompt_fn: Callable[[], Any],
    cast_fn: Callable[[Any], Any] = lambda x: x,
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
    from src.radar.airplane.conflicts import CONFLICT_REASONS

    reasons = list(CONFLICT_REASONS)
    for number, reason in enumerate(reasons, start=1):
        print(f"  {number}. {reason:<9} (plane {CONFLICT_REASONS[reason]})")
    while True:
        answer = input("Reason (number or name): ").strip()
        try:
            return normalize_conflict_reason(answer)
        except argparse.ArgumentTypeError as exc:
            print(f"  {exc}")


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


def resolve_params(args: argparse.Namespace, spec: CommandSpec) -> dict[str, Any]:
    """Resolve all parameters declared on `spec` in declaration order."""
    first_pos_val = (
        getattr(args, spec.primary_pos_attr, None) if spec.primary_pos_attr else None
    )
    first_pos_is_json = _is_json_or_file_token(first_pos_val)
    array_keys = [p.name for p in spec.params]
    json_data = _extract_json_blob(
        first_pos_val,
        getattr(args, "json_payload", None),
        array_keys,
    )

    pos_vals: dict[str, Any] = {}
    for p in spec.params:
        pos_attr = f"pos_{p.name}"
        val = getattr(args, pos_attr, None)
        if first_pos_is_json and pos_attr == spec.primary_pos_attr:
            val = None
        pos_vals[p.name] = val

    has_explicit_input = bool(json_data) or any(
        getattr(args, p.name, None) is not None or pos_vals[p.name] is not None
        for p in spec.params
    )
    interactive = bool(getattr(args, "interactive", False)) or not has_explicit_input

    resolved: dict[str, Any] = {}
    for p in spec.params:
        resolved[p.name] = pick_value(
            flag_val=getattr(args, p.name, None),
            pos_val=pos_vals[p.name],
            json_data=json_data,
            json_keys=p.json_keys,
            interactive=interactive,
            prompt_fn=p.prompt_fn,
            cast_fn=p.cast,
            required=p.required,
        )
    return resolved


# --- Shared Parameter Specs ---

AIRCRAFT_ID_PARAM = ParamSpec(
    name="aircraft_id",
    flags=("--aircraft-id", "--id"),
    json_keys=("aircraft_id", "id"),
    prompt_fn=lambda: ask_text("Aircraft ID"),
    cast=str,
    pos_metavar="AIRCRAFT_ID_OR_@JSON",
)

LATITUDE_CREATE_PARAM = ParamSpec(
    name="latitude",
    flags=("--latitude", "--lat"),
    json_keys=("latitude", "lat"),
    prompt_fn=lambda: ask_number("Latitude"),
    cast=float,
    pos_type=float,
    flag_type=float,
    pos_metavar="LATITUDE",
)

LONGITUDE_CREATE_PARAM = ParamSpec(
    name="longitude",
    flags=("--longitude", "--lon", "--lng"),
    json_keys=("longitude", "lon", "lng"),
    prompt_fn=lambda: ask_number("Longitude"),
    cast=float,
    pos_type=float,
    flag_type=float,
    pos_metavar="LONGITUDE",
)

LATITUDE_MOVE_PARAM = ParamSpec(
    name="latitude",
    flags=("--latitude", "--lat"),
    json_keys=("latitude", "lat"),
    prompt_fn=lambda: ask_number("New latitude"),
    cast=float,
    pos_type=float,
    flag_type=float,
    pos_metavar="LATITUDE",
)

LONGITUDE_MOVE_PARAM = ParamSpec(
    name="longitude",
    flags=("--longitude", "--lon", "--lng"),
    json_keys=("longitude", "lon", "lng"),
    prompt_fn=lambda: ask_number("New longitude"),
    cast=float,
    pos_type=float,
    flag_type=float,
    pos_metavar="LONGITUDE",
)

ALTITUDE_CREATE_PARAM = ParamSpec(
    name="altitude",
    flags=("--altitude", "--alt"),
    json_keys=("altitude", "alt"),
    prompt_fn=lambda: ask_number("Altitude (feet)"),
    cast=float,
    pos_type=float,
    flag_type=float,
    pos_metavar="ALTITUDE",
)

ALTITUDE_SET_PARAM = ParamSpec(
    name="altitude",
    flags=("--altitude", "--alt"),
    json_keys=("altitude", "alt", "new_altitude"),
    prompt_fn=lambda: ask_number("New altitude (feet)"),
    cast=float,
    pos_type=float,
    flag_type=float,
    pos_metavar="ALTITUDE",
)

STATUS_PARAM = ParamSpec(
    name="status",
    flags=("--status",),
    json_keys=("status",),
    prompt_fn=ask_status,
    cast=normalize_status,
    pos_type=normalize_status,
    flag_type=normalize_status,
    pos_metavar="STATUS",
)

REASON_PARAM = ParamSpec(
    name="reason",
    flags=("--reason",),
    json_keys=("reason",),
    prompt_fn=ask_reason,
    cast=normalize_conflict_reason,
    pos_metavar="REASON",
)


# --- Command Handlers ---

def _run_create(conn, params: dict[str, Any], _args: argparse.Namespace) -> None:
    create_airplane(
        conn,
        params["aircraft_id"],
        params["latitude"],
        params["longitude"],
        params["altitude"],
        params["status"],
    )
    print(f"\nCreated airplane {params['aircraft_id']} and sent it to tower.")


def _run_set_altitude(conn, params: dict[str, Any], _args: argparse.Namespace) -> None:
    update_altitude(conn, params["aircraft_id"], params["altitude"])
    send_aircraft_info(conn, params["aircraft_id"])
    print(
        f"\nSet {params['aircraft_id']} altitude to {params['altitude']} feet "
        "and sent the update to tower."
    )


def _run_set_position(conn, params: dict[str, Any], _args: argparse.Namespace) -> None:
    update_position(conn, params["aircraft_id"], params["latitude"], params["longitude"])
    send_aircraft_info(conn, params["aircraft_id"])
    print(
        f"\nMoved {params['aircraft_id']} to ({params['latitude']}, {params['longitude']}) "
        "and sent the update to tower."
    )


def _run_send_info(conn, params: dict[str, Any], _args: argparse.Namespace) -> None:
    aircraft_id = params["aircraft_id"]
    info = send_aircraft_info(conn, aircraft_id)
    print(f"\nSent {aircraft_id} to tower:")
    print(f"  Latitude:  {info['latitude']:.4f}")
    print(f"  Longitude: {info['longitude']:.4f}")
    print(f"  Altitude:  {info['altitude']:.1f} ft")
    print(f"  Status:    {info['status']}")
    print(f"  Runway:    {info['runway_id'] or '-'}")
    print(f"  Updated:   {info['timestamp']}")


def _single_id_action_handler(
    action: Callable[[Any, str], Any],
    message_template: str,
) -> Callable[[Any, dict[str, Any], argparse.Namespace], None]:
    def _handler(conn, params: dict[str, Any], _args: argparse.Namespace) -> None:
        aircraft_id = params["aircraft_id"]
        action(conn, aircraft_id)
        print(message_template.format(aircraft_id=aircraft_id))

    return _handler


def _run_check_replies(conn, _params: dict[str, Any], _args: argparse.Namespace) -> None:
    results = check_tower_replies(conn)
    if not results:
        print("No replies from tower about radar's planes.")
        return
    for line in results:
        print(line)


def _run_list(conn, _params: dict[str, Any], _args: argparse.Namespace) -> None:
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


def _run_loop(conn, _params: dict[str, Any], args: argparse.Namespace) -> None:
    run(conn, ticks=1 if args.once else None)


def _run_report_conflict(conn, params: dict[str, Any], _args: argparse.Namespace) -> None:
    conflict = open_conflict(conn, params["aircraft_id"], params["reason"])
    print(
        f"\nConflict {params['reason']} opened for {params['aircraft_id']} "
        f"(id {conflict['conflict_id']})."
    )
    print("`python -m src.radar.airplane run` sends it to tower every second until tower resolves it.")


def _run_conflicts(conn, _params: dict[str, Any], _args: argparse.Namespace) -> None:
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


def _add_list_extra_args(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("--db", dest="db", default=argparse.SUPPRESS)


def _add_run_extra_args(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("--once", action="store_true", help="Run a single loop tick and exit")


COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="create",
        help="Create an airplane and notify tower",
        params=(
            AIRCRAFT_ID_PARAM,
            LATITUDE_CREATE_PARAM,
            LONGITUDE_CREATE_PARAM,
            ALTITUDE_CREATE_PARAM,
            STATUS_PARAM,
        ),
        handler=_run_create,
    ),
    CommandSpec(
        name="list",
        help="List all airplanes in radar.db",
        primary_pos_attr=None,
        extra_args=_add_list_extra_args,
        handler=_run_list,
    ),
    CommandSpec(
        name="set-altitude",
        help="Update an airplane's altitude and notify tower",
        params=(AIRCRAFT_ID_PARAM, ALTITUDE_SET_PARAM),
        handler=_run_set_altitude,
    ),
    CommandSpec(
        name="set-position",
        help="Update an airplane's position and notify tower",
        params=(AIRCRAFT_ID_PARAM, LATITUDE_MOVE_PARAM, LONGITUDE_MOVE_PARAM),
        handler=_run_set_position,
    ),
    CommandSpec(
        name="send-info",
        help="Send an airplane's current telemetry to tower",
        params=(AIRCRAFT_ID_PARAM,),
        handler=_run_send_info,
    ),
    CommandSpec(
        name="request-landing",
        help="Request a landing runway from tower",
        params=(AIRCRAFT_ID_PARAM,),
        handler=_single_id_action_handler(
            request_landing, "\nSent landing request for {aircraft_id} to tower."
        ),
    ),
    CommandSpec(
        name="request-takeoff",
        help="Request a takeoff runway from tower",
        params=(AIRCRAFT_ID_PARAM,),
        handler=_single_id_action_handler(
            request_takeoff, "\nSent takeoff request for {aircraft_id} to tower."
        ),
    ),
    CommandSpec(
        name="report-landed",
        help="Report to tower that an airplane has landed",
        params=(AIRCRAFT_ID_PARAM,),
        handler=_single_id_action_handler(
            report_landed, "\nTold tower {aircraft_id} has landed."
        ),
    ),
    CommandSpec(
        name="report-departed",
        help="Report to tower that an airplane has departed",
        params=(AIRCRAFT_ID_PARAM,),
        handler=_single_id_action_handler(
            report_departed, "\nTold tower {aircraft_id} has departed."
        ),
    ),
    CommandSpec(
        name="report-parked",
        help="Report to tower that a landed airplane has parked",
        params=(AIRCRAFT_ID_PARAM,),
        handler=_single_id_action_handler(
            report_parked, "\nTold tower {aircraft_id} has parked."
        ),
    ),
    CommandSpec(
        name="check-replies",
        help="Read tower replies and update runways",
        primary_pos_attr=None,
        handler=_run_check_replies,
    ),
    CommandSpec(
        name="run",
        help="Run the R2 radar monitoring loop",
        primary_pos_attr=None,
        extra_args=_add_run_extra_args,
        handler=_run_loop,
    ),
    CommandSpec(
        name="report-conflict",
        help="Open a conflict for an aircraft",
        params=(AIRCRAFT_ID_PARAM, REASON_PARAM),
        handler=_run_report_conflict,
    ),
    CommandSpec(
        name="conflicts",
        help="List conflicts in radar.db",
        primary_pos_attr=None,
        handler=_run_conflicts,
    ),
)

_COMMAND_SPEC_BY_NAME: dict[str, CommandSpec] = {spec.name: spec for spec in COMMAND_SPECS}


def _invoke_spec(conn, args: argparse.Namespace, spec: CommandSpec) -> None:
    params = resolve_params(args, spec)
    spec.handler(conn, params, args)


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

    for spec in COMMAND_SPECS:
        sub = subparsers.add_parser(spec.name, help=spec.help)
        if spec.params:
            _add_common_flags(sub)
        for p in spec.params:
            pos_kwargs: dict[str, Any] = {
                "nargs": "?",
                "metavar": p.pos_metavar or p.name.upper(),
            }
            if p.pos_type is not None:
                pos_kwargs["type"] = p.pos_type
            sub.add_argument(f"pos_{p.name}", **pos_kwargs)

            flag_kwargs: dict[str, Any] = {"dest": p.name}
            if p.flag_type is not None:
                flag_kwargs["type"] = p.flag_type
            sub.add_argument(*p.flags, **flag_kwargs)

        if spec.extra_args is not None:
            spec.extra_args(sub)

        sub.set_defaults(func=lambda conn, a, s=spec: _invoke_spec(conn, a, s))

    return parser


# --- Backward-Compatible `cmd_*` Entry Points ---

def _call_named_cmd(cmd_name: str, conn, args: argparse.Namespace) -> None:
    spec = _COMMAND_SPEC_BY_NAME[cmd_name]
    _invoke_spec(conn, args, spec)


def cmd_create(conn, args: argparse.Namespace) -> None:
    _call_named_cmd("create", conn, args)


def cmd_set_altitude(conn, args: argparse.Namespace) -> None:
    _call_named_cmd("set-altitude", conn, args)


def cmd_set_position(conn, args: argparse.Namespace) -> None:
    _call_named_cmd("set-position", conn, args)


def cmd_send_info(conn, args: argparse.Namespace) -> None:
    _call_named_cmd("send-info", conn, args)


def cmd_request(conn, args: argparse.Namespace, ask_tower, kind: str) -> None:
    aircraft_id = resolve_params(args, _COMMAND_SPEC_BY_NAME["request-landing"])["aircraft_id"]
    ask_tower(conn, aircraft_id)
    print(f"\nSent {kind} request for {aircraft_id} to tower.")


def cmd_report(conn, args: argparse.Namespace, tell_tower, done: str) -> None:
    aircraft_id = resolve_params(args, _COMMAND_SPEC_BY_NAME["report-landed"])["aircraft_id"]
    tell_tower(conn, aircraft_id)
    print(f"\nTold tower {aircraft_id} {done}.")


def cmd_check_replies(conn, args: argparse.Namespace) -> None:
    _call_named_cmd("check-replies", conn, args)


def cmd_list(conn, args: argparse.Namespace) -> None:
    _call_named_cmd("list", conn, args)


def cmd_run(conn, args: argparse.Namespace) -> None:
    _call_named_cmd("run", conn, args)


def cmd_report_conflict(conn, args: argparse.Namespace) -> None:
    _call_named_cmd("report-conflict", conn, args)


def cmd_conflicts(conn, args: argparse.Namespace) -> None:
    _call_named_cmd("conflicts", conn, args)


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