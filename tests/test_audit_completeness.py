import unittest
import sqlite3
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pipeline.process_event import process_failure_event

def get_in_memory_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    schema_path = os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    return conn

class TestAuditCompleteness(unittest.TestCase):

    def test_audit_log_entries_count_per_event(self):
        """Asserts that each processed event generates at least 3 audit_log entries (classification, decision, action)."""
        conn = get_in_memory_db()
        cursor = conn.cursor()

        test_events = [
            ("sub_audit_1", "card_expired", "Card expired", "card_expired", "BAD_REQUEST"),
            ("sub_audit_2", "payment_failed", "Insufficient balance", "payment_failed", "BAD_REQUEST"),
            ("sub_audit_3", "payment_risk_block", "Risk block", "payment_risk_block", "GATEWAY_ERROR"),
            ("sub_audit_4", "mandate_inactive", "Mandate revoked", "mandate_inactive", "BAD_REQUEST"),
            ("sub_audit_5", "payment_failed", "e-commerce disabled", "payment_failed", "BAD_REQUEST"),
        ]

        for i, (sub_id, reason, desc, err_reason, err_code) in enumerate(test_events, 1):
            cursor.execute(
                "INSERT INTO subscriptions (id, customer_id, plan_amount, currency, status, created_at) VALUES (?, ?, 1000, 'INR', 'active', '2026-09-04T00:00:00Z')",
                (sub_id, f"cust_{sub_id}")
            )
            cursor.execute(
                """
                INSERT INTO failure_events (subscription_id, external_event_id, event_type, error_code, error_reason, error_description, attempt_number, received_at)
                VALUES (?, ?, 'payment.failed', ?, ?, ?, 1, '2026-09-04T00:00:00Z')
                """,
                (sub_id, f"evt_audit_{i}", err_code, err_reason, desc)
            )
            fe_id = cursor.lastrowid
            conn.commit()

            process_failure_event(fe_id, conn=conn)

            # Query audit_log for this subscription
            cursor.execute("SELECT COUNT(*) FROM audit_log WHERE subscription_id = ?", (sub_id,))
            audit_count = cursor.fetchone()[0]
            self.assertGreaterEqual(audit_count, 3, f"Subscription '{sub_id}' had only {audit_count} audit_log entries (expected >= 3).")

        conn.close()

    def test_audit_log_append_only_immutability(self):
        """Confirms audit_log rows are never modified or deleted upon pipeline re-runs or duplicate events."""
        conn = get_in_memory_db()
        cursor = conn.cursor()

        sub_id = "sub_audit_immutability"
        cursor.execute("INSERT INTO subscriptions (id, customer_id, plan_amount, currency, status, created_at) VALUES (?, 'cust_immut', 1000, 'INR', 'active', '2026-09-04T00:00:00Z')", (sub_id,))
        cursor.execute(
            """
            INSERT INTO failure_events (subscription_id, external_event_id, event_type, error_code, error_reason, error_description, attempt_number, received_at)
            VALUES (?, 'evt_immut_1', 'payment.failed', 'BAD_REQUEST', 'card_expired', 'Card expired', 1, '2026-09-04T00:00:00Z')
            """,
            (sub_id,)
        )
        fe_id_1 = cursor.lastrowid
        conn.commit()

        # Run event 1
        process_failure_event(fe_id_1, conn=conn)

        cursor.execute("SELECT id, subscription_id, event_summary, timestamp FROM audit_log WHERE subscription_id = ?", (sub_id,))
        initial_entries = cursor.fetchall()
        initial_count = len(initial_entries)
        self.assertGreaterEqual(initial_count, 3)

        # Run event 2 for same subscription
        cursor.execute(
            """
            INSERT INTO failure_events (subscription_id, external_event_id, event_type, error_code, error_reason, error_description, attempt_number, received_at)
            VALUES (?, 'evt_immut_2', 'payment.failed', 'BAD_REQUEST', 'card_expired', 'Card expired second failure', 2, '2026-09-04T01:00:00Z')
            """,
            (sub_id,)
        )
        fe_id_2 = cursor.lastrowid
        conn.commit()

        process_failure_event(fe_id_2, conn=conn)

        cursor.execute("SELECT id, subscription_id, event_summary, timestamp FROM audit_log WHERE subscription_id = ?", (sub_id,))
        updated_entries = cursor.fetchall()
        updated_count = len(updated_entries)

        # Verify initial entries are byte-for-byte unchanged
        for idx in range(initial_count):
            self.assertEqual(initial_entries[idx], updated_entries[idx], "Audit log entry was modified or deleted!")

        # Verify new entries were APPENDED
        self.assertGreater(updated_count, initial_count)

        conn.close()

if __name__ == "__main__":
    unittest.main()
