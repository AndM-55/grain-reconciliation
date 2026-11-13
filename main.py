import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path("reconciliation.db")
SCHEMA_PATH = Path("schema.sql")
LB_TO_KG = 0.4536
truck_ids = set()
field_ids = set()
new_field_count = 0

# unload_id 1dccaaf4-fe5d-486c-be70-e2e0050c7be1 and 361111e6-8ab4-466b-b91c-ea32e272f588 are tricky here
# maybe even add 3ac2ff60-5686-4564-a28c-dd2d1d59d793 to the list?

# WEIGHT_TOLERANCE_KG = 50.0

###################################################################

def print_reconciliation_report():
    """Queries the SQLite database and prints the required reconciliation report to the console."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("\n" + "=" * 80)
    print(" GRAIN CART RECONCILIATION REPORT")
    print("=" * 80)

    cursor.execute("SELECT COUNT(*) FROM reconciled_unloads")
    resolved_count = cursor.fetchone()[0]

    # --- PART 1: Field-by-Field Breakdown ---
    print(f"\n[1] RECONCILED UNLOADS BY FIELD ({resolved_count} total records)")
    print(f"{'Field name':<20} | {'Crop':<10} | {'Unloads':<8} | {'Total Weight (kg)':<18}")
    print("-" * 80)

    cursor.execute(
        """
        SELECT 
            r.field_id, 
            f.name AS field_name, 
            r.crop, 
            COUNT(*) as unload_count, 
            SUM(r.weight_kg) as total_weight
        FROM reconciled_unloads r
        LEFT JOIN fields f ON r.field_id = f.id
        GROUP BY r.field_id, f.name, r.crop
        ORDER BY total_weight DESC
        """
    )
    reconciled_rows = cursor.fetchall()
    if reconciled_rows:
        for row in reconciled_rows:
            print(f"{row['field_name']:<20} | {row['crop']:<10} | {row['unload_count']:<8} | {row['total_weight']:<18.2f}")
    else:
        print("  No successfully reconciled records found.")

    # --- PART 2: Unresolved Records with Reasons ---
    cursor.execute("SELECT COUNT(*) FROM unresolved_unloads")
    unresolved_count = cursor.fetchone()[0]

    print(f"\n[2] UNRESOLVED ANOMALIES & CONFLICTS ({unresolved_count} records)")
    print(f"{'Unload ID / Ref':<38} | {'Source':<10} | {'Reason'}")
    print("-" * 80)

    cursor.execute("SELECT unload_id, source, reason FROM unresolved_unloads")
    unresolved_rows = cursor.fetchall()
    if unresolved_rows:
        for row in unresolved_rows:
            ref_id = row['unload_id'] if row['unload_id'] else "N/A (Orphan)"
            print(f"{ref_id:<38} | {row['source']:<12} | {row['reason']}")
    else:
        print("  None. All records resolved cleanly!")

    print("=" * 80 + "\n")
    conn.close()

###################################################################

def _find_cloud_record_by_id(record_id, active_cloud_data):
    """Helper function to find a matching cloud entry by ID."""
    for cloud_rec in active_cloud_data:
        if cloud_rec.get("id") == record_id:
            return cloud_rec
    return None

###################################################################

def standardize_timestamp(ts_str):
    if not ts_str:
        return None
    
    # 1. Ensure 'T' separates date and time (handles spaces if present)
    clean_str = ts_str.replace(" ", "T")
    
    # 2. Parse into a timezone-aware datetime object
    dt = datetime.fromisoformat(clean_str)
    
    # 3. Convert to UTC so every timestamp shares the exact same anchor
    dt_utc = dt.astimezone(timezone.utc)
    
    # 4. Return as a standard ISO string (e.g., '2026-09-15T19:04:00+00:00')
    return dt_utc.isoformat()

###################################################################

def normalize_record(raw, active_cloud_data, rec_type):
    if rec_type == "controller":
        raw_unit = raw.get("unit", "unknown").lower()
        
        if raw_unit in ["lb", "pounds", "lbs"]:
            weight_in_kg = LB_TO_KG * raw["weight"]
        elif raw_unit == "kg":
            weight_in_kg = raw["weight"]
        else:
            # Unknown or missing unit: fall back to the matching cloud record's weight
            cloud_match = _find_cloud_record_by_id(raw.get("id"), active_cloud_data)
            if cloud_match:
                weight_in_kg = cloud_match.get("weight_kg", 0.0)
            else:
                weight_in_kg = raw.get("weight", 0.0)
        unloaded_at = standardize_timestamp(raw["unloaded_at"].replace(" ", "T") + "-06:00")
        updated_at = standardize_timestamp(raw["updated_at"].replace(" ", "T") + "-06:00") 
    else: 
        weight_in_kg = raw.get("weight_kg")
        unloaded_at = standardize_timestamp(raw["unloaded_at"])
        updated_at = standardize_timestamp(raw["updated_at"]) 

    return {
        "id": raw["id"],  # Same identifier
        "field_id": raw["field_id"],
        "truck_id": raw["truck_id"],
        "crop": raw["crop"],
        "weight_kg": weight_in_kg,  
        "unloaded_at": unloaded_at,
        "updated_at": updated_at
    }

###################################################################

def store_reconciled_record(cursor: sqlite3.Cursor, record):
    cursor.execute(
        """
                INSERT OR REPLACE INTO reconciled_unloads 
                (id, field_id, truck_id, crop, weight_kg, unloaded_at, updated_at, resolution_notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
        (
            record["id"],
            record["field_id"],
            record["truck_id"],
            record["crop"],
            record["weight_kg"],
            record["unloaded_at"],
            record["updated_at"],
            None  # resolution_notes can be None for normal successful syncs
        )
    )
