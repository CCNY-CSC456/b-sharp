CREATE TABLE IF NOT EXISTS airport (
    airport_id TEXT PRIMARY KEY,
    perimeter REAL,
    latitude REAL,
    longitude REAL
);

-- The airport's runways (10, created with the airport). Who is ON a runway lives in runway_assignments.
-- status and aircraft_id are from before runway_assignments existed: tower no longer changes them
-- (status stays 'Available'), but they stay because command's dashboard still reads this table.
CREATE TABLE IF NOT EXISTS runways (
    airport_id TEXT,
    runway_id INTEGER,
    status TEXT CHECK(status IN ('Available','Not Available')),
    timestamp TEXT,
    aircraft_id TEXT,
    PRIMARY KEY (airport_id, runway_id)
);

-- Messages tower has already handled (the shared inbox never forgets), as "aircraft:type:timestamp" keys.
CREATE TABLE IF NOT EXISTS processed_messages (
    message_id TEXT PRIMARY KEY
);

-- Who is on which runway, and in which phase. A row exists only while a plane holds a runway; a free
-- runway has no row. One plane per runway and one runway per plane, per airport.
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
