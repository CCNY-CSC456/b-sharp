CREATE TABLE IF NOT EXISTS airport (
    airport_id TEXT PRIMARY KEY,
    perimeter REAL,
    latitude REAL,
    longitude REAL
);

CREATE TABLE IF NOT EXISTS runways (
    airport_id TEXT,
    runway_id INTEGER,
    status TEXT CHECK(status IN ('Available','Not Available')),
    timestamp TEXT,
    aircraft_id TEXT,
    PRIMARY KEY (airport_id, runway_id)
);

CREATE TABLE IF NOT EXISTS processed_messages (
    message_id TEXT PRIMARY KEY
);

-- Dynamic assignments (1:1 constraint between runway and aircraft)
CREATE TABLE IF NOT EXISTS runway_assignments (
    airport_id TEXT NOT NULL,
    runway_id INTEGER NOT NULL UNIQUE,
    aircraft_id TEXT NOT NULL UNIQUE,
    status TEXT CHECK(status IN ('LANDING_ASSIGNED', 'LANDED', 'TAKEOFF_ASSIGNED')),
    assigned_at TEXT NOT NULL,
    PRIMARY KEY (airport_id, runway_id)
);

CREATE VIEW IF NOT EXISTS runway_assignments_json AS
SELECT json_pretty(
    json_group_array(
        json_object(
            'airport_id', airport_id,
            'runway_id', runway_id,
            'aircraft_id', aircraft_id,
            'status', status,
            'assigned_at', assigned_at
        )
    )
) AS json_dump
FROM runway_assignments;

CREATE TABLE IF NOT EXISTS ACTIVE (
    aircraft_id TEXT PRIMARY KEY,
    latitude REAL,
    longitude REAL,
    altitude REAL,
    status TEXT CHECK(status IN ('Parked','Departing','Landing')),
    timestamp TEXT,
    runway_id TEXT
);