###################################################################

def store_dropped_record(cursor: sqlite3.Cursor, record, reason, source):
    cursor.execute(
        """
                INSERT OR REPLACE INTO unresolved_unloads 
                (unload_id, source, raw_payload, reason)
                VALUES (?, ?, ?, ?)
                """,
        (
            record["id"],
            source,
            json.dumps(record),
            reason
        )
    )

###################################################################

def new_field(cursor: sqlite3.Cursor, record):
    cursor.execute(
        """
                INSERT OR REPLACE INTO fields (id, name, area_ha, crop)
                VALUES (?, ?, ?, ?)
                """,
        (record["field_id"], f"New Field {new_field_count}", -1.0, record["crop"])
    )

###################################################################

def check_discrepancies(cursor: sqlite3.Cursor, controller_record):
    
    if controller_record["truck_id"] not in truck_ids:
        store_dropped_record(cursor, controller_record, "Truck ID discrepancy", "Controller")
        return False
    elif controller_record["field_id"] not in field_ids:
        new_field(cursor, controller_record)
        return True
    else:
        # Query the database to check if a reconciled unload with the exact 
        # same field, truck, and timestamp already exists.
        # (Make sure 'reconciled_unloads' matches your actual table name)
        cursor.execute(
            """
            SELECT 1 FROM reconciled_unloads 
            WHERE field_id = ? 
              AND truck_id = ? 
              AND unloaded_at = ?
            """,
            (
                controller_record["field_id"],
                controller_record["truck_id"],
                controller_record["unloaded_at"]
            )
        )
        existing_match = cursor.fetchone()
        
        if existing_match:
            store_dropped_record(cursor, controller_record, "Duplicate unload discrepancy", "Controller")
            return False
            
    return True


###################################################################

