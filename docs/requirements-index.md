| ID | Team | Description | Code | Tests | Metrics |
|----|----|----|----|----|----|
| REQ-TOW-005 | Tower | Message Sending Utility | src/tower/messaging/ | tests/tower/test_messaging.py | |
| REQ-RAD-012 | Radar | Create Airplane | src/radar/airplane/ | tests/radar/test_aircraft_repo.py | |
| REQ-TOW-006 | Tower | Create Airport | src/tower/airport/ | tests/tower/test_airport_repo.py | |
| REQ-OPS-001 | Command | Unified airport visibility dashboard | src/command/dashboard.py, src/command/airport.py | tests/command/test_airport.py, tests/command/test_dashboard.py | |
| REQ-OPS-002 | Command | Tower messaging in the dashboard | src/command/dashboard.py | tests/command/test_dashboard.py | |
| REQ-RAD-013 | Radar | Integration with Tower | src/radar/airplane/runway_requests.py | tests/radar/test_runway_requests.py | |
| REQ-TOW-007 | Tower | Assign Runway | src/tower/airport/airport_repo.py | tests/tower/test_assign_runway.py | |
| REQ-TOW-008 | Tower | Answer Radar Runway Requests | src/tower/airport/runway_requests.py, src/tower/airport/__main__.py | tests/tower/test_answer_requests.py | |
| REQ-RAD-014 | Radar | Report Landed/Departed to Tower | src/radar/airplane/runway_requests.py, src/radar/airplane/aircraft_repo.py | tests/radar/test_landed_departed.py | |
| REQ-TOW-010 | Tower | Free Runway | src/tower/airport/airport_repo.py | tests/tower/test_free_runway.py | |
| REQ-TOW-011 | Tower | Takeoff Clearance and Departures | src/tower/airport/runway_requests.py, src/tower/airport/__main__.py | tests/tower/test_departures.py | |
| REQ-OPS-003 | Command | Airfield color palette | src/command/dashboard.html, src/command/dashboard.py | tests/command/test_palette.py | |
| REQ-OPS-004 | Command | Dashboard layout: header row and three panels | src/command/dashboard.html, src/command/dashboard.py | tests/command/test_layout.py | |
| REQ-OPS-005 | Command | Read local Tower state and display assigned aircraft | src/command/airport.py, src/command/messages.py, src/command/dashboard.py, src/command/dashboard.html | tests/command/test_airport.py, tests/command/test_dashboard.py | |
| REQ-OPS-006 | Command | Recorded aircraft coordinates around a centered runway schematic | src/command/aircraft.py, src/command/dashboard.py, src/command/dashboard.html | tests/command/test_aircraft.py | |
| REQ-RAD-015 | Radar | Change Aircraft Altitude | src/radar/airplane/aircraft_repo.py, src/radar/airplane/__main__.py | tests/radar/test_altitude.py | |
| REQ-RAD-016 | Radar | Send Aircraft Info to Tower | src/radar/airplane/runway_requests.py, src/radar/airplane/__main__.py | tests/radar/test_aircraft_info.py | |
