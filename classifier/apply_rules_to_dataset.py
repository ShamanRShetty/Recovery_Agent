"""
Deterministic Classifier Dataset Runner (Phase 2)
=================================================

Applies the pure deterministic rule-based classifier (classifier/rules.py)
to all 40 failure_events rows in SQLite and populates the classifications table.
"""

import os
import sqlite3
import sys

# Ensure UTF-8 output encoding on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.init import get_db_connection
from classifier.rules import classify_by_rules

def apply_rules_to_dataset():
    print("=" * 60)
    print("PHASE 2: APPLYING DETERMINISTIC CLASSIFIER TO DATASET")
    print("=" * 60)

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Idempotent re-run strategy: clear existing classifications table rows before re-populating
    cursor.execute("DELETE FROM classifications;")
    conn.commit()
    print("[OK] Cleared existing classifications table rows.")

    # Fetch all failure_events rows
    events = cursor.execute("""
        SELECT id, subscription_id, external_event_id, error_code, error_reason, error_description, error_source, error_step
        FROM failure_events
        ORDER BY id
    """).fetchall()

    print(f"[OK] Fetched {len(events)} failure_events rows for classification.")

    inserted_count = 0
    classification_records = []

    for ev in events:
        category, confidence = classify_by_rules(
            error_code=ev["error_code"],
            error_reason=ev["error_reason"],
            error_description=ev["error_description"],
            error_source=ev["error_source"],
            error_step=ev["error_step"]
        )
        
        classification_records.append((
            ev["id"],
            category,
            "rule",
            confidence,
            None # llm_reasoning is NULL for rule-based classification
        ))

    cursor.executemany(
        """
        INSERT INTO classifications (failure_event_id, category, method, confidence, llm_reasoning)
        VALUES (?, ?, ?, ?, ?)
        """,
        classification_records
    )
    conn.commit()
    inserted_count = len(classification_records)
    print(f"[OK] Successfully inserted {inserted_count} rows into classifications table.")

    # Query and display actual classifications distribution from database
    cursor.execute("""
        SELECT category, count(*) as count, min(confidence) as min_conf, max(confidence) as max_conf
        FROM classifications
        GROUP BY category
        ORDER BY category
    """)
    distribution = cursor.fetchall()

    print("\n" + "=" * 60)
    print("CLASSIFICATIONS TABLE CATEGORY DISTRIBUTION (FROM DATABASE)")
    print("=" * 60)
    total_classified = 0
    for row in distribution:
        cat = row["category"]
        cnt = row["count"]
        min_c = row["min_conf"]
        max_c = row["max_conf"]
        total_classified += cnt
        print(f"  - {cat}: {cnt} rows (confidence: {min_c} to {max_c})")
    print(f"  TOTAL CLASSIFIED: {total_classified} rows")
    print("=" * 60)

    # Downstream isolation assertion check
    downstream_tables = ["decisions", "actions", "case_state", "audit_log"]
    print("\n[VERIFICATION] Asserting downstream tables remain 100% empty...")
    for tbl in downstream_tables:
        cursor.execute(f"SELECT count(*) FROM {tbl};")
        cnt = cursor.fetchone()[0]
        if cnt != 0:
            raise RuntimeError(f"[ERROR] Downstream table '{tbl}' contains {cnt} rows! Expected 0.")
        print(f"   Table '{tbl}': {cnt} rows [OK]")

    conn.close()

if __name__ == "__main__":
    apply_rules_to_dataset()
