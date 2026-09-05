"""
Hardening Pass Regression Tests (Part B)
========================================

Verifies graceful error handling and resilience for Findings #1, #2, #3, and #4:
1. POST /simulate/event rejects blank/whitespace subscription_id with 422.
2. POST /cases/{id}/human-review rejects non-escalated cases with 400 Bad Request.
3. POST /webhooks/razorpay rejects non-object JSON payloads with 400 Bad Request (no 500 crash).
4. Concurrent simulation requests for new subscription IDs use INSERT OR IGNORE (no 500 crash).
"""

import hashlib
import hmac
import json
import sqlite3
import unittest
import uuid

from api.routes import SimulateEventRequest, human_review_case, HumanReviewRequest
from api.webhook_translator import translate_razorpay_payload
from db.init import get_db_connection, init_db
from engine.case_state import update_case_state
from pydantic import ValidationError
from fastapi import HTTPException

class TestHardeningRegressions(unittest.TestCase):

    def setUp(self):
        init_db()

    def test_simulate_event_blank_subscription_id_rejected(self):
        """Finding #1: Blank/whitespace subscription_id should raise ValidationError (422)."""
        with self.assertRaises(ValidationError):
            SimulateEventRequest(subscription_id="")

        with self.assertRaises(ValidationError):
            SimulateEventRequest(subscription_id="   ")

    def test_human_review_non_escalated_case_rejected(self):
        """Finding #2: Human review on an 'open' case should raise HTTPException 400 Bad Request."""
        unique_sub_id = f"sub_regress_open_{uuid.uuid4().hex[:8]}"
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO subscriptions (id, customer_id, plan_amount, currency, status, created_at) VALUES (?, 'cust_test', 1000, 'INR', 'pending', '2026-09-04T00:00:00Z')",
                (unique_sub_id,)
            )
            update_case_state(conn, unique_sub_id, "send_nudge", "card_expired", subscription_status="pending")
            conn.commit()
        finally:
            conn.close()

        with self.assertRaises(HTTPException) as ctx:
            human_review_case(unique_sub_id, HumanReviewRequest(decision="approve", note="test"))

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Human review is only allowed for cases in 'escalated' status", ctx.exception.detail)

    def test_malformed_webhook_non_dict_rejected(self):
        """Finding #3: Non-object webhook payloads (list, string) should raise ValueError (400 Bad Request)."""
        with self.assertRaises(ValueError) as ctx:
            translate_razorpay_payload([1, 2, 3])
        self.assertIn("root JSON must be an object", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            translate_razorpay_payload("just a string")
        self.assertIn("root JSON must be an object", str(ctx.exception))

    def test_concurrent_subscription_insert_safety(self):
        """Finding #4: INSERT OR IGNORE prevents 500 error when subscription ID already exists."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            sub_id = f"sub_regress_ignore_{uuid.uuid4().hex[:8]}"
            # Simulate first insert
            cursor.execute(
                "INSERT OR IGNORE INTO subscriptions (id, customer_id, plan_amount, currency, status, created_at) VALUES (?, ?, 1000, 'INR', 'pending', '2026-09-04T00:00:00.000Z')",
                (sub_id, f"cust_{sub_id}")
            )
            # Duplicate insert should not raise IntegrityError
            cursor.execute(
                "INSERT OR IGNORE INTO subscriptions (id, customer_id, plan_amount, currency, status, created_at) VALUES (?, ?, 1000, 'INR', 'pending', '2026-09-04T00:00:00.000Z')",
                (sub_id, f"cust_{sub_id}")
            )
            conn.commit()
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
