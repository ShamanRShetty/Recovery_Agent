"""
Verification Script for Phase 6 (Real Razorpay Webhook Ingestion)
===================================================================

Executes all 6 required verification steps for Phase 6:
1 & 2 & 3. Runs unit test suite for webhook security & translator
4. Simulates full request with valid signature against POST /webhooks/razorpay
5. Repeats request with exact same X-Razorpay-Event-Id -> 200 duplicate_ignored
6. Repeats request with wrong signature -> 400 rejection & no DB write
"""

import hashlib
import hmac
import json
import os
import sqlite3
import sys
import unittest
import urllib.error
import urllib.request

BASE_URL = "http://127.0.0.1:8000"
DB_PATH = "db/recovery_agent.db"
TEST_SECRET = "test_razorpay_webhook_secret_key_2026"

def post_raw_webhook(body_bytes, headers):
    url = f"{BASE_URL}/webhooks/razorpay"
    req = urllib.request.Request(url, data=body_bytes, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, body

def run_verification():
    print("=" * 80)
    print("PHASE 6 VERIFICATION RUNNER")
    print("=" * 80)

    # Set environment variable for test
    os.environ["RAZORPAY_WEBHOOK_SECRET"] = TEST_SECRET

    # -------------------------------------------------------------------------
    # STEPS 1, 2, 3: Run Unit Test Suite
    # -------------------------------------------------------------------------
    print("\n--- STEPS 1-3: Running Unit Test Suite (Security & Translator) ---")
    loader = unittest.TestLoader()
    suite = loader.discover("tests")
    runner = unittest.TextTestRunner(verbosity=2)
    test_result = runner.run(suite)
    if not test_result.wasSuccessful():
        print("ERROR: Unit tests failed!")
        sys.exit(1)

    # -------------------------------------------------------------------------
    # STEP 4: Simulate full request locally with valid signature
    # -------------------------------------------------------------------------
    print("\n--- STEP 4: POST /webhooks/razorpay with valid signature ---")
    evt_id = "evt_rzp_test_valid_001"
    sub_id = "sub_rzp_test_expired_101"

    payload_dict = {
        "entity": "event",
        "account_id": "acc_phase6_test",
        "event": "payment.failed",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_rzp_phase6_001",
                    "amount": 250000,
                    "currency": "INR",
                    "status": "failed",
                    "order_id": "order_rzp_001",
                    "invoice_id": "inv_rzp_001",
                    "subscription_id": sub_id,
                    "error": {
                        "code": "BAD_REQUEST_ERROR",
                        "description": "Card has expired. Please update payment method.",
                        "source": "bank",
                        "step": "payment_authorization",
                        "reason": "card_expired"
                    }
                }
            },
            "subscription": {
                "entity": {
                    "id": sub_id,
                    "status": "active"
                }
            }
        },
        "created_at": 1600000000
    }

    raw_body = json.dumps(payload_dict).encode("utf-8")
    signature = hmac.new(TEST_SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-Razorpay-Signature": signature,
        "X-Razorpay-Event-Id": evt_id
    }

    status, body = post_raw_webhook(raw_body, headers)
    print(f"HTTP Status: {status} (Expected 200)")
    print(f"Response: {json.dumps(body, indent=2)}")

    # Verify DB rows created across failure_events, classifications, decisions, actions, audit_log, case_state
    print("\n--- DB Rows Created for Step 4 ---")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("\n1. failure_events row:")
    row = cursor.execute("SELECT * FROM failure_events WHERE external_event_id = ?", (evt_id,)).fetchone()
    print(json.dumps(dict(row), indent=2) if row else "None")

    print("\n2. case_state row:")
    row = cursor.execute("SELECT * FROM case_state WHERE subscription_id = ?", (sub_id,)).fetchone()
    print(json.dumps(dict(row), indent=2) if row else "None")

    # -------------------------------------------------------------------------
    # STEP 5: Repeat step 4 with SAME event ID -> 200 duplicate_ignored
    # -------------------------------------------------------------------------
    print("\n--- STEP 5: POST /webhooks/razorpay with SAME X-Razorpay-Event-Id (Duplicate Test) ---")
    status2, body2 = post_raw_webhook(raw_body, headers)
    print(f"HTTP Status: {status2} (Expected 200)")
    print(f"Response: {json.dumps(body2, indent=2)}")

    fe_count = cursor.execute("SELECT count(*) FROM failure_events WHERE external_event_id = ?", (evt_id,)).fetchone()[0]
    print(f"Count of failure_events rows for event '{evt_id}': {fe_count} (Expected: 1)")

    # -------------------------------------------------------------------------
    # STEP 6: Repeat with WRONG signature -> 400 rejection & no DB write
    # -------------------------------------------------------------------------
    print("\n--- STEP 6: POST /webhooks/razorpay with WRONG signature ---")
    wrong_headers = {
        "Content-Type": "application/json",
        "X-Razorpay-Signature": "invalid_signature_hash_0000000000000000",
        "X-Razorpay-Event-Id": "evt_rzp_tampered_999"
    }
    status3, body3 = post_raw_webhook(raw_body, wrong_headers)
    print(f"HTTP Status: {status3} (Expected 400)")
    print(f"Response: {json.dumps(body3, indent=2)}")

    tampered_row = cursor.execute("SELECT * FROM failure_events WHERE external_event_id = 'evt_rzp_tampered_999'").fetchone()
    print(f"DB search for rejected event 'evt_rzp_tampered_999': {tampered_row} (Expected: None)")

    conn.close()

if __name__ == "__main__":
    run_verification()
