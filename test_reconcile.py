import sqlite3
import pytest
from main import normalize_record, process_unloads, init_db

@pytest.fixture
def test_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Create schema tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reconciled_unloads (
            id TEXT PRIMARY KEY,
            field_id TEXT NOT NULL,
            truck_id TEXT NOT NULL,
            crop TEXT NOT NULL,
            weight_kg REAL NOT NULL,
            unloaded_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            resolution_notes TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS unresolved_unloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unload_id TEXT,
            source TEXT NOT NULL,
            raw_payload TEXT NOT NULL,
            reason TEXT NOT NULL,
            logged_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    yield conn

def test_normalize_controller_record():
    """Test that controller records correctly map their weight and keys."""
    raw = {
        "id": "test-id",
        "field_id": "field-A",
        "truck_id": "truck-1",
        "crop": "wheat",
        "weight": 4500.0,
        "unloaded_at": "2026-10-15 09:00:00",
        "updated_at": "2026-10-15 09:30:00"
    }

    active = [{
        "id": "test-id",
        "field_id": "field-A",
        "truck_id": "truck-1",
        "crop": "wheat",
        "weight_kg": 4500.0,
        "unloaded_at": "2026-10-15T10:00:00-05:00",
        "updated_at": "2026-10-15T10:30:00-05:00",
        "trashed_at": None
    }]
    normalized_controller = normalize_record(raw, active, "controller")
    normalized_cloud = normalize_record(active[0], active, "cloud")

    assert normalized_controller == normalized_cloud
    
    assert normalized_controller["id"] == "test-id"
    assert normalized_controller["weight_kg"] == 4500.0
    assert "T" in normalized_controller["unloaded_at"] 

def test_duplicate_controller_unload_routing(test_db, monkeypatch):
    """Test that duplicate controller unloads sharing the same timestamp, field, and truck are routed to unresolved_unloads."""
    import io
    import json
    import main
    import builtins

    # Define mock dataset where one controller record matches the cloud, 
    # and a second controller record attempts to record the exact same unload 2 seconds later with a new ID.
    mock_cloud_data = [{
        "id": "1dccaaf4-fe5d-486c-be70-e2e0050c7be1",
        "field_id": "64d1fc80-38fa-4c1e-b13e-b833119151cb",
        "truck_id": "4a861507-1003-4528-9ea6-9f9b7370ae32",
        "crop": "wheat",
        "weight_kg": 9279.4,
        "unloaded_at": "2026-09-15T09:47:00-05:00",
        "updated_at": "2026-09-15T09:47:05-05:00",
        "trashed_at": None
    }]

    mock_controller_data = [{
        "id": "1dccaaf4-fe5d-486c-be70-e2e0050c7be1",
        "field_id": "64d1fc80-38fa-4c1e-b13e-b833119151cb",
        "truck_id": "4a861507-1003-4528-9ea6-9f9b7370ae32",
        "crop": "wheat",
        "weight": 9279.4,
        "unloaded_at": "2026-09-15 08:47:00",
        "updated_at": "2026-09-15 08:47:05",
        "unit": "kg"
    }, 
    {
        "id": "361111e6-8ab4-466b-b91c-ea32e272f588",
        "field_id": "64d1fc80-38fa-4c1e-b13e-b833119151cb",
        "truck_id": "4a861507-1003-4528-9ea6-9f9b7370ae32",
        "crop": "wheat",
        "weight": 9279.4,
        "unloaded_at": "2026-09-15 08:47:00",
        "updated_at": "2026-09-15 08:47:08",
        "unit": "kg"
    }]

    # Mock file reads so json.load pulls our mock datasets
    real_open = builtins.open
    def mock_open(file, *args, **kwargs):
        if "cloud_unloads.json" in str(file):
            return io.StringIO(json.dumps(mock_cloud_data))
        elif "controller_unloads.json" in str(file):
            return io.StringIO(json.dumps(mock_controller_data))
        # Use real_open instead of open() to avoid recursion!
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr("builtins.open", mock_open)

    monkeypatch.setattr("builtins.open", mock_open)

    # Mock sqlite3.connect 
    monkeypatch.setattr(main.sqlite3, "connect", lambda *args, **kwargs: test_db)

    # Run the pipeline
    main.init_db(test_db)
    main.load_reference_data(test_db)
    main.process_unloads(test_db)

    # Verify table counts
    cursor = test_db.cursor()
    cursor.execute("SELECT COUNT(*) FROM reconciled_unloads")
    reconciled_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM unresolved_unloads")
    unresolved_count = cursor.fetchone()[0]

    assert reconciled_count == 1, "Expected exactly 1 reconciled record"
    assert unresolved_count == 1, "Expected exactly 1 unresolved duplicate record"

    # Verify correct ID made it to reconciled_unloads
    cursor.execute("SELECT id FROM reconciled_unloads")
    reconciled_row = cursor.fetchone()
    assert reconciled_row["id"] == "1dccaaf4-fe5d-486c-be70-e2e0050c7be1"

    # Verify correct ID was flagged/routed to unresolved_unloads
    cursor.execute("SELECT unload_id, reason FROM unresolved_unloads")
    unresolved_row = cursor.fetchone()
    assert unresolved_row["unload_id"] == "361111e6-8ab4-466b-b91c-ea32e272f588"
    assert "Duplicate" in unresolved_row["reason"] or "unload" in unresolved_row["reason"].lower()

def test_unknown_field_id_reconciliation(test_db, monkeypatch):
    """Test that a record referencing an unknown field ID (not in fields.json) is successfully reconciled."""
    import io
    import json
    import main
    import builtins

    new_field_id = "99999999-9999-9999-9999-999999999999"

    mock_cloud_data = [{}]

    mock_controller_data = [{
        "id": "e4a11111-2222-3333-4444-555555555555",
        "field_id": new_field_id,
        "truck_id": "4a861507-1003-4528-9ea6-9f9b7370ae32",
        "crop": "canola",
        "weight": 8500.0,
        "unloaded_at": "2026-09-15 09:30:00",
        "updated_at": "2026-09-15 09:30:05",
        "unit": "kg"
    }]

    real_open = builtins.open
    def mock_open(file, *args, **kwargs):
        if "cloud_unloads.json" in str(file):
            return io.StringIO(json.dumps(mock_cloud_data))
        elif "controller_unloads.json" in str(file):
            return io.StringIO(json.dumps(mock_controller_data))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr("builtins.open", mock_open)
    monkeypatch.setattr(main.sqlite3, "connect", lambda *args, **kwargs: test_db)

    cursor = test_db.cursor()

    # Run the pipeline
    main.init_db(test_db)
    main.load_reference_data(test_db)
    cursor.execute("SELECT COUNT(*) FROM fields")
    prev_fields_count = cursor.fetchone()[0]
    main.process_unloads(test_db)
    cursor.execute("SELECT COUNT(*) FROM fields")
    curr_fields_count = cursor.fetchone()[0]

    assert curr_fields_count == prev_fields_count + 1

    # Verify table counts
    cursor.execute("SELECT COUNT(*) FROM reconciled_unloads")
    reconciled_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM unresolved_unloads")
    unresolved_count = cursor.fetchone()[0]

    assert reconciled_count == 1, "Expected the mystery field record to be successfully reconciled"
    assert unresolved_count == 0, "Expected zero unresolved records for a valid mystery field match"

    # Verify correct ID and unknown field reference made it through
    cursor.execute("SELECT id, field_id FROM reconciled_unloads")
    row = cursor.fetchone()
    assert row["id"] == "e4a11111-2222-3333-4444-555555555555"
    assert row["field_id"] == new_field_id

