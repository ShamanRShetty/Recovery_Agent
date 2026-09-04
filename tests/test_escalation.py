import unittest
import sqlite3
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.policy import decide_action, ACTION_ESCALATE
from pipeline.process_event import process_failure_event

def get_in_memory_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    schema_path = os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    return conn

class TestEscalationHandling(unittest.TestCase):

    def test_distinct_escalation_rule_ids(self):
        """Confirms that every distinct escalation scenario produces a specific, distinct playbook_rule_id."""
        escalation_scenarios = [
            # (category, confidence, case_state, sub_status, attempt, expected_rule)
            ("card_expired", 0.50, {"contact_count": 0}, "pending", 1, "low_confidence_escalation"),
            ("unclassified", 0.0, {"contact_count": 0}, "pending", 1, "low_confidence_escalation"),
            ("risk_block", 1.0, {"contact_count": 0}, "pending", 1, "rb_always_human_review"),
            ("card_expired", 1.0, {"contact_count": 2}, "pending", 3, "ce_contact_limit_reached"),
            ("card_not_enabled", 1.0, {"contact_count": 1}, "pending", 2, "cne_single_nudge_limit"),
            ("insufficient_funds", 1.0, {"contact_count": 1}, "halted", 4, "if_retries_exhausted"),
        ]

        expected_rules_seen = set()

        for cat, conf, state, status, attempt, expected_rule in escalation_scenarios:
            action, rule_id = decide_action(cat, conf, state, status, attempt)
            self.assertEqual(action, ACTION_ESCALATE, f"Scenario {cat} ({expected_rule}) did not return escalate.")
            self.assertEqual(rule_id, expected_rule, f"Scenario {cat} returned rule {rule_id}, expected {expected_rule}.")
            expected_rules_seen.add(rule_id)

        # Confirm we tested distinct rules
        self.assertGreaterEqual(len(expected_rules_seen), 4, "Escalation rule IDs must be distinct.")

    def test_escalated_case_state_status_becomes_escalated(self):
        """Confirms that when pipeline processes an escalated decision, case_state.status becomes 'escalated'."""
        conn = get_in_memory_db()
        cursor = conn.cursor()

        # Insert risk block failure event (triggers escalation)
        cursor.execute("INSERT INTO subscriptions (id, customer_id, plan_amount, currency, status, created_at) VALUES ('sub_esc_test', 'cust_esc', 1000, 'INR', 'active', '2026-09-04T00:00:00Z')")
        cursor.execute(
            """
            INSERT INTO failure_events (subscription_id, external_event_id, event_type, error_code, error_reason, error_description, attempt_number, received_at)
            VALUES ('sub_esc_test', 'evt_esc_1', 'payment.failed', 'GATEWAY_ERROR', 'payment_risk_block', 'High risk block', 1, '2026-09-04T00:00:00Z')
            """
        )
        fe_id = cursor.lastrowid
        conn.commit()

        # Process event through full pipeline
        summary = process_failure_event(fe_id, conn=conn)

        # Assert case_state status is 'escalated'
        self.assertEqual(summary["decision"]["action_type"], "escalate")
        self.assertEqual(summary["case_state"]["status"], "escalated")

        # Verify directly in SQLite
        cursor.execute("SELECT status FROM case_state WHERE subscription_id = 'sub_esc_test'")
        row = cursor.fetchone()
        self.assertEqual(row[0], "escalated")

        conn.close()

if __name__ == "__main__":
    unittest.main()
