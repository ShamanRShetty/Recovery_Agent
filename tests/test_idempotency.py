import unittest
import asyncio
import json
import hmac
import hashlib
import sqlite3
import uuid
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api.webhooks import handle_razorpay_webhook
from db.init import get_db_connection

class MockRequest:
    def __init__(self, body_bytes: bytes, headers: dict):
        self._body_bytes = body_bytes
        self.headers = headers

    async def body(self) -> bytes:
        return self._body_bytes

class TestIdempotencyAndDuplicates(unittest.TestCase):

    def setUp(self):
        self.secret = "test_webhook_secret_key_123"
        os.environ["RAZORPAY_WEBHOOK_SECRET"] = self.secret

    def _generate_signature(self, body_bytes: bytes) -> str:
        return hmac.new(
            self.secret.encode("utf-8"),
            body_bytes,
            hashlib.sha256
        ).hexdigest()

    def test_duplicate_external_event_id_ignored(self):
        """Confirms re-sending same X-Razorpay-Event-Id returns duplicate_ignored and inserts only 1 row."""
        unique_suffix = uuid.uuid4().hex[:8]
        evt_id = f"evt_dedup_{unique_suffix}"
        sub_id = f"sub_dedup_{unique_suffix}"

        payload = {
            "entity": "event",
            "account_id": "acc_1001",
            "event": "payment.failed",
            "contains": ["payment", "subscription"],
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_1001",
                        "status": "failed",
                        "error_code": "BAD_REQUEST_ERROR",
                        "error_reason": "card_expired",
                        "error_description": "Card has expired"
                    }
                },
                "subscription": {
                    "entity": {
                        "id": sub_id,
                        "customer_id": "cust_dedup_1001"
                    }
                }
            }
        }
        body_bytes = json.dumps(payload).encode("utf-8")
        sig = self._generate_signature(body_bytes)

        headers = {
            "X-Razorpay-Signature": sig,
            "X-Razorpay-Event-Id": evt_id,
            "Content-Type": "application/json"
        }

        # First webhook call -> 200 processed
        req1 = MockRequest(body_bytes, headers)
        res1 = asyncio.run(handle_razorpay_webhook(req1))
        body1 = json.loads(res1.body.decode("utf-8"))
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(body1["status"], "processed")

        # Second webhook call (duplicate) -> 200 duplicate_ignored
        req2 = MockRequest(body_bytes, headers)
        res2 = asyncio.run(handle_razorpay_webhook(req2))
        body2 = json.loads(res2.body.decode("utf-8"))
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(body2["status"], "duplicate_ignored")

        # Verify database has exactly 1 failure_events row for this external_event_id
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM failure_events WHERE external_event_id = ?", (evt_id,))
        count = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)

    def test_different_external_event_ids_treated_as_distinct(self):
        """Confirms 2 different X-Razorpay-Event-Ids with identical payloads are processed as distinct events."""
        unique_suffix = uuid.uuid4().hex[:8]
        evt_id_a = f"evt_distinct_A_{unique_suffix}"
        evt_id_b = f"evt_distinct_B_{unique_suffix}"
        sub_id = f"sub_distinct_{unique_suffix}"

        payload = {
            "entity": "event",
            "account_id": "acc_2001",
            "event": "payment.failed",
            "contains": ["payment", "subscription"],
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_2001",
                        "status": "failed",
                        "error_code": "BAD_REQUEST_ERROR",
                        "error_reason": "card_expired",
                        "error_description": "Card has expired"
                    }
                },
                "subscription": {
                    "entity": {
                        "id": sub_id,
                        "customer_id": "cust_distinct_2001"
                    }
                }
            }
        }
        body_bytes = json.dumps(payload).encode("utf-8")
        sig = self._generate_signature(body_bytes)

        # Call A
        req_a = MockRequest(body_bytes, {
            "X-Razorpay-Signature": sig,
            "X-Razorpay-Event-Id": evt_id_a,
            "Content-Type": "application/json"
        })
        res_a = asyncio.run(handle_razorpay_webhook(req_a))
        body_a = json.loads(res_a.body.decode("utf-8"))
        self.assertEqual(res_a.status_code, 200)
        self.assertEqual(body_a["status"], "processed")

        # Call B (different event id, identical payload)
        req_b = MockRequest(body_bytes, {
            "X-Razorpay-Signature": sig,
            "X-Razorpay-Event-Id": evt_id_b,
            "Content-Type": "application/json"
        })
        res_b = asyncio.run(handle_razorpay_webhook(req_b))
        body_b = json.loads(res_b.body.decode("utf-8"))
        self.assertEqual(res_b.status_code, 200)
        self.assertEqual(body_b["status"], "processed")

        # Verify database has 2 failure_events rows for this subscription
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM failure_events WHERE subscription_id = ?", (sub_id,))
        count = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(count, 2)

if __name__ == "__main__":
    unittest.main()
