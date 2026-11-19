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

-- Dynamic assignments (1:1 per-airport constraint between runway and aircraft)
CREATE TABLE IF NOT EXISTS runway_assignments (
    airport_id TEXT NOT NULL,
    runway_id INTEGER NOT NULL,
    aircraft_id TEXT NOT NULL,
    status TEXT CHECK(status IN ('LANDING_ASSIGNED', 'LANDED', 'TAKEOFF_ASSIGNED')),
    assigned_at TEXT NOT NULL,
    PRIMARY KEY (airport_id, runway_id),
    UNIQUE (airport_id, aircraft_id) -- having them be indivudally unique prevented multiple airports from existing
);

-- REQ-TOW-012: what tower last told command about each runway, so only changes are sent.
CREATE TABLE IF NOT EXISTS runway_status_sent (
    airport_id TEXT NOT NULL,
    runway_id INTEGER NOT NULL,
    aircraft_id TEXT,
    phase TEXT,
    PRIMARY KEY (airport_id, runway_id)
);

-- REQ-TOW-013: each airborne-or-grounded plane's latest known position, rebuilt from radar's messages every run.
-- on_ground is 1 after radar reports LANDED or PARKED, or when altitude is 0 or status is Parked.
-- requested_at is when the plane last asked for a runway (NULL if it never has); it decides who moves.
CREATE TABLE IF NOT EXISTS aircraft_positions (
    airport_id TEXT NOT NULL,
    aircraft_id TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    altitude REAL NOT NULL,
    status TEXT,
    on_ground INTEGER NOT NULL CHECK(on_ground IN (0, 1)),
    requested_at TEXT,
    timestamp TEXT,
    PRIMARY KEY (airport_id, aircraft_id)
);

-- REQ-TOW-013: one row per unsafe separation, never deleted (it is also the history).
-- aircraft_id is the plane that moves; other_aircraft_id stays where it is.
-- WAITING  = too close, but no clear spot yet (radar not told)
-- OPEN     = radar told to move aircraft_id to move_to_latitude / move_to_longitude
-- RESOLVED = radar said it moved (or the planes stopped being too close while WAITING)
-- CANCELLED = one of the planes landed, parked, or departed first
CREATE TABLE IF NOT EXISTS separations (
    separation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    airport_id TEXT NOT NULL,
    aircraft_id TEXT NOT NULL,
    other_aircraft_id TEXT NOT NULL,
    move_to_latitude REAL,
    move_to_longitude REAL,
    status TEXT NOT NULL CHECK(status IN ('WAITING', 'OPEN', 'RESOLVED', 'CANCELLED')),
    opened_at TEXT NOT NULL,
    resolved_at TEXT
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


-- unverified
CREATE TABLE IF NOT EXISTS runway_request_queue (
    queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
    airport_id TEXT NOT NULL,
    aircraft_id TEXT NOT NULL,
    req_type TEXT NOT NULL CHECK(req_type IN ('REQUEST_LANDING', 'REQUEST_TAKEOFF')),
    req_timestamp TEXT,
    msg_key TEXT NOT NULL,
    position INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (airport_id, aircraft_id)
);

CREATE TABLE IF NOT EXISTS runway_response_queue (
    response_id INTEGER PRIMARY KEY AUTOINCREMENT,
    airport_id TEXT NOT NULL,
    target TEXT NOT NULL CHECK(target IN ('radar', 'command')),
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
