# REQ-RAD-013

The radar subsystem shall request runways from tower and store the runway tower assigns.

- Radar shall send tower a request for a runway to land (arrivals).
- Radar shall send tower a request for a runway to take off (departures).
- Radar shall receive tower's replies: runway assigned (with a runway ID) or no runway available.
- When a runway is assigned, radar shall update the airplane with that runway ID.
