"""REQ-OPS-005: read Tower's airport and aircraft assignments without writing to Tower."""

from contextlib import closing
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def get_airport_state():
    """Read a consistent snapshot from Tower's current or proposed schema.

    COMMAND_TOWER_DB selects a different local database. The default is tower.db
    in this checkout's root, independent of Command's working directory. Missing
    databases are errors; Command never creates or seeds Tower's airport data.
    """
    path = Path(os.environ.get("COMMAND_TOWER_DB", str(REPOSITORY_ROOT / "tower.db"))).expanduser().resolve()
    airport_id = os.environ.get("COMMAND_AIRPORT_ID", "DEMO-001")
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN")  # Read the tables from one consistent snapshot.
        airport = conn.execute(
            "SELECT airport_id, perimeter, latitude, longitude FROM airport WHERE airport_id = ?",
            (airport_id,),
        ).fetchone()
        if airport is None:
            raise sqlite3.OperationalError("The configured airport is not available")
        rows = conn.execute(
            "SELECT * FROM runways WHERE airport_id = ? ORDER BY runway_id", (airport_id,)
        ).fetchall()
        if not rows:
            raise sqlite3.OperationalError("The configured airport has no runway data")
        has_assignments = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'runway_assignments'"
        ).fetchone() is not None
        assignments = {}
        if has_assignments:
            assignments = {
                row["runway_id"]: dict(row)
                for row in conn.execute(
                    "SELECT runway_id, aircraft_id, status, assigned_at FROM runway_assignments "
                    "WHERE airport_id = ?", (airport_id,)
                )
            }

        runways = []
        for row in rows:
            runway = dict(row)
            if has_assignments:
                assignment = assignments.get(runway["runway_id"])
                # Assignments own aircraft occupancy; runways still own base availability.
                aircraft_id = assignment["aircraft_id"] if assignment else None
                assignment_status = assignment["status"] if assignment else None
                assigned_at = assignment["assigned_at"] if assignment else None
                status = "Not Available" if assignment else runway["status"]
            else:
                aircraft_id = runway.get("aircraft_id")
                assignment_status = None  # Legacy data cannot tell assigned from landed.
                assigned_at = None
                status = runway["status"]
            runways.append({
                "runway_id": runway["runway_id"],
                "status": status,
                "timestamp": runway["timestamp"],
                "aircraft_id": aircraft_id,
                "assignment_status": assignment_status,
                "assigned_at": assigned_at,
            })

    snapshot = dict(airport)
    snapshot.update(
        number_of_runways=len(runways),
        runways=runways,
        assignment_source="runway_assignments" if has_assignments else "legacy_runways",
        observed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    return snapshot
