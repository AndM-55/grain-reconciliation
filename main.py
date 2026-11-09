import json
import sqlite3
from pathlib import Path

DB_PATH = Path("reconciliation.db")
SCHEMA_PATH = Path("schema.sql")
WEIGHT_TOLERANCE_KG = 50.0

def print_reconciliation_report():
    """Queries the SQLite database and prints the required reconciliation report to the console."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("\n" + "=" * 80)
    print(" GRAIN CART RECONCILIATION REPORT")
    print("=" * 80)

    # --- PART 1: Field-by-Field Breakdown ---
    print("\n[1] RECONCILED UNLOADS BY FIELD")
    print(f"{'Field ID':<38} | {'Crop':<10} | {'Unloads':<8} | {'Total Weight (kg)':<18}")
    print("-" * 80)

    cursor.execute(
        """
        SELECT field_id, crop, COUNT(*) as unload_count, SUM(weight_kg) as total_weight
        FROM reconciled_unloads
        GROUP BY field_id, crop
        ORDER BY total_weight DESC
        """
    )
    reconciled_rows = cursor.fetchall()
    if reconciled_rows:
        for row in reconciled_rows:
            print(f"{row['field_id']} | {row['crop']:<10} | {row['unload_count']:<8} | {row['total_weight']:<18.2f}")
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
            print(f"{ref_id:<38} | {row['source']:<10} | {row['reason']}")
    else:
        print("  None. All records resolved cleanly!")

    print("=" * 80 + "\n")
    conn.close()

def normalize_controller_record(raw):
    return {
        "id": raw["id"],  # Same identifier
        "field_id": raw["field_id"],
        "truck_id": raw["truck_id"],
        "crop": raw["crop"],
        "weight_kg": raw["weight"],  # Already in kg, just map the key
        "unloaded_at": raw["unloaded_at"].replace(" ", "T") + "-05:00",
        "updated_at": raw["updated_at"].replace(" ", "T") + "-05:00"
    }

def process_unloads():
    """Loads cloud and controller unloads and runs reconciliation."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Allows accessing columns by name
    cursor = conn.cursor()

    cursor.execute("DELETE FROM reconciled_unloads")
    cursor.execute("DELETE FROM unresolved_unloads")
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

    deleted_cloud_data = [
        record for record in cloud_data
        if record.get("trashed_at") is not None
    ]
    print(f"number of records deleted on behalf of cloud:     {len(deleted_cloud_data)}")

    normalized_controller_data = [
        normalize_controller_record(record) for record in controller_data
    ]

    # Index normalized controller records by ID 
    controller_dictionary = {record["id"]: record for record in normalized_controller_data}

    matched_controller_ids = set()

    # Iterate through active cloud records to match and reconcile
    for cloud_record in active_cloud_data:
        record_id = cloud_record["id"]
        controller_record = controller_dictionary.get(record_id)

        if controller_record:
            matched_controller_ids.add(record_id)
            # Both systems have this record. Check for weight divergence.
            cloud_weight = cloud_record["weight_kg"]
            controller_weight = controller_record["weight_kg"]
            
            if abs(cloud_weight - controller_weight) > WEIGHT_TOLERANCE_KG:
                # Discrepancy is too high - route to unresolved_unloads for manual review
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO unresolved_unloads 
                    (unload_id, source, raw_payload, reason)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        cloud_record["id"],
                        "cloud",
                        json.dumps({"cloud": cloud_record, "controller": controller_record}),
                        f"Weight discrepancy exceeds tolerance: Cloud={cloud_weight}kg, Controller={controller_weight}kg"
                    )
                )
            else:
                # Weights are aligned. Resolve conflict by taking the most recently updated record.
                winning_record = (
                    cloud_record 
                    if cloud_record["updated_at"] >= controller_record["updated_at"] 
                    else controller_record
                )
                
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO reconciled_unloads 
                    (id, field_id, truck_id, crop, weight_kg, unloaded_at, updated_at, resolution_notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        winning_record["id"],
                        winning_record["field_id"],
                        winning_record["truck_id"],
                        winning_record["crop"],
                        winning_record["weight_kg"],
                        winning_record["unloaded_at"],
                        winning_record["updated_at"],
                        None  # resolution_notes can be None for normal successful syncs
                    )
                )
        else:
            # Record exists in Cloud, but missing from Controller (Valid Master record)
            cursor.execute(
                """
                INSERT OR REPLACE INTO reconciled_unloads 
                (id, field_id, truck_id, crop, weight_kg, unloaded_at, updated_at, resolution_notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cloud_record["id"],
                    cloud_record["field_id"],
                    cloud_record["truck_id"],
                    cloud_record["crop"],
                    cloud_record["weight_kg"],
                    cloud_record["unloaded_at"],
                    cloud_record["updated_at"],
                    None
                )
            )    

    for controller_id, controller_record in controller_dictionary.items():
        if controller_id not in matched_controller_ids:
            cursor.execute(
                """
                INSERT OR REPLACE INTO unresolved_unloads 
                (unload_id, source, raw_payload, reason)
                VALUES (?, ?, ?, ?)
                """,
                (
                    controller_record["id"],
                    "controller",
                    json.dumps(controller_record),
                    "Record exists on controller but missing from Cloud master"
                )
            )

    conn.commit()



def init_db():
    """Automatically initializing the SQLite database using schema.sql."""
    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, "r") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
    print("Database initialized successfully from schema.sql")


# this function will load the reference data for trucks and fields into the databases
def load_reference_data():
    """Loads fields and trucks"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Load fields.json
    with open("data/fields.json", "r") as f:
        fields = json.load(f)
        for field in fields:
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
            cursor.execute(
                """
                INSERT OR REPLACE INTO trucks (id, name, capacity_kg)
                VALUES (?, ?, ?)
                """,
                (truck["id"], truck["name"], truck["capacity_kg"])
            )

    conn.commit()
    conn.close()
    print("Reference data (fields and trucks) loaded successfully!")



def main():
    print("Grain Cart Reconciliation Pipeline")

    
    # Initialize Database
    init_db()
    
    # Load JSON files
    load_reference_data()
    # Run reconciliation logic
    process_unloads()
    
    print("==========================================")

if __name__ == "__main__":
    import sys
    
    # Check if a 'report' argument was passed from the terminal
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        print_reconciliation_report()
    else:
        # Default behavior: run pipeline, then display the report
        main()