# REQ-RAD-012

The radar subsystem shall create an airplane, store it, and send its data to tower.

- An airplane has an ID, latitude, longitude, altitude (feet), status, and timestamp.
- Status shall be one of "Parked", "Departing", or "Landing".
- Timestamps shall use the format "yyyy-mm-ddTHH:MM:SS".
- Two airplanes shall not share the same ID.
- Creating an airplane shall send its data to tower through the messaging service.
