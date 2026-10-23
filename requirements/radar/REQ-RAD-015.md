# REQ-RAD-015

The radar subsystem shall change the altitude of an existing airplane.

- Radar shall set a new altitude (feet) for an airplane by its ID.
- Altitude shall not be negative.
- Changing the altitude shall refresh the airplane's timestamp.
- Changing the altitude of an airplane that does not exist shall be rejected.
- After the altitude is changed, radar shall send tower the airplane's updated data
  (the AIRCRAFT_INFO message from REQ-RAD-016). If the change is rejected, nothing shall be sent.
