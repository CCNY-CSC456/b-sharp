| ID | Team | Description | Code | Tests | Metrics |
|----|----|----|----|----|----|
| REQ-TOW-005 | Tower | Message Sending Utility | src/tower/messaging/ | tests/tower/test_messaging.py | |
| REQ-RAD-012 | Radar | Create Airplane | src/radar/airplane/ | tests/radar/test_aircraft_repo.py | |
| REQ-TOW-006 | Tower | Create Airport | src/tower/airport/ | tests/tower/test_airport_repo.py | |
| REQ-OPS-001 | Command | Unified airport visibility dashboard | src/command/dashboard.py, src/command/airport.py | tests/command/test_airport.py, tests/command/test_dashboard.py | |
| REQ-OPS-002 | Command | Tower messaging in the dashboard | src/command/dashboard.py | tests/command/test_dashboard.py | |
| REQ-RAD-013 | Radar | Integration with Tower | src/radar/airplane/runway_requests.py | tests/radar/test_runway_requests.py | |
| REQ-TOW-014 | Tower | Persistent Polling Process Loop | | |