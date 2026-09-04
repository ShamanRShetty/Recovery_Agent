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

class TestE2EScenarios(unittest.TestCase):

    def test_successful_recovery_card_expired(self):
        """Card expired failure -> nudge sent -> subscription.activated arrives -> recovered with zero further contact."""
        conn = get_in_memory_db()
        cursor = conn.cursor()

        sub_id = "sub_e2e_rec_1"
        cursor.execute("INSERT INTO subscriptions (id, customer_id, plan_amount, currency, status, created_at) VALUES (?, 'cust_rec', 1000, 'INR', 'pending', '2026-09-04T00:00:00Z')", (sub_id,))

        # Event 1: payment.failed (card_expired)
        cursor.execute(
            """
            INSERT INTO failure_events (subscription_id, external_event_id, event_type, error_code, error_reason, error_description, attempt_number, received_at)
            VALUES (?, 'evt_e2e_1', 'payment.failed', 'BAD_REQUEST', 'card_expired', 'Card expired', 1, '2026-09-04T00:00:00Z')
            """,
            (sub_id,)
        )
        fe_id_1 = cursor.lastrowid
        conn.commit()

        res1 = process_failure_event(fe_id_1, conn=conn)
        self.assertEqual(res1["decision"]["action_type"], "send_nudge")
        self.assertEqual(res1["case_state"]["contact_count"], 1)

        # Event 2: subscription.activated event (customer updated card and paid)
        cursor.execute("UPDATE subscriptions SET status = 'active' WHERE id = ?", (sub_id,))
        cursor.execute(
            """
            INSERT INTO failure_events (subscription_id, external_event_id, event_type, error_code, error_reason, error_description, attempt_number, received_at)
            VALUES (?, 'evt_e2e_2', 'subscription.activated', 'BAD_REQUEST', 'card_expired', 'Card updated and subscription reactivated', 2, '2026-09-04T01:00:00Z')
            """,
            (sub_id,)
        )
        fe_id_2 = cursor.lastrowid
        conn.commit()

        res2 = process_failure_event(fe_id_2, conn=conn)
        self.assertEqual(res2["decision"]["action_type"], "stop")
        self.assertEqual(res2["case_state"]["status"], "recovered")
        self.assertEqual(res2["case_state"]["contact_count"], 1)

        conn.close()

    def test_failed_recovery_card_expired_max_contacts(self):
        """Card expired failure -> 2 nudges sent -> 3rd failure event arrives -> case escalates, contact_count ceiling=2."""
        conn = get_in_memory_db()
        cursor = conn.cursor()

        sub_id = "sub_e2e_fail_1"
        cursor.execute("INSERT INTO subscriptions (id, customer_id, plan_amount, currency, status, created_at) VALUES (?, 'cust_fail', 1000, 'INR', 'pending', '2026-09-04T00:00:00Z')", (sub_id,))

        # Event 1: Nudge 1
        cursor.execute("INSERT INTO failure_events (subscription_id, external_event_id, event_type, error_code, error_reason, error_description, attempt_number, received_at) VALUES (?, 'evt_f_1', 'payment.failed', 'BAD_REQUEST', 'card_expired', 'Card expired', 1, '2026-09-04T00:00:00Z')", (sub_id,))
        res1 = process_failure_event(cursor.lastrowid, conn=conn)
        self.assertEqual(res1["decision"]["action_type"], "send_nudge")
        self.assertEqual(res1["case_state"]["contact_count"], 1)

        # Event 2: Nudge 2
        cursor.execute("INSERT INTO failure_events (subscription_id, external_event_id, event_type, error_code, error_reason, error_description, attempt_number, received_at) VALUES (?, 'evt_f_2', 'payment.failed', 'BAD_REQUEST', 'card_expired', 'Card expired', 2, '2026-09-04T01:00:00Z')", (sub_id,))
        res2 = process_failure_event(cursor.lastrowid, conn=conn)
        self.assertEqual(res2["decision"]["action_type"], "send_nudge")
        self.assertEqual(res2["case_state"]["contact_count"], 2)

        # Event 3: Escalation (contact count limit reached)
        cursor.execute("INSERT INTO failure_events (subscription_id, external_event_id, event_type, error_code, error_reason, error_description, attempt_number, received_at) VALUES (?, 'evt_f_3', 'payment.failed', 'BAD_REQUEST', 'card_expired', 'Card expired', 3, '2026-09-04T02:00:00Z')", (sub_id,))
        res3 = process_failure_event(cursor.lastrowid, conn=conn)
        self.assertEqual(res3["decision"]["action_type"], "escalate")
        self.assertEqual(res3["case_state"]["status"], "escalated")
        self.assertEqual(res3["case_state"]["contact_count"], 2) # Ceiling enforced!

        conn.close()

    def test_insufficient_funds_native_retry_zero_contact_recovery(self):
        """Insufficient funds -> attempt 1 wait -> Razorpay native retry succeeds -> recovered with contact_count=0."""
        conn = get_in_memory_db()
        cursor = conn.cursor()

        sub_id = "sub_e2e_inf_1"
        cursor.execute("INSERT INTO subscriptions (id, customer_id, plan_amount, currency, status, created_at) VALUES (?, 'cust_inf', 1000, 'INR', 'pending', '2026-09-04T00:00:00Z')", (sub_id,))

        # Event 1: payment.failed (insufficient_funds, attempt 1)
        cursor.execute(
            """
            INSERT INTO failure_events (subscription_id, external_event_id, event_type, error_code, error_reason, error_description, attempt_number, received_at)
            VALUES (?, 'evt_inf_1', 'payment.failed', 'BAD_REQUEST', 'payment_failed', 'Insufficient balance in account', 1, '2026-09-04T00:00:00Z')
            """,
            (sub_id,)
        )
        res1 = process_failure_event(cursor.lastrowid, conn=conn)
        self.assertEqual(res1["decision"]["action_type"], "wait")
        self.assertEqual(res1["case_state"]["contact_count"], 0)

        # Native retry succeeds -> subscription.activated arrives
        cursor.execute("UPDATE subscriptions SET status = 'active' WHERE id = ?", (sub_id,))
        cursor.execute(
            """
            INSERT INTO failure_events (subscription_id, external_event_id, event_type, error_code, error_reason, error_description, attempt_number, received_at)
            VALUES (?, 'evt_inf_2', 'subscription.activated', 'BAD_REQUEST', 'payment_failed', 'Insufficient balance resolved, payment successful on native retry', 2, '2026-09-04T06:00:00Z')
            """,
            (sub_id,)
        )
        res2 = process_failure_event(cursor.lastrowid, conn=conn)
        self.assertEqual(res2["decision"]["action_type"], "stop")
        self.assertEqual(res2["case_state"]["status"], "recovered")
        self.assertEqual(res2["case_state"]["contact_count"], 0)

        conn.close()

if __name__ == "__main__":
    unittest.main()
