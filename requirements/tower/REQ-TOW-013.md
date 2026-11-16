# REQ-TOW-013

The tower subsystem shall detect airborne airplanes that are too close and tell radar exactly where to move one of them.

## When two airplanes are too close

- Two airborne airplanes are too close when they are less than SEPARATION_DEGREES (0.10 degrees) apart in latitude
  AND less than 0.10 degrees in longitude AND less than SEPARATION_FEET (1000 ft) apart in altitude.
  Exactly at a limit counts as safe. Both limits are variables so they can be changed.
- Altitude is in feet, as radar sends it.
- An airplane is on the ground, and ignored, after radar reports it LANDED or PARKED (until it departs), or when
  its altitude is 0 or its status is Parked. A DEPARTED airplane is removed.
- Tower keeps each airplane's latest known position in the aircraft_positions table, built from radar's messages.

## Which airplane moves, and where

- If only one of the two holds a runway, the other one moves.
- Otherwise the airplane later in the queue moves: the one that asked for a runway later. An airplane that has not
  asked counts as later than one that has. A tie goes to the higher aircraft ID.
- An airplane already told to move (or waiting for a spot) is not picked again.
- Tower tries 8 spots (N, NE, E, SE, S, SW, W, NW) 0.11 degrees from the airplane that stays, and throws out any
  spot too close to another airplane, counting airplanes at the spots tower has already sent but radar has not
  confirmed. Of the spots left, the one closest to the moving airplane is sent; ties go in the order above.
  If none is clear, tower tries twice as far (0.22 degrees). The moving airplane keeps its altitude.
- Coordinates are rounded to 4 decimal places.
- If no spot is clear, the event is WAITING: command is told (with no coordinates) and radar is not.
  Tower looks again on each run and tells radar once a spot is clear. If the airplanes stop being too close
  first, the event is RESOLVED.

## Messages

- Tower to radar, once per event:
  `{"type": "UNSAFE_SEPARATION", "separation_id": 7, "aircraft_id": "B2", "other_aircraft_id": "A1",
  "move_to_latitude": 40.81, "move_to_longitude": -73.80, "timestamp": "2026-11-15T14:00:00"}`
  aircraft_id moves to the move_to coordinates; other_aircraft_id stays where it is.
- Radar to tower, when it has moved the airplane:
  `{"type": "UNSAFE_SEPARATION_RESOLVED", "separation_id": 7, "aircraft_id": "B2", "timestamp": "..."}`
  Tower trusts radar and treats the airplane as at the move_to spot until radar sends a newer position.
  A message with an unknown separation_id, or from an airplane that was not told to move, is ignored.
- Tower to command: the same UNSAFE_SEPARATION message plus `"severity": 1` (with null move_to coordinates while
  WAITING, and again with coordinates once a spot is found), and when the event is over:
  `{"type": "UNSAFE_SEPARATION_RESOLVED", "separation_id": 7, "severity": 1, "aircraft_id": "B2",
  "other_aircraft_id": "A1", "timestamp": "..."}`
- No message shall be sent twice for the same event.

## Recording

- Every event is a row in the separations table and is never deleted. Its status is WAITING (no spot yet), OPEN
  (radar told to move), RESOLVED (radar moved it, or the airplanes drifted apart while WAITING), or CANCELLED
  (one of the airplanes landed, parked, or departed first). Command is told the event is resolved in both of the
  last two cases.
