# REQ-OPS-004: Dashboard Layout

**Owning Team:** Command
**Subsystem:** Visibility

## Requirement

The Command dashboard shall show a single header row and three side by side panels: the airport map, runway availability, and Tower messages.

## Acceptance criteria

- The page heading reads "b-sharp ATC Midterm Demo".
- The header row shows Coordinates, Perimeter, Runways, and Latest update · UTC next to the heading.
  - Coordinates use the form `40.6413° N / 73.7781° W`.
  - Perimeter shows Tower's number as is, labeled "demo units", with no conversion.
  - Latest update is the newest runway timestamp.
- There is no separate Airport ID card. The airport ID stays visible as the map's label (for example "DEMO-001 / Airport"), so REQ-OPS-001 is still met.
- On wide screens the three panels sit side by side in this order: the airport map (widest), runway availability, and Tower messages.
- On medium screens the map spans the full width, with runway availability and Tower messages side by side below it. On phones all three stack in the same order.
- Runway availability lists all 10 runways in one column, with a summary such as "9 available / 1 not available". Each runway keeps its ID, status, and full `yyyy-mm-ddTHH:MM:SS` timestamp (REQ-OPS-001).
- Tower messages keep the inbox and the send form (REQ-OPS-002). The send button reads "Send to Tower".
- The element IDs that REQ-OPS-001 and REQ-OPS-002 tests rely on are kept, and the REQ-OPS-003 colors are unchanged.
- No data, polling, or messaging behavior changes. This is a layout and labels only change.
