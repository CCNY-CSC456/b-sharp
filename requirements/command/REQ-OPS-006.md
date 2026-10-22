# REQ-OPS-006: Recorded Aircraft Coordinate Map

**Owning Team:** Command
**Subsystem:** Visibility

## Requirement

Command shall display aircraft at their recorded geographic coordinates around a centered, functioning airport runway schematic.

## Acceptance criteria

- `GET /api/aircraft` reads aircraft ID, latitude, longitude, altitude in feet, Radar status, and position timestamp from the local `radar.db` aircraft table. `COMMAND_RADAR_DB` overrides its checkout-root default path.
- Command opens Radar's database read-only. Missing or incomplete data returns HTTP 503 without creating or migrating the database. No Tower or Radar source is changed.
- Valid latitude / longitude values position aircraft on a north-up local coordinate plot centered on Tower's airport coordinates. Map width is selectable from 4 to 100 km. Aircraft outside that extent remain in the detail list and are counted; their markers are not clamped to false positions.
- The central airport and runways remain schematic, explicitly labeled as not to scale. Availability colors and assigned aircraft continue to come from Tower. A runway detail view expands the existing schematic.
- Markers show ID, altitude, and coordinates. The selectable detail list also shows full coordinates, recorded time, Radar status, and any matching Tower runway assignment.
- Aircraft at identical coordinates share a marker; selecting it cycles their labels. Every aircraft remains individually selectable in the list. Marker controls are keyboard accessible.
- Missing or invalid coordinates are omitted and counted. An unknown altitude is labeled unavailable, never converted to zero.
- The map shows stored positions and does not generate aircraft movement. Five-second refreshes read new coordinates and label retained snapshots stale after an outage. Radar, Tower, and messaging failures remain independent.
- Radar keeps rows after departure. Command may hide a row only when Radar's latest lifecycle message explicitly reports `DEPARTED`; a later request or telemetry message reactivates it. Lifecycle messages are read without consuming them, including `tower-READ` recipients. If that history cannot be read, stored positions remain visible with a warning. Missing Tower assignments do not imply departure or runway refusal.
