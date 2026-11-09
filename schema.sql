PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS fields (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    area_ha REAL NOT NULL,
    crop TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trucks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    capacity_kg REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS reconciled_unloads (
    id TEXT PRIMARY KEY,
    field_id TEXT NOT NULL,
    truck_id TEXT NOT NULL,
    crop TEXT NOT NULL,
    weight_kg REAL NOT NULL,
    unloaded_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    resolution_notes TEXT,
    FOREIGN KEY (field_id) REFERENCES fields(id),
    FOREIGN KEY (truck_id) REFERENCES trucks(id)
);

CREATE TABLE IF NOT EXISTS unresolved_unloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    unload_id TEXT,
    source TEXT NOT NULL,
    raw_payload TEXT NOT NULL,
    reason TEXT NOT NULL,
    logged_at TEXT DEFAULT CURRENT_TIMESTAMP
);