from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from src.radar.airplane.aircraft_repo import get_aircraft, init_db
from src.radar.airplane.conflicts import fake_conflict_resolved, get_conflict, get_conflicts
from src.radar.airplane.runway_requests import fake_tower_reply
from src.radar.airplane.separation import fake_unsafe_separation

FAKE_COMMAND_ARRAY_KEYS: dict[str, list[str]] = {
    "fake-tower-reply": ["aircraft_id", "runway_id"],
    "fake-unsafe-separation": ["aircraft_id", "latitude", "longitude"],
    "fake-conflict-resolved": ["conflict_id"],
}


class _FakeArgumentParser(argparse.ArgumentParser):
    def convert_arg_line_to_args(self, arg_line: str) -> list[str]:
        stripped = arg_line.strip()
        if not stripped or stripped.startswith("#"):
            return []
        if stripped.startswith("{") or stripped.startswith("["):
            return [stripped]
        return super().convert_arg_line_to_args(arg_line)


def _add_fake_common_flags(parser: argparse.ArgumentParser) -> None:
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


def _is_json_or_file_token(val: str | None) -> bool:
    if val is None:
        return False
    s = val.strip()
    return s.startswith("@") or s.startswith("{") or s.startswith("[")


def _load_json_source(
    source: str,
    label: str = "JSON",
    array_keys: list[str] | None = None,
) -> dict[str, Any]:
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
    command: str | None,
) -> dict[str, Any]:
    keys = FAKE_COMMAND_ARRAY_KEYS.get(command or "")
    if json_flag is not None:
        return _load_json_source(json_flag, "--json", array_keys=keys)
    if pos_first is not None:
        stripped = pos_first.strip()
        if stripped.startswith("@") or stripped.startswith("{") or stripped.startswith("["):
            return _load_json_source(stripped, "JSON argument", array_keys=keys)
    return {}


def _pick_value(
    flag_val: Any,
    pos_val: Any,
    json_data: dict[str, Any],
    json_keys: list[str],
    interactive: bool,
    prompt_fn,
    cast_fn=lambda x: x,
    required: bool = True,
) -> Any:
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


def _ask_text(question: str) -> str:
    while True:
        answer = input(f"{question}: ").strip()
        if answer:
            return answer
        print("  This can't be empty.")


def _ask_number(question: str) -> float:
    while True:
        answer = input(f"{question}: ").strip()
        try:
            return float(answer)
        except ValueError:
            print("  Please type a number.")


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

    aircraft_id = _pick_value(
        args.aircraft_id,
        pos_id,
        json_data,
        ["aircraft_id", "id"],
        interactive,
        lambda: _ask_text("Aircraft ID"),
        str,
    )
    if get_aircraft(conn, aircraft_id) is None:
        raise ValueError(f"radar has no aircraft {aircraft_id}")

    runway_id = _pick_value(
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

    aircraft_id = _pick_value(
        args.aircraft_id,
        pos_id,
        json_data,
        ["aircraft_id", "id"],
        interactive,
        lambda: _ask_text("Aircraft ID"),
        str,
    )
    if get_aircraft(conn, aircraft_id) is None:
        raise ValueError(f"radar has no aircraft {aircraft_id}")

    latitude = _pick_value(
        args.latitude,
        pos_latitude := args.pos_latitude,
        json_data,
        ["latitude", "lat"],
        interactive,
        lambda: _ask_number("Move to latitude"),
        float,
    )
    longitude = _pick_value(
        args.longitude,
        pos_longitude := args.pos_longitude,
        json_data,
        ["longitude", "lon", "lng"],
        interactive,
        lambda: _ask_number("Move to longitude"),
        float,
    )
    _ = (pos_latitude, pos_longitude)

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

    conflict_id = _pick_value(
        args.conflict_id,
        pos_cid,
        json_data,
        ["conflict_id", "id"],
        interactive,
        lambda: _ask_text("Conflict ID"),
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


def build_fake_parser() -> argparse.ArgumentParser:
    parser = _FakeArgumentParser(
        prog="python -m src.radar.airplane.fake_cli",
        description="Temporary shim CLI for fake-* test commands.",
        fromfile_prefix_chars="@",
    )
    parser.add_argument(
        "--db",
        default="radar.db",
        help="Path to SQLite database (default: radar.db)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_fake = subparsers.add_parser("fake-tower-reply", help="TESTING: simulate a runway reply from tower")
    _add_fake_common_flags(p_fake)
    p_fake.add_argument("pos_aircraft_id", nargs="?", metavar="AIRCRAFT_ID_OR_@JSON")
    p_fake.add_argument("pos_runway_id", nargs="?", metavar="RUNWAY_ID")
    p_fake.add_argument("--aircraft-id", "--id", dest="aircraft_id")
    p_fake.add_argument("--runway-id", "--runway", dest="runway_id")
    p_fake.set_defaults(func=cmd_fake_reply)

    p_sep = subparsers.add_parser(
        "fake-unsafe-separation",
        help="TESTING: simulate an UNSAFE_SEPARATION message from tower",
    )
    _add_fake_common_flags(p_sep)
    p_sep.add_argument("pos_aircraft_id", nargs="?", metavar="AIRCRAFT_ID_OR_@JSON")
    p_sep.add_argument("pos_latitude", nargs="?", type=float, metavar="LATITUDE")
    p_sep.add_argument("pos_longitude", nargs="?", type=float, metavar="LONGITUDE")
    p_sep.add_argument("--aircraft-id", "--id", dest="aircraft_id")
    p_sep.add_argument("--latitude", "--lat", dest="latitude", type=float)
    p_sep.add_argument("--longitude", "--lon", "--lng", dest="longitude", type=float)
    p_sep.set_defaults(func=cmd_fake_unsafe_separation)

    p_resolved = subparsers.add_parser(
        "fake-conflict-resolved",
        help="TESTING: simulate a CONFLICT_RESOLVED message from tower",
    )
    _add_fake_common_flags(p_resolved)
    p_resolved.add_argument("pos_conflict_id", nargs="?", metavar="CONFLICT_ID_OR_@JSON")
    p_resolved.add_argument("--conflict-id", "--id", dest="conflict_id")
    p_resolved.set_defaults(func=cmd_fake_conflict_resolved)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_fake_parser()
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