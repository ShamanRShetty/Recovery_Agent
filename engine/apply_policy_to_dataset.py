"""
Policy Engine Dataset Runner (Phase 3)
=====================================

Applies the pure policy decision engine (engine/policy.py) to all classified events,
inserts rows into the decisions table, and manages state transitions in case_state.
Processes events strictly in received_at order per subscription.
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
from engine.policy import decide_action
from engine.case_state import get_or_create_case_state, update_case_state

def apply_policy_to_dataset():
    print("=" * 60)
    print("PHASE 3: APPLYING POLICY ENGINE TO DATASET")
    print("=" * 60)

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Idempotent re-run strategy: clear decisions table and reset case_state table
    cursor.execute("DELETE FROM decisions;")
    cursor.execute("DELETE FROM case_state;")
    conn.commit()
    print("[OK] Cleared existing decisions and reset case_state tables.")

    # Fetch all classified events joined with failure_events and subscriptions
    # CRITICAL ORDER REQUIREMENT: ORDER BY subscription_id, received_at ASC
    classified_events = cursor.execute("""
        SELECT 
            cl.id as classification_id,
            cl.failure_event_id,
            cl.category,
            cl.method,
            cl.confidence,
            fe.subscription_id,
            fe.external_event_id,
            fe.event_type,
            fe.attempt_number,
            fe.received_at,
            s.status as master_subscription_status
        FROM classifications cl
        JOIN failure_events fe ON cl.failure_event_id = fe.id
        JOIN subscriptions s ON fe.subscription_id = s.id
        ORDER BY fe.subscription_id ASC, fe.received_at ASC, fe.id ASC
    """).fetchall()

    print(f"[OK] Fetched {len(classified_events)} classified events for policy evaluation.")

    decisions_count = 0
    for item in classified_events:
        sub_id = item["subscription_id"]
        category = item["category"]
        confidence = item["confidence"]
        attempt_number = item["attempt_number"]
        event_type = item["event_type"]
        master_status = item["master_subscription_status"]
        class_id = item["classification_id"]

        # Derive event lifecycle status from event_type and master_status
        if event_type == "subscription.activated":
            sub_status = "active"
        elif event_type == "subscription.halted":
            sub_status = "halted"
        elif event_type == "subscription.cancelled":
            sub_status = "cancelled"
        else:
            sub_status = "halted" if master_status == "halted" else "pending"

        # Read current case_state for this subscription
        case_state = get_or_create_case_state(conn, sub_id)

        # Call pure policy function
        action_type, playbook_rule_id = decide_action(
            category=category,
            confidence=confidence,
            case_state=case_state,
            subscription_status=sub_status,
            attempt_number=attempt_number
        )

        # Write decision record
        cursor.execute(
            """
            INSERT INTO decisions (classification_id, action_type, playbook_rule_id)
            VALUES (?, ?, ?)
            """,
            (class_id, action_type, playbook_rule_id)
        )
        decisions_count += 1

        # Update case_state based on decision
        update_case_state(
            conn=conn,
            subscription_id=sub_id,
            action_type=action_type,
            category=category,
            subscription_status=sub_status
        )

    conn.commit()
    print(f"[OK] Successfully recorded {decisions_count} decisions in DB.")

    # Query and display action_type distribution from decisions table
    cursor.execute("""
        SELECT action_type, count(*) as count
        FROM decisions
        GROUP BY action_type
        ORDER BY action_type
    """)
    action_dist = cursor.fetchall()

    print("\n" + "=" * 60)
    print("DECISIONS TABLE ACTION_TYPE DISTRIBUTION (FROM DATABASE)")
    print("=" * 60)
    for row in action_dist:
        print(f"  - {row['action_type']}: {row['count']} decisions")
    print("=" * 60)

    # Verification: Confirm no subscription contact_count > 2 in case_state
    cursor.execute("SELECT max(contact_count) FROM case_state;")
    max_contacts = cursor.fetchone()[0]
    if max_contacts is not None and max_contacts > 2:
        raise RuntimeError(f"[ERROR] Max contact limit exceeded! Found contact_count = {max_contacts}")
    print(f"[VERIFICATION] Max contact_count across all case_state records: {max_contacts} (Limit: 2) [OK]")

    # Downstream isolation assertion check
    downstream_tables = ["actions", "audit_log"]
    print("\n[VERIFICATION] Asserting downstream tables remain 100% empty...")
    for tbl in downstream_tables:
        cursor.execute(f"SELECT count(*) FROM {tbl};")
        cnt = cursor.fetchone()[0]
        if cnt != 0:
            raise RuntimeError(f"[ERROR] Downstream table '{tbl}' contains {cnt} rows! Expected 0.")
        print(f"   Table '{tbl}': {cnt} rows [OK]")

    conn.close()

if __name__ == "__main__":
    apply_policy_to_dataset()
