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