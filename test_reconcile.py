import sqlite3
import pytest
from main import normalize_controller_record, process_unloads

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
    conn.close()



def test_normalize_controller_record():
    """Test that controller records correctly map their weight and keys."""
    raw = {
        "id": "test-id",
        "field_id": "field-A",
        "truck_id": "truck-1",
        "crop": "wheat",
        "weight": 4500.0,
        "unloaded_at": "2026-10-15 10:00:00",
        "updated_at": "2026-10-15 10:30:00"
    }
    # FIX THIS BEFORE TESTING
    active = [{
        "id": "test-id",
        "field_id": "field-A",
        "truck_id": "truck-1",
        "crop": "wheat",
        "weight": 4500.0,
        "unloaded_at": "2026-10-15 10:00:00",
        "updated_at": "2026-10-15 10:30:00"
    }]
    normalized = normalize_controller_record(raw, active)
    
    assert normalized["id"] == "test-id"
    assert normalized["weight_kg"] == 4500.0
    assert "T" in normalized["unloaded_at"] 
    assert "-06:00" in normalized["unloaded_at"]

def test_weight_discrepancy_routing(test_db, monkeypatch):
    """Test that records exceeding the weight tolerance are routed to unresolved_unloads."""
    import io
    import json
    import main

    # Define mock dataset where cloud and controller weights diverge beyond tolerance
    mock_cloud_data = [{
        "id": "rec-001",
        "field_id": "field-north",
        "truck_id": "truck-01",
        "crop": "canola",
        "weight_kg": 5000.0,
        "unloaded_at": "2026-10-15 10:00:00",
        "updated_at": "2026-10-15 10:30:00",
        "trashed_at": None
    }]

    mock_controller_data = [{
        "id": "rec-001",
        "field_id": "field-north",
        "truck_id": "truck-01",
        "crop": "canola",
        "weight": 4500.0,  # 500kg difference 
        "unloaded_at": "2026-10-15 10:00:00",
        "updated_at": "2026-10-15 10:20:00"
    }]

    # Mock file reads so json.load 
    def mock_open(file, *args, **kwargs):
        if "cloud_unloads.json" in str(file):
            return io.StringIO(json.dumps(mock_cloud_data))
        elif "controller_unloads.json" in str(file):
            return io.StringIO(json.dumps(mock_controller_data))
        return open(file, *args, **kwargs)

    monkeypatch.setattr("builtins.open", mock_open)

    # Mock sqlite3.connect 
    monkeypatch.setattr(main.sqlite3, "connect", lambda *args, **kwargs: test_db)

    # Run the pipeline
    main.process_unloads()

    # Assert that the record was successfully caught and routed to unresolved_unloads
    cursor = test_db.cursor()
    cursor.execute("SELECT COUNT(*) FROM unresolved_unloads")
    unresolved_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM reconciled_unloads")
    reconciled_count = cursor.fetchone()[0]

    assert unresolved_count == 1, "Expected the divergent record to be routed to unresolved_unloads"
    assert reconciled_count == 0, "Expected reconciled_unloads to remain empty due to weight divergence"

    # Verify the reason logged is correct
    cursor.execute("SELECT reason, source FROM unresolved_unloads")
    row = cursor.fetchone()
    assert "Weight discrepancy exceeds tolerance" in row["reason"]
    assert row["source"] == "cloud"

