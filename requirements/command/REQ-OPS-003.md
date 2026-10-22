# REQ-OPS-003: Airfield Color Palette

**Owning Team:** Command
**Subsystem:** Visibility

## Requirement

The Command dashboard shall use the Airfield color palette on a charcoal background.

## Acceptance criteria

- The page background is a flat charcoal (`#1c1d1f`) with no color tint.
- `Available` runway status is green (`#6fd08c`) in the runway list.
- `Not Available` runways are violet (`#b18cff`) on the map and in the runway list.
- Warnings and errors (degraded data links, unavailable data, a failed send) are red (`#ff6b6b`).
- The Send button, logo mark, and input focus ring are light gray (`#d6d6d2`).
- Every color is defined once as a token in the page's `:root` style block. No other style rule uses a literal hex color.
- Text colors have a contrast ratio of at least 4.5:1 against the panels they appear on.
- Layout, text, and behavior are unchanged. This is a styles only change.

## Notes

- Sky blue (`#5ab4ff`) and amber (`#ffb02e`) are reserved for arriving and departing planes, which a later requirement adds. They are not used here, so status colors never mean two things.
