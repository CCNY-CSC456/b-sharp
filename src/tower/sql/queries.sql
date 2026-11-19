-- NOTE: these are from tower & specifically just airport_repo.py
----|                                 [ORD]                                 |-->

-- name: check_tables
SELECT name FROM sqlite_master WHERE type='table';

-- name: insert_airport
INSERT INTO airport VALUES (?, ?, ?, ?);

-- name: insert_runway
INSERT INTO runways (airport_id, runway_id, status, timestamp) VALUES (?, ?, ?, ?);

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

-- name: get_assignment_and_status
SELECT runway_id, status FROM runway_assignments WHERE airport_id = ? AND aircraft_id = ?;

-- name: update_assignment_status
UPDATE runway_assignments SET status = ? WHERE airport_id = ? AND aircraft_id = ?;

-- name: delete_assignment
DELETE FROM runway_assignments WHERE airport_id = ? AND aircraft_id = ?;

-- name: mark_message_processed
INSERT OR IGNORE INTO processed_messages (message_id) VALUES (?);

-- name: check_message_processed
SELECT 1 FROM processed_messages WHERE message_id = ?;

-- name: get_runway_status
SELECT r.runway_id, ra.aircraft_id, ra.status
FROM runways r
LEFT JOIN runway_assignments ra
    ON r.airport_id = ra.airport_id AND r.runway_id = ra.runway_id
WHERE r.airport_id = ?
ORDER BY r.runway_id;

-- name: get_sent_runway_status
SELECT runway_id, aircraft_id, phase FROM runway_status_sent WHERE airport_id = ?;

-- name: record_sent_runway_status
INSERT OR REPLACE INTO runway_status_sent (airport_id, runway_id, aircraft_id, phase) VALUES (?, ?, ?, ?);

-- name: clear_aircraft_positions
DELETE FROM aircraft_positions WHERE airport_id = ?;

-- name: insert_aircraft_position
INSERT INTO aircraft_positions
    (airport_id, aircraft_id, latitude, longitude, altitude, status, on_ground, requested_at, timestamp)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);

-- name: get_aircraft_positions
SELECT aircraft_id, latitude, longitude, altitude, status, on_ground, requested_at, timestamp
FROM aircraft_positions WHERE airport_id = ? ORDER BY aircraft_id;

-- name: get_separations
SELECT separation_id, aircraft_id, other_aircraft_id, move_to_latitude, move_to_longitude, status, opened_at, resolved_at
FROM separations WHERE airport_id = ? ORDER BY separation_id;

-- name: insert_separation
INSERT INTO separations (airport_id, aircraft_id, other_aircraft_id, move_to_latitude, move_to_longitude, status, opened_at)
VALUES (?, ?, ?, ?, ?, ?, ?);

-- name: set_separation_move_to
UPDATE separations SET move_to_latitude = ?, move_to_longitude = ?, status = 'OPEN'
WHERE airport_id = ? AND separation_id = ? AND status = 'WAITING';

-- name: close_separation
UPDATE separations SET status = ?, resolved_at = ?
WHERE airport_id = ? AND separation_id = ? AND status IN ('WAITING', 'OPEN');


-- NOTE extracted from the db file during refactor

-- name: old_schema
CREATE TABLE IF NOT EXISTS messages (sender TEXT, recipient TEXT, content TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP);

-- name: messages_schema
CREATE TABLE IF NOT EXISTS messages (
    sender    TEXT,
    recipient TEXT,
    content   TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    consumed  INTEGER DEFAULT 0,
    kind      INTEGER DEFAULT 0
);

-- name: save_message
INSERT INTO messages (sender, recipient, content) VALUES (?, ?, ?); -- TODO remove once confident in messaging refactor

-- name: send_message
INSERT INTO messages (sender, recipient, content, kind) VALUES (?, ?, ?, ?);


-- name: messages_columns
PRAGMA table_info(messages);

