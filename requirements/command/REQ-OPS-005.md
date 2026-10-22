# REQ-OPS-005: Local Tower State and Aircraft Visibility

**Owning Team:** Command
**Subsystem:** Visibility

## Requirement

Command shall read Tower's local airport database and show assigned aircraft on its unified dashboard, without changing Tower's source or database schema.

## Acceptance criteria

- `GET /api/airport` reads the configured airport and all of its runways from `tower.db` using a read-only SQLite connection and a consistent read transaction.
- `COMMAND_TOWER_DB` overrides the database path, and `COMMAND_AIRPORT_ID` overrides the airport ID (default `DEMO-001`). The default database path is the checkout root, independent of the working directory.
- If `runway_assignments` exists, it is authoritative for aircraft occupancy. Empty assignments leave all runways visible and remove previously displayed aircraft. A runway remains `Not Available` if it has an assignment or Tower's base runway status is `Not Available`.
- If the assignments table does not exist, Command uses Tower's current `runways` fields and shows an unknown aircraft phase rather than inventing landing/takeoff state.
- The map and runway cards show assigned aircraft IDs, with readable `LANDING_ASSIGNED`, `LANDED`, and `TAKEOFF_ASSIGNED` labels where provided.
- `assigned_at` means assignment time. It is not presented as the time of the latest state transition. Tower's timestamps are displayed without inventing a timezone; `observed_at` separately records Command's read time in UTC.
- A missing, locked, incomplete, or unreadable airport database returns HTTP 503 without creating or seeding it. The page and messaging remain usable.
- After a failed refresh, the last successful snapshot is visibly labeled stale. A later successful refresh clears that warning.
- Browser refreshes do not overlap and continue every five seconds.
- `/api/command-messages` reads the most recent 100 Command messages without marking them read. It includes both `command` and `command-READ` recipients and preserves distinct messages with identical text.
- The table currently represents assigned aircraft only. Command does not infer no-runway results, parked aircraft, geographic flight positions, or Tower process liveness from missing assignment rows.
