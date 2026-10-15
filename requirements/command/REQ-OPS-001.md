# REQ-OPS-001: Command Visibility Dashboard

**Owning Team:** Command
**Subsystem:** Visibility

## Requirement

The Command subsystem shall show the current airport system state in a single unified dashboard.

## Acceptance criteria

- The dashboard shows a square airport perimeter with runway boxes inside it.
- Airport ID, perimeter, latitude, longitude, and runway count are visible.
- Each runway shows its ID, availability status, and timestamp in `yyyy-mm-ddTHH:MM:SS` format.
- Demo fields match Tower's existing airport model: a numeric perimeter, runways numbered 1 through 10, and statuses `Available` or `Not Available`.
- The dashboard includes Tower messaging as specified by REQ-OPS-002.
- Airport data comes from a replaceable data-access function backed by hard-coded demo data for this version.
- If airport or messaging data cannot be loaded, the dashboard shows a degraded state and a useful message.
- The demo data source and UTC timestamp semantics are documented; the schematic does not claim geographic accuracy or live Tower synchronization.