-- name: add_messages_consumed
ALTER TABLE messages ADD COLUMN consumed INTEGER DEFAULT 0;

-- name: add_messages_kind
ALTER TABLE messages ADD COLUMN kind INTEGER DEFAULT 0;

-- name: increment_consumed
UPDATE messages SET consumed = consumed + 1 WHERE rowid = ?;

-- name: default_retrieve
SELECT rowid, sender, recipient, content FROM messages WHERE recipient = ?;

-- name: enhanced_retrieve
SELECT rowid, sender, recipient, content FROM messages WHERE recipient = ? AND consumed = 0;



-- REQ-TOW-014: the saved runway queue and the reply outbox (scheduler.py)

-- name: get_request_queue
SELECT queue_id, aircraft_id, req_type, req_timestamp, msg_key, position, created_at
FROM runway_request_queue
WHERE airport_id = ?
ORDER BY position ASC, queue_id ASC;

-- name: insert_request_queue
INSERT INTO runway_request_queue (airport_id, aircraft_id, req_type, req_timestamp, msg_key, position, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?);

-- name: delete_request_queue_by_aircraft
DELETE FROM runway_request_queue WHERE airport_id = ? AND aircraft_id = ?;

-- name: replace_request_queue
DELETE FROM runway_request_queue WHERE airport_id = ?;

-- name: get_response_queue
SELECT response_id, target, payload_json, created_at
FROM runway_response_queue
WHERE airport_id = ?
ORDER BY response_id ASC;

-- name: insert_response_queue
INSERT INTO runway_response_queue (airport_id, target, payload_json, created_at)
VALUES (?, ?, ?, ?);

-- name: delete_response_queue_item
DELETE FROM runway_response_queue WHERE response_id = ? AND airport_id = ?;



-- name: get_conflicts
SELECT conflict_id, aircraft_id, reason, first_reported_at, spots, status, opened_at, resolved_at
FROM conflicts WHERE airport_id = ? ORDER BY conflict_id;

-- name: insert_conflict
INSERT INTO conflicts (airport_id, aircraft_id, reason, first_reported_at, spots, status, opened_at)
VALUES (?, ?, ?, ?, ?, 'PENDING', ?);

-- name: resolve_conflict
UPDATE conflicts SET status = 'RESOLVED', resolved_at = ?
WHERE airport_id = ? AND conflict_id = ? AND status = 'PENDING';



-- unvalidated


-- name: insert_airport
INSERT INTO airport (airport_id, perimeter, latitude, longitude, runway_count)
VALUES (?, ?, ?, ?, ?);

-- name: seed_runways_from_airport
WITH RECURSIVE seq(n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1
    FROM seq, airport
    WHERE airport.airport_id = ?
      AND n < airport.runway_count
)
INSERT OR IGNORE INTO runways (airport_id, runway_id, status, timestamp, aircraft_id)
SELECT ?, n, 'Available', ?, NULL
FROM seq;

-- name: update_airport_runway_count
UPDATE airport
SET runway_count = ?
WHERE airport_id = ?;


-- name: sync_runways_up
WITH RECURSIVE seq(n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1
    FROM seq, airport
    WHERE airport.airport_id = ?
      AND n < airport.runway_count
)
INSERT OR IGNORE INTO runways (airport_id, runway_id, status, timestamp, aircraft_id)
SELECT ?, n, 'Available', ?, NULL
FROM seq;

-- name: trim_excess_runways
DELETE FROM runways
WHERE airport_id = ?
  AND runway_id > (
      SELECT runway_count FROM airport WHERE airport_id = ?
  )
  AND NOT EXISTS (
      SELECT 1
      FROM runway_assignments ra
      WHERE ra.airport_id = runways.airport_id
        AND ra.runway_id = runways.runway_id
  );

-- name: last_runway_resync
SELECT COUNT(*) FROM runways WHERE airport_id = ?;

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













