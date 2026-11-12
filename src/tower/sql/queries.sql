-- NOTE: these are from tower & specifically just airport_repo.py
----|                                 [ORD]                                 |-->

-- name: check_tables
SELECT name FROM sqlite_master WHERE type='table';

-- name: insert_airport
INSERT INTO airport VALUES (?, ?, ?, ?);

-- name: insert_runway
INSERT INTO runways (airport_id, runway_id, status, timestamp) VALUES (?, ?, ?, ?);

-- name: get_runway_by_aircraft
SELECT runway_id FROM runways WHERE airport_id = ? AND aircraft_id = ?;

-- name: find_available_runway
SELECT runway_id FROM runways WHERE airport_id = ? AND status = 'Available' ORDER BY runway_id LIMIT 1;

-- name: lock_runway
UPDATE runways SET status = 'Not Available', aircraft_id = ?, timestamp = ? WHERE airport_id = ? AND runway_id = ? AND status = 'Available';

-- name: free_runway_record
UPDATE runways SET status = 'Available', aircraft_id = NULL, timestamp = ? WHERE airport_id = ? AND runway_id = ?;

-- name: find_available_runway_joint
SELECT r.runway_id
FROM runways r
LEFT JOIN runway_assignments ra
    ON r.airport_id = ra.airport_id AND r.runway_id = ra.runway_id
WHERE r.airport_id = ?
  AND r.status = 'Available'
  AND ra.runway_id IS NULL
ORDER BY r.runway_id
LIMIT 1;

-- name: insert_runway_assignment
INSERT INTO runway_assignments (airport_id, runway_id, aircraft_id, status, assigned_at) VALUES (?, ?, ?, ?, ?);

-- name: get_assignment
SELECT runway_id FROM runway_assignments WHERE airport_id = ? AND aircraft_id = ?;

-- name: update_assignment_status
UPDATE runway_assignments SET status = ? WHERE airport_id = ? AND aircraft_id = ?;

-- name: delete_assignment
DELETE FROM runway_assignments WHERE airport_id = ? AND aircraft_id = ?;

-- name: mark_message_processed
INSERT OR IGNORE INTO processed_messages (message_id) VALUES (?);

-- name: check_message_processed
SELECT 1 FROM processed_messages WHERE message_id = ?;

----|                                 [END]                                 |-->


-- NOTE: from radar at large
----|                                 [ORD]                                 |-->

-- NOTE: AirplaneAircraftrepoStrings

-- NOTE: the RDR_A_00 query is really a schema, eventually goes in radar/schemas

-- name: RDR_A_00
CREATE TABLE IF NOT EXISTS aircraft (aircraft_id TEXT PRIMARY KEY, latitude REAL, longitude REAL, altitude REAL, status TEXT CHECK(status IN ('Parked','Departing','Landing')), timestamp TEXT, runway_id TEXT);

-- name: RDR_A_01
INSERT INTO aircraft (aircraft_id, latitude, longitude, altitude, status, timestamp, runway_id) VALUES (?, ?, ?, ?, ?, ?, ?);

-- name: RDR_A_02
SELECT aircraft_id, latitude, longitude, altitude, status, timestamp, runway_id FROM aircraft WHERE aircraft_id = ?;

-- name: RDR_A_03
UPDATE aircraft SET runway_id = ?, timestamp = ? WHERE aircraft_id = ?;

-- name: RDR_A_04
DELETE FROM aircraft WHERE aircraft_id = ?;

-- name: RDR_A_05
UPDATE aircraft SET altitude = ?, timestamp = ? WHERE aircraft_id = ?;



-- NOTE: AirplanemainStrings

-- name: RDR_B_06
SELECT aircraft_id, latitude, longitude, altitude, status, timestamp, runway_id FROM aircraft;


----|                                 [END]                                 |-->


-- NOTE: from command at large
----|                                 [ORD]                                 |-->

-- NOTE: AirportStrings

-- name: CMD_A_00
SELECT airport_id, perimeter, latitude, longitude FROM airport WHERE airport_id = ?;

-- name: CMD_A_01
SELECT * FROM runways WHERE airport_id = ? ORDER BY runway_id;

-- name: CMD_A_02
SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'runway_assignments';

-- name: CMD_A_03
SELECT runway_id, aircraft_id, status, assigned_at FROM runway_assignments WHERE airport_id = ?;


-- NOTE: MessagesStrings

-- name: CMD_B_04
SELECT rowid, sender, content FROM messages WHERE recipient IN (?, ?) ORDER BY rowid DESC LIMIT 100;


-- NOTE: AircraftStrings

-- name: CMD_C_05
SELECT content FROM messages WHERE sender = 'radar' AND recipient IN ('tower', 'tower-READ') ORDER BY rowid DESC;

-- name: CMD_C_06
SELECT aircraft_id, latitude, longitude, altitude, status, timestamp FROM aircraft ORDER BY aircraft_id;

----|                                 [END]                                 |-->













