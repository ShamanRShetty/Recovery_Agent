import os
import sqlite3
import sys

# Ensure UTF-8 output encoding on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from db.init import init_db, get_db_connection

VERIFY_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "test_verification.db")

def cleanup_test_db():
    if os.path.exists(VERIFY_DB_PATH):
        os.remove(VERIFY_DB_PATH)

def run_verification():
    print("=" * 60)
    print("RUNNING DATABASE VERIFICATION SUITE")
    print("=" * 60)

    # 1. Clean init
    cleanup_test_db()
    print("\n[CHECK 1] Initializing database from clean state...")
    init_db(VERIFY_DB_PATH)
    print("[OK] Clean initialization succeeded.")

    conn = get_db_connection(VERIFY_DB_PATH)
    cursor = conn.cursor()

    # 2. Confirm all 7 tables exist
    print("\n[CHECK 2] Verifying table existence...")
    expected_tables = {
        'subscriptions',
        'failure_events',
        'classifications',
        'decisions',
        'actions',
        'case_state',
        'audit_log'
    }
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    actual_tables = set(row[0] for row in cursor.fetchall())
    
    print(f"Actual tables found: {sorted(list(actual_tables))}")
    missing = expected_tables - actual_tables
    if missing:
        raise RuntimeError(f"[ERROR] Missing tables: {missing}")
    print("[OK] All 7 required tables exist.")

    # Insert valid hierarchy of rows to anchor FK references across all tables
    cursor.execute(
        "INSERT INTO subscriptions (id, customer_id, plan_amount) VALUES (?, ?, ?)",
        ("sub_valid_1", "cust_100", 999)
    )
    cursor.execute(
        "INSERT INTO failure_events (id, subscription_id, external_event_id, event_type) VALUES (?, ?, ?, ?)",
        (10, "sub_valid_1", "evt_anchor_10", "payment.failed")
    )
    cursor.execute(
        "INSERT INTO classifications (id, failure_event_id, category, method, confidence) VALUES (?, ?, ?, ?, ?)",
        (20, 10, "insufficient_funds", "rule", 0.95)
    )
    cursor.execute(
        "INSERT INTO decisions (id, classification_id, action_type, playbook_rule_id) VALUES (?, ?, ?, ?)",
        (30, 20, "send_nudge", "rule_funds_01")
    )
    conn.commit()

    # 3. Confirm Foreign Key Enforcement
    print("\n[CHECK 3] Testing Foreign Key Enforcement (inserting invalid subscription_id)...")
    try:
        cursor.execute(
            "INSERT INTO failure_events (subscription_id, external_event_id, event_type) VALUES (?, ?, ?)",
            ("sub_NON_EXISTENT", "evt_fk_test", "payment.failed")
        )
        conn.commit()
        raise RuntimeError("[ERROR] FK constraint failed to reject invalid reference!")
    except sqlite3.IntegrityError as e:
        print(f"[OK] Foreign Key Constraint successfully REJECTED bad reference!")
        print(f"   Literal error output: {e}")

    # 4. Confirm external_event_id UNIQUE constraint
    print("\n[CHECK 4] Testing Webhook Idempotency (external_event_id UNIQUE constraint)...")
    cursor.execute(
        "INSERT INTO failure_events (subscription_id, external_event_id, event_type) VALUES (?, ?, ?)",
        ("sub_valid_1", "evt_idempotency_key_001", "payment.failed")
    )
    conn.commit()
    print("   First event inserted successfully.")

    try:
        cursor.execute(
            "INSERT INTO failure_events (subscription_id, external_event_id, event_type) VALUES (?, ?, ?)",
            ("sub_valid_1", "evt_idempotency_key_001", "payment.failed")
        )
        conn.commit()
        raise RuntimeError("[ERROR] UNIQUE constraint failed to reject duplicate external_event_id!")
    except sqlite3.IntegrityError as e:
        print("[OK] Webhook Idempotency UNIQUE constraint successfully REJECTED duplicate event!")
        print(f"   Literal error output: {e}")

    # 5. Confirm CHECK Constraints reject invalid values
    print("\n[CHECK 5] Testing CHECK constraints on all tables...")
    
    check_tests = [
        (
            "subscriptions.plan_amount > 0",
            "INSERT INTO subscriptions (id, customer_id, plan_amount) VALUES ('sub_bad_amount', 'cust_1', -50)",
        ),
        (
            "subscriptions.status IN ('active','pending','halted','cancelled')",
            "INSERT INTO subscriptions (id, customer_id, plan_amount, status) VALUES ('sub_bad_status', 'cust_1', 100, 'unknown')",
        ),
        (
            "failure_events.event_type IN (...)",
            "INSERT INTO failure_events (subscription_id, external_event_id, event_type) VALUES ('sub_valid_1', 'evt_chk_1', 'bad_event')",
        ),
        (
            "failure_events.attempt_number > 0",
            "INSERT INTO failure_events (subscription_id, external_event_id, event_type, attempt_number) VALUES ('sub_valid_1', 'evt_chk_2', 'payment.failed', 0)",
        ),
        (
            "classifications.category IN (...)",
            "INSERT INTO classifications (failure_event_id, category, method, confidence) VALUES (10, 'invalid_category', 'rule', 0.9)",
        ),
        (
            "classifications.method IN ('rule','llm')",
            "INSERT INTO classifications (failure_event_id, category, method, confidence) VALUES (10, 'insufficient_funds', 'random', 0.9)",
        ),
        (
            "classifications.confidence >= 0.0 AND confidence <= 1.0",
            "INSERT INTO classifications (failure_event_id, category, method, confidence) VALUES (10, 'insufficient_funds', 'rule', 1.5)",
        ),
        (
            "decisions.action_type IN ('send_nudge','wait','escalate','stop')",
            "INSERT INTO decisions (classification_id, action_type, playbook_rule_id) VALUES (20, 'invalid_action', 'rule_1')",
        ),
        (
            "actions.simulated IN (0,1)",
            "INSERT INTO actions (decision_id, action_type, simulated, result) VALUES (30, 'email', 2, 'success')",
        ),
        (
            "actions.result IN ('success','failed','no_op')",
            "INSERT INTO actions (decision_id, action_type, simulated, result) VALUES (30, 'email', 1, 'invalid_result')",
        ),
        (
            "case_state.contact_count >= 0 AND contact_count <= 2",
            "INSERT INTO case_state (subscription_id, contact_count) VALUES ('sub_valid_1', 3)",
        ),
        (
            "case_state.status IN ('open','recovered','escalated','stopped')",
            "INSERT INTO case_state (subscription_id, status) VALUES ('sub_valid_1', 'completed')",
        ),
        (
            "audit_log.actor IN ('system','llm','human')",
            "INSERT INTO audit_log (subscription_id, event_summary, actor) VALUES ('sub_valid_1', 'summary', 'bot')",
        ),
    ]

    rejected_count = 0
    for label, statement in check_tests:
        try:
            cursor.execute(statement)
            conn.commit()
            print(f"[ERROR] CHECK constraint test failed to reject invalid value for [{label}]!")
            raise RuntimeError(f"Constraint failure for {label}")
        except sqlite3.IntegrityError as e:
            rejected_count += 1
            print(f"[OK] REJECTED invalid value for [{label}] -> {e}")
            conn.rollback()

    print(f"\n[OK] All {rejected_count} CHECK constraints verified successfully!")
    conn.close()
    
    # Cleanup test DB
    cleanup_test_db()
    print("\n" + "=" * 60)
    print("VERIFICATION SUITE COMPLETED SUCCESSFULLY (100% PASS)")
    print("=" * 60)

if __name__ == "__main__":
    run_verification()