def process_unloads(db_path_or_conn=None):
    """Loads cloud and controller unloads and runs reconciliation."""
    if db_path_or_conn is None:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM reconciled_unloads")
        cursor.execute("DELETE FROM unresolved_unloads") 
    elif isinstance(db_path_or_conn, sqlite3.Connection):
        conn = db_path_or_conn
    else:
        conn = sqlite3.connect(db_path_or_conn)
    cursor = conn.cursor()

    conn.row_factory = sqlite3.Row  # Allows accessing columns by name
    conn.commit()

    with open("data/cloud_unloads.json", "r") as f:
        cloud_data = json.load(f)
        
    with open("data/controller_unloads.json", "r") as f:
        controller_data = json.load(f)

    print(f"Loaded {len(cloud_data)} cloud records and {len(controller_data)} controller records.")

    # trashed_at filtering
    active_cloud_data = [
        record for record in cloud_data 
        if record.get("trashed_at") is None
    ]

    trashed_cloud_record_ids = set()

    for record in cloud_data:
        if record.get("trashed_at") is not None:
            trashed_cloud_record_ids.add(record["id"])
            store_dropped_record(cursor, record, "Trashed", "Cloud")

    deleted_cloud_data = [
        record for record in cloud_data
        if record.get("trashed_at") is not None
    ]
    print(f"number of records deleted on behalf of cloud:     {len(deleted_cloud_data)}")

    normalized_controller_data = [
        normalize_record(record, active_cloud_data, "controller") for record in controller_data
    ]

    # Index normalized controller records by ID 
    controller_dictionary = {record["id"]: record for record in normalized_controller_data}
    matched_controller_ids = set()

    # Iterate through active cloud records to match and reconcile
    if len(active_cloud_data) > 0:

        for cloud_record in active_cloud_data:
            record_id = cloud_record.get("id")
            controller_record = controller_dictionary.get(record_id)

            if controller_record:
                matched_controller_ids.add(record_id)
                reconcilable = check_discrepancies(cursor, controller_record)

                if reconcilable:
                    cloud_dt = datetime.fromisoformat(cloud_record["updated_at"])
                    controller_dt = datetime.fromisoformat(controller_record["updated_at"])
                    
                    winning_record = (
                        normalize_record(cloud_record, active_cloud_data, "cloud") 
                        if cloud_dt >= controller_dt
                        else controller_record
                    )

                    store_reconciled_record(cursor, winning_record) 

    if len(controller_dictionary) > 0:
        for controller_id, controller_record in controller_dictionary.items():
            if controller_id not in matched_controller_ids:
                if controller_id in trashed_cloud_record_ids:
                    store_dropped_record(cursor, controller_record, "Trashed By Cloud master", "Controller")
                else:
                    reconcilable = check_discrepancies(cursor, controller_record)
                    if reconcilable:
                        store_reconciled_record(cursor, controller_record)

    conn.commit()


###################################################################

def init_db(db_path_or_conn=None):
    """Automatically initializing the SQLite database using schema.sql."""
    is_external_conn = isinstance(db_path_or_conn, sqlite3.Connection)
    
    if db_path_or_conn is None:
        conn = sqlite3.connect(DB_PATH)
    elif is_external_conn:
        conn = db_path_or_conn
    else:
        conn = sqlite3.connect(db_path_or_conn)
        
    with open(SCHEMA_PATH, "r") as f:
        conn.executescript(f.read())
        
    conn.commit()
    
    # Only close if we opened the connection locally
    if not is_external_conn and db_path_or_conn is not None:
        conn.close()
    elif db_path_or_conn is None:
        conn.close()
        
    print("Database initialized successfully from schema.sql")


###################################################################
# this function will load the reference data for trucks and fields into the databases
def load_reference_data(db_path_or_conn=None):
    """Loads fields and trucks"""
    if db_path_or_conn is None:
        conn = sqlite3.connect(DB_PATH)
    elif isinstance(db_path_or_conn, sqlite3.Connection):
        conn = db_path_or_conn
    else:
        conn = sqlite3.connect(db_path_or_conn)
    cursor = conn.cursor()
    
    # Load fields.json
    with open("data/fields.json", "r") as f:
        fields = json.load(f)
        for field in fields:
            field_ids.add(field["id"])
            cursor.execute(
                """
                INSERT OR REPLACE INTO fields (id, name, area_ha, crop)
                VALUES (?, ?, ?, ?)
                """,
                (field["id"], field["name"], field["area_ha"], field["crop"])
            )

    # Load trucks.json
    with open("data/trucks.json", "r") as f:
        trucks = json.load(f)
        for truck in trucks:
            truck_ids.add(truck["id"])
            cursor.execute(
                """
                INSERT OR REPLACE INTO trucks (id, name, capacity_kg)
                VALUES (?, ?, ?)
                """,
                (truck["id"], truck["name"], truck["capacity_kg"])
            )

    conn.commit()
    print("Reference data (fields and trucks) loaded successfully!")

###################################################################

def main():
    print("Grain Cart Reconciliation Pipeline")

    
    # Initialize Database
    init_db()
    
    # Load JSON files
    load_reference_data()
    # Run reconciliation logic
    process_unloads()
    
    print("==========================================")

###################################################################

if __name__ == "__main__":
    import sys
    
    # Check if a 'report' argument was passed from the terminal
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        print_reconciliation_report()
    else:
        # Default behavior: run pipeline
        main()