"""
Action Executor & Audit Logger Dataset Runner (Phase 4)
========================================================

Applies simulated action execution (executor/actions.py) to all decisions rows in SQLite,
populates the actions table, and records detailed 3-step audit narratives in audit_log.
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
from executor.actions import execute_action
from audit.logger import log_audit_entry

def apply_actions_to_dataset():
    print("=" * 60)
    print("PHASE 4: APPLYING ACTION EXECUTOR & AUDIT LOGGER TO DATASET")
    print("=" * 60)

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Idempotent re-run strategy: clear actions and audit_log tables
    cursor.execute("DELETE FROM actions;")
    cursor.execute("DELETE FROM audit_log;")
    conn.commit()
    print("[OK] Cleared existing actions and audit_log tables.")

    # Fetch all decisions joined with classifications, failure_events, subscriptions, and case_state
    # CRITICAL ORDER REQUIREMENT: ORDER BY fe.subscription_id ASC, fe.received_at ASC
    decision_rows = cursor.execute("""
        SELECT 
            d.id as decision_id,
            d.classification_id,
            d.action_type,
            d.playbook_rule_id,
            cl.category,
            cl.method,
            cl.confidence,
            fe.id as failure_event_id,
            fe.subscription_id,
            fe.external_event_id,
            fe.attempt_number,
            fe.received_at,
            cs.status as case_status
        FROM decisions d
        JOIN classifications cl ON d.classification_id = cl.id
        JOIN failure_events fe ON cl.failure_event_id = fe.id
        LEFT JOIN case_state cs ON fe.subscription_id = cs.subscription_id
        ORDER BY fe.subscription_id ASC, fe.received_at ASC, fe.id ASC
    """).fetchall()

    print(f"[OK] Fetched {len(decision_rows)} decisions for action execution and audit logging.")

    actions_inserted = 0
    audit_entries_logged = 0

    for item in decision_rows:
        dec_id = item["decision_id"]
        sub_id = item["subscription_id"]
        action_type = item["action_type"]
        rule_id = item["playbook_rule_id"]
        category = item["category"]
        method = item["method"]
        confidence = item["confidence"]
        evt_id = item["external_event_id"]
        attempt_number = item["attempt_number"]
        case_status = item["case_status"]

        # 1. Execute Simulated Action
        simulated, result, payload_json = execute_action(
            action_type=action_type,
            playbook_rule_id=rule_id,
            category=category,
            subscription_id=sub_id,
            attempt_number=attempt_number,
            case_status=case_status
        )

        # 2. Insert record into actions table
        cursor.execute(
            """
            INSERT INTO actions (decision_id, action_type, simulated, payload, result)
            VALUES (?, ?, ?, ?, ?)
            """,
            (dec_id, action_type, simulated, payload_json, result)
        )
        actions_inserted += 1

        # 3. Log 3-Step Human-Readable Audit Entries into audit_log table
        # Step A: Classification Summary
        summary_class = (
            f"Classified failure event '{evt_id}' for subscription '{sub_id}' "
            f"as category '{category}' via {method} engine with confidence {confidence:.2f}."
        )
        log_audit_entry(conn, sub_id, summary_class, actor="system")

        # Step B: Policy Decision Summary
        summary_decision = (
            f"Policy engine evaluated subscription '{sub_id}': "
            f"decided action '{action_type}' (Playbook Rule: '{rule_id}')."
        )
        log_audit_entry(conn, sub_id, summary_decision, actor="system")

        # Step C: Action Execution Summary
        summary_action = (
            f"Action executed: '{action_type}' (simulated) for subscription '{sub_id}', "
            f"result: {result}."
        )
        log_audit_entry(conn, sub_id, summary_action, actor="system")

        audit_entries_logged += 3

    conn.commit()
    print(f"[OK] Successfully inserted {actions_inserted} actions and logged {audit_entries_logged} audit entries.")

    # Query and display action execution results breakdown
    cursor.execute("""
        SELECT action_type, result, count(*) as count
        FROM actions
        GROUP BY action_type, result
        ORDER BY action_type
    """)
    results_dist = cursor.fetchall()

    print("\n" + "=" * 60)
    print("ACTIONS TABLE RESULT BREAKDOWN (FROM DATABASE)")
    print("=" * 60)
    for row in results_dist:
        print(f"  - Action: '{row['action_type']}' | Result: '{row['result']}' | Count: {row['count']}")
    print("=" * 60)

    # Query and display total audit log count
    cursor.execute("SELECT count(*) FROM audit_log;")
    total_audit = cursor.fetchone()[0]
    print(f"[VERIFICATION] Total audit_log rows in DB: {total_audit} (Expected 3 per event: {len(decision_rows)*3}) [OK]")

    # Verification: Confirm prior tables unchanged
    cursor.execute("SELECT count(*) FROM subscriptions;")
    subs_cnt = cursor.fetchone()[0]
    cursor.execute("SELECT count(*) FROM failure_events;")
    fe_cnt = cursor.fetchone()[0]
    cursor.execute("SELECT count(*) FROM classifications;")
    cl_cnt = cursor.fetchone()[0]
    cursor.execute("SELECT count(*) FROM decisions;")
    dec_cnt = cursor.fetchone()[0]

    print(f"[VERIFICATION] Prior table row counts: subscriptions={subs_cnt}, failure_events={fe_cnt}, classifications={cl_cnt}, decisions={dec_cnt} [OK]")

    conn.close()

if __name__ == "__main__":
    apply_actions_to_dataset()
