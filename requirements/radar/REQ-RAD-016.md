# REQ-RAD-016

The radar subsystem shall send tower the current data of an airplane on request.

- Given an aircraft ID, radar shall send tower that airplane's data from radar's database:
  ID, latitude, longitude, altitude (feet), status, runway, and timestamp.
- If radar has no airplane with that ID, nothing shall be sent.
