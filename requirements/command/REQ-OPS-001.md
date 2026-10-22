# REQ-OPS-001: Command Visibility Dashboard

**Owning Team:** Command
**Subsystem:** Visibility

## Requirement

The Command subsystem shall show the current airport system state in a single unified dashboard.

## Acceptance criteria

- The dashboard shows a square airport perimeter with runway boxes inside it.
- Airport ID, perimeter, latitude, longitude, and runway count are visible.
- Each runway shows its ID, availability status, and timestamp in `yyyy-mm-ddTHH:MM:SS` format.
- Fields come from Tower's airport model: a numeric perimeter, all configured runways, and statuses `Available` or `Not Available`.
- The dashboard includes Tower messaging as specified by REQ-OPS-002.
- Airport data comes from a replaceable, read-only data-access function backed by Tower's local database (REQ-OPS-005).
- If airport or messaging data cannot be loaded, the dashboard shows a degraded state and a useful message.
- The database source and timestamp semantics are documented; the schematic shows aircraft at assigned runways and does not claim geographic position or process liveness.
