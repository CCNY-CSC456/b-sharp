# REQ-TOW-006

The tower subsystem shall create an airport and store it with its runways.

- An airport has an ID, perimeter, latitude, and longitude.
- An airport has 10 runways.
- A runway has an ID, a status, and a timestamp.
- Status shall be one of "Available" or "Not Available". New runways start as "Available".
- Timestamps shall use the format "yyyy-mm-ddTHH:MM:SS".
- Two airports shall not share the same ID.
- Creating the tables and creating an airport shall each report success (True) or failure (False).
