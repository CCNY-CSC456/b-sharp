# REQ-TOW-007

The tower subsystem shall assign an available runway to an airplane.

- Tower shall give the airplane an "Available" runway, if there is one.
- The assigned runway shall become "Not Available", record the airplane's ID, and update its timestamp.
- If no runway is available, tower shall assign nothing and report that no runway was assigned.
- An airplane that already has a runway shall get the same runway again, not a second one.
- Two airplanes shall never be assigned the same runway.
