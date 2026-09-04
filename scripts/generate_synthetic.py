"""
Synthetic Dataset Generator for Failed Subscription Recovery Agent (Phase 1)
=============================================================================

Dataset Design & Scenario Distribution Summary:
Total failure_events rows: EXACTLY 40 across 23 subscriptions

Category Scenario Breakdown:
- insufficient_funds (8 events across 4 subscriptions):
  - 4 events (2 subs: sub_synth_ins_1, sub_synth_ins_2) representing eventual resolution via native retry (payment.failed + subscription.activated)
  - 2 events (1 sub: sub_synth_ins_3) representing retries exhausting to halted state (payment.failed + subscription.halted)
  - 2 events (1 sub: sub_synth_ins_4) representing resolution in cycle 1, then second failure in cycle 2

- card_expired (8 events across 5 subscriptions):
  - 3 events (sub_synth_exp_1: 2 events, sub_synth_exp_2: 1 event) recovered after 1 contact-equivalent pattern
  - 2 events (sub_synth_exp_3: 2 events) recovered only after second failure event
  - 3 events (sub_synth_exp_4: 1 event, sub_synth_exp_5: 2 events) unrecovered (ends without subscription.activated, includes out-of-order delivery)

- card_not_enabled (5 events across 3 subscriptions):
  - 3 events (sub_synth_cne_1: 2 events, sub_synth_cne_2: 1 event) resolved
  - 2 events (sub_synth_cne_3: 2 events) unresolved

- risk_block (5 events across 4 subscriptions):
  - 3 events (sub_synth_rsk_1, sub_synth_rsk_2, sub_synth_rsk_3) with terminal risk blocks
  - 2 events (sub_synth_rsk_4: 2 events) where risk_block is followed by card_expired on same subscription_id

- mandate_cancelled (5 events across 5 subscriptions):
  - 4 clean terminal cancellations (sub_synth_mnd_1, sub_synth_mnd_2, sub_synth_mnd_3, sub_synth_mnd_4)
  - 1 new independent subscription for same customer_id (sub_synth_mnd_5)

- unclassified / ambiguous (9 events across 7 subscriptions):
  - 3 vague-but-plausibly classifiable descriptions (sub_synth_amb_1, sub_synth_amb_2, sub_synth_amb_3)
  - 3 generic / uninterpretable descriptions including NULL & attempt > 1 (sub_synth_amb_4, sub_synth_amb_5, sub_synth_amb_6)
  - 3 contradictory signal descriptions (sub_synth_amb_7: 3 events)

Mandatory Edge Cases Embedded:
1. Webhook Idempotency Duplicate: Attempt duplicate insert of external_event_id 'evt_synth_ins_001'
2. Out-of-order Delivery: sub_synth_exp_5 has subscription.halted received_at earlier than payment.failed
3. NULL Error Description: sub_synth_amb_6 has NULL error_description
4. Attempt Number > 1 on First Event: sub_synth_amb_4 has attempt_number = 3 on first event
"""

import json
import os
import sqlite3
import sys

# Ensure UTF-8 output encoding on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from db.init import get_db_connection, init_db

def build_raw_payload(event_type, sub_id, evt_id, amount, error_code, error_desc, error_source, error_step, error_reason):
    """Generates a synthetic Razorpay-shaped webhook JSON string."""
    payload_obj = {
        "entity": "event",
        "account_id": "acc_synth_razorpay_01",
        "event": event_type,
        "contains": ["payment" if "payment" in event_type else "subscription"],
        "payload": {
            "payment" if "payment" in event_type else "subscription": {
                "entity": {
                    "id": f"pay_{evt_id}",
                    "subscription_id": sub_id,
                    "amount": amount,
                    "currency": "INR",
                    "status": "failed" if "failed" in event_type else ("halted" if "halted" in event_type else "activated"),
                    "description": "Subscription payment - Synthetic Data",
                    "error_code": error_code,
                    "error_description": error_desc,
                    "error_source": error_source,
                    "error_step": error_step,
                    "error_reason": error_reason
                }
            }
        },
        "created_at": 1772359200,
        "synth": True
    }
    return json.dumps(payload_obj)

def generate_synthetic_data():
    print("=" * 60)
    print("PHASE 1: SYNTHETIC DATASET GENERATION")
    print("=" * 60)

    # Re-initialize DB to ensure schema exists
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()

    # Idempotent cleanup of all tables respecting foreign key order
    cursor.execute("DELETE FROM audit_log;")
    cursor.execute("DELETE FROM actions;")
    cursor.execute("DELETE FROM decisions;")
    cursor.execute("DELETE FROM classifications;")
    cursor.execute("DELETE FROM case_state;")
    cursor.execute("DELETE FROM failure_events;")
    cursor.execute("DELETE FROM subscriptions;")
    conn.commit()


    # 1. Subscriptions Dataset (23 total subscriptions)
    subscriptions_data = [
        # insufficient_funds (4 subs)
        ("sub_synth_ins_1", "cust_ins_101", 49900, "INR", "active"),
        ("sub_synth_ins_2", "cust_ins_102", 99900, "INR", "active"),
        ("sub_synth_ins_3", "cust_ins_103", 149900, "INR", "halted"),
        ("sub_synth_ins_4", "cust_ins_104", 299900, "INR", "active"),
        
        # card_expired (5 subs)
        ("sub_synth_exp_1", "cust_exp_201", 50000, "INR", "active"),
        ("sub_synth_exp_2", "cust_exp_202", 75000, "INR", "active"),
        ("sub_synth_exp_3", "cust_exp_203", 120000, "INR", "active"),
        ("sub_synth_exp_4", "cust_exp_204", 199900, "INR", "pending"),
        ("sub_synth_exp_5", "cust_exp_205", 249900, "INR", "halted"),

        # card_not_enabled (3 subs)
        ("sub_synth_cne_1", "cust_cne_301", 89900, "INR", "active"),
        ("sub_synth_cne_2", "cust_cne_302", 129900, "INR", "active"),
        ("sub_synth_cne_3", "cust_cne_303", 199900, "INR", "pending"),

        # risk_block (4 subs)
        ("sub_synth_rsk_1", "cust_rsk_401", 499900, "INR", "halted"),
        ("sub_synth_rsk_2", "cust_rsk_402", 999900, "INR", "halted"),
        ("sub_synth_rsk_3", "cust_rsk_403", 1500000, "INR", "halted"),
        ("sub_synth_rsk_4", "cust_rsk_404", 350000, "INR", "halted"),

        # mandate_cancelled (5 subs)
        ("sub_synth_mnd_1", "cust_mnd_501", 69900, "INR", "cancelled"),
        ("sub_synth_mnd_2", "cust_mnd_502", 119900, "INR", "cancelled"),
        ("sub_synth_mnd_3", "cust_mnd_503", 179900, "INR", "cancelled"),
        ("sub_synth_mnd_4", "cust_mnd_repeat", 249900, "INR", "cancelled"),
        ("sub_synth_mnd_5", "cust_mnd_repeat", 299900, "INR", "active"), # Edge Case: New subscription for same customer

        # unclassified / ambiguous (7 subs)
        ("sub_synth_amb_1", "cust_amb_601", 59900, "INR", "pending"),
        ("sub_synth_amb_2", "cust_amb_602", 89900, "INR", "pending"),
        ("sub_synth_amb_3", "cust_amb_603", 119900, "INR", "pending"),
        ("sub_synth_amb_4", "cust_amb_604", 149900, "INR", "pending"),
        ("sub_synth_amb_5", "cust_amb_605", 199900, "INR", "pending"),
        ("sub_synth_amb_6", "cust_amb_606", 249900, "INR", "pending"),
        ("sub_synth_amb_7", "cust_amb_607", 349900, "INR", "pending"),
    ]

    cursor.executemany(
        "INSERT INTO subscriptions (id, customer_id, plan_amount, currency, status) VALUES (?, ?, ?, ?, ?)",
        subscriptions_data
    )
    conn.commit()
    print(f"[OK] Seeded {len(subscriptions_data)} subscriptions.")

    # 2. Failure Events Dataset (EXACTLY 40 events)
    # Tuples: (subscription_id, external_event_id, event_type, error_code, error_reason, error_description, error_source, error_step, attempt_number, plan_amount, received_at, scenario_category)
    events_data = [
        # --- INSUFFICIENT FUNDS (8 events) ---
        # Sub 1: Native retry eventual recovery (2 events)
        ("sub_synth_ins_1", "evt_synth_ins_001", "payment.failed", "BAD_REQUEST_ERROR", "payment_failed", "Insufficient balance in customer account", "bank", "payment_execution", 1, 49900, "2026-03-01T10:00:00.000Z", "insufficient_funds"),
        ("sub_synth_ins_1", "evt_synth_ins_002", "subscription.activated", None, None, None, None, None, 2, 49900, "2026-03-02T10:00:00.000Z", "insufficient_funds"),
        
        # Sub 2: Native retry eventual recovery (2 events)
        ("sub_synth_ins_2", "evt_synth_ins_003", "payment.failed", "BAD_REQUEST_ERROR", "payment_failed", "Low balance in linked account", "bank", "payment_execution", 1, 99900, "2026-03-03T10:00:00.000Z", "insufficient_funds"),
        ("sub_synth_ins_2", "evt_synth_ins_004", "subscription.activated", None, None, None, None, None, 2, 99900, "2026-03-04T10:00:00.000Z", "insufficient_funds"),
        
        # Sub 3: Retries exhausted to halted (2 events)
        ("sub_synth_ins_3", "evt_synth_ins_005", "payment.failed", "BAD_REQUEST_ERROR", "payment_failed", "Customer bank account balance insufficient", "bank", "payment_execution", 1, 149900, "2026-03-05T10:00:00.000Z", "insufficient_funds"),
        ("sub_synth_ins_3", "evt_synth_ins_006", "subscription.halted", "BAD_REQUEST_ERROR", "payment_failed", "Max retries reached due to insufficient funds", "gateway", "payment_execution", 4, 149900, "2026-03-08T10:00:00.000Z", "insufficient_funds"),

        # Sub 4: Resolved cycle 1, fails again in cycle 2 (2 events)
        ("sub_synth_ins_4", "evt_synth_ins_007", "payment.failed", "BAD_REQUEST_ERROR", "payment_failed", "Account balance low for recurring charge", "bank", "payment_execution", 1, 299900, "2026-02-01T10:00:00.000Z", "insufficient_funds"),
        ("sub_synth_ins_4", "evt_synth_ins_008", "payment.failed", "BAD_REQUEST_ERROR", "payment_failed", "Insufficient balance on monthly renewal cycle", "bank", "payment_execution", 1, 299900, "2026-03-01T10:00:00.000Z", "insufficient_funds"),

        # --- CARD EXPIRED (8 events) ---
        # Sub 1: Recovered after 1 contact pattern (2 events)
        ("sub_synth_exp_1", "evt_synth_exp_001", "payment.failed", "BAD_REQUEST_ERROR", "card_expired", "Card has expired", "issuer", "payment_authorization", 1, 50000, "2026-03-01T11:00:00.000Z", "card_expired"),
        ("sub_synth_exp_1", "evt_synth_exp_002", "subscription.activated", None, None, None, None, None, 2, 50000, "2026-03-03T11:00:00.000Z", "card_expired"),

        # Sub 2: Recovered after 1 contact pattern (1 event - failure before update)
        ("sub_synth_exp_2", "evt_synth_exp_003", "payment.failed", "BAD_REQUEST_ERROR", "card_expired", "Expired card details used for auto-debit", "issuer", "payment_authorization", 1, 75000, "2026-03-02T11:00:00.000Z", "card_expired"),

        # Sub 3: Recovered only after second failure event (2 events)
        ("sub_synth_exp_3", "evt_synth_exp_004", "payment.failed", "BAD_REQUEST_ERROR", "card_expired", "Card expiry date in past", "issuer", "payment_authorization", 1, 120000, "2026-03-03T11:00:00.000Z", "card_expired"),
        ("sub_synth_exp_3", "evt_synth_exp_005", "payment.failed", "BAD_REQUEST_ERROR", "card_expired", "Card expired, update required", "issuer", "payment_authorization", 2, 120000, "2026-03-05T11:00:00.000Z", "card_expired"),

        # Sub 4: Unrecovered (1 event)
        ("sub_synth_exp_4", "evt_synth_exp_006", "payment.failed", "BAD_REQUEST_ERROR", "card_expired", "Card expired during recurring charge", "issuer", "payment_authorization", 1, 199900, "2026-03-04T11:00:00.000Z", "card_expired"),

        # Sub 5: Unrecovered with Out-Of-Order Delivery edge case (2 events)
        # EDGE CASE: subscription.halted received_at (10:00) is EARLIER than payment.failed received_at (12:00)
        ("sub_synth_exp_5", "evt_synth_exp_007", "payment.failed", "BAD_REQUEST_ERROR", "card_expired", "Card has expired", "issuer", "payment_authorization", 1, 249900, "2026-03-06T12:00:00.000Z", "card_expired"),
        ("sub_synth_exp_5", "evt_synth_exp_008", "subscription.halted", "BAD_REQUEST_ERROR", "card_expired", "Subscription halted due to expired card", "gateway", "payment_authorization", 2, 249900, "2026-03-06T10:00:00.000Z", "card_expired"),

        # --- CARD NOT ENABLED (5 events) ---
        # Sub 1: Resolved (2 events)
        ("sub_synth_cne_1", "evt_synth_cne_001", "payment.failed", "BAD_REQUEST_ERROR", "payment_failed", "International or e-commerce transaction not enabled on card", "bank", "payment_authorization", 1, 89900, "2026-03-01T12:00:00.000Z", "card_not_enabled"),
        ("sub_synth_cne_1", "evt_synth_cne_002", "subscription.activated", None, None, None, None, None, 2, 89900, "2026-03-03T12:00:00.000Z", "card_not_enabled"),

        # Sub 2: Resolved (1 event)
        ("sub_synth_cne_2", "evt_synth_cne_003", "payment.failed", "BAD_REQUEST_ERROR", "payment_failed", "Online payment permissions disabled on card", "bank", "payment_authorization", 1, 129900, "2026-03-02T12:00:00.000Z", "card_not_enabled"),

        # Sub 3: Unresolved (2 events)
        ("sub_synth_cne_3", "evt_synth_cne_004", "payment.failed", "BAD_REQUEST_ERROR", "payment_failed", "Recurring e-mandate transactions not allowed on card type", "bank", "payment_authorization", 1, 199900, "2026-03-03T12:00:00.000Z", "card_not_enabled"),
        ("sub_synth_cne_3", "evt_synth_cne_005", "payment.failed", "BAD_REQUEST_ERROR", "payment_failed", "E-commerce channel disabled by cardholder", "bank", "payment_authorization", 2, 199900, "2026-03-05T12:00:00.000Z", "card_not_enabled"),

        # --- RISK BLOCK (5 events) ---
        # Sub 1: Terminal risk block (1 event)
        ("sub_synth_rsk_1", "evt_synth_rsk_001", "payment.failed", "GATEWAY_ERROR", "payment_risk_block", "High risk transaction blocked by fraud prevention engine", "gateway", "payment_authorization", 1, 499900, "2026-03-01T13:00:00.000Z", "risk_block"),

        # Sub 2: Terminal risk block (1 event)
        ("sub_synth_rsk_2", "evt_synth_rsk_002", "payment.failed", "GATEWAY_ERROR", "payment_risk_block", "Suspected fraudulent activity block by issuer", "issuer", "payment_authorization", 1, 999900, "2026-03-02T13:00:00.000Z", "risk_block"),

        # Sub 3: Terminal risk block (1 event)
        ("sub_synth_rsk_3", "evt_synth_rsk_003", "payment.failed", "GATEWAY_ERROR", "payment_risk_block", "Issuer security policy risk restriction enforced", "issuer", "payment_authorization", 1, 1500000, "2026-03-03T13:00:00.000Z", "risk_block"),

        # Sub 4: Risk block followed by second event of DIFFERENT category (card_expired) (2 events)
        ("sub_synth_rsk_4", "evt_synth_rsk_004", "payment.failed", "GATEWAY_ERROR", "payment_risk_block", "Risk engine blocked authorization", "gateway", "payment_authorization", 1, 350000, "2026-03-04T13:00:00.000Z", "risk_block"),
        ("sub_synth_rsk_4", "evt_synth_rsk_005", "payment.failed", "BAD_REQUEST_ERROR", "card_expired", "Card has expired", "issuer", "payment_authorization", 2, 350000, "2026-03-06T13:00:00.000Z", "risk_block"),

        # --- MANDATE CANCELLED (5 events) ---
        # Sub 1: Clean terminal cancellation (1 event)
        ("sub_synth_mnd_1", "evt_synth_mnd_001", "subscription.cancelled", "BAD_REQUEST_ERROR", "mandate_inactive", "Mandate revoked by customer at bank", "bank", "mandate_validation", 1, 69900, "2026-03-01T14:00:00.000Z", "mandate_cancelled"),

        # Sub 2: Clean terminal cancellation (1 event)
        ("sub_synth_mnd_2", "evt_synth_mnd_002", "subscription.cancelled", "BAD_REQUEST_ERROR", "mandate_inactive", "Autopay mandate cancelled by user", "bank", "mandate_validation", 1, 119900, "2026-03-02T14:00:00.000Z", "mandate_cancelled"),

        # Sub 3: Clean terminal cancellation (1 event)
        ("sub_synth_mnd_3", "evt_synth_mnd_003", "subscription.cancelled", "BAD_REQUEST_ERROR", "mandate_inactive", "E-mandate registration cancelled", "bank", "mandate_validation", 1, 179900, "2026-03-03T14:00:00.000Z", "mandate_cancelled"),

        # Sub 4: Clean terminal cancellation for repeating customer (1 event)
        ("sub_synth_mnd_4", "evt_synth_mnd_004", "subscription.cancelled", "BAD_REQUEST_ERROR", "mandate_inactive", "Customer cancelled recurring mandate", "bank", "mandate_validation", 1, 249900, "2026-02-15T14:00:00.000Z", "mandate_cancelled"),

        # Sub 5: New subscription for same customer_id (1 event)
        ("sub_synth_mnd_5", "evt_synth_mnd_005", "payment.failed", "BAD_REQUEST_ERROR", "mandate_inactive", "Mandate not active for new subscription", "bank", "mandate_validation", 1, 299900, "2026-03-05T14:00:00.000Z", "mandate_cancelled"),

        # --- UNCLASSIFIED / AMBIGUOUS (9 events) ---
        # 3 Vague-but-plausibly-classifiable descriptions
        ("sub_synth_amb_1", "evt_synth_amb_001", "payment.failed", "BAD_REQUEST_ERROR", "payment_failed", "Unable to process transaction due to account status", "bank", "payment_execution", 1, 59900, "2026-03-01T15:00:00.000Z", "unclassified"),
        ("sub_synth_amb_2", "evt_synth_amb_002", "payment.failed", "BAD_REQUEST_ERROR", "payment_failed", "Payment declined by issuer bank during validation", "issuer", "payment_authorization", 1, 89900, "2026-03-02T15:00:00.000Z", "unclassified"),
        ("sub_synth_amb_3", "evt_synth_amb_003", "payment.failed", "BAD_REQUEST_ERROR", "payment_failed", "Card authorization query returned non-zero response code", "gateway", "payment_authorization", 1, 119900, "2026-03-03T15:00:00.000Z", "unclassified"),

        # 3 Generic / uninterpretable descriptions (including NULL)
        # EDGE CASE: sub_synth_amb_4 has attempt_number = 3 on first event
        ("sub_synth_amb_4", "evt_synth_amb_004", "payment.failed", "BAD_REQUEST_ERROR", "payment_failed", "transaction could not be completed", "gateway", "payment_execution", 3, 149900, "2026-03-04T15:00:00.000Z", "unclassified"),
        ("sub_synth_amb_5", "evt_synth_amb_005", "payment.failed", "SERVER_ERROR", "system_error", "An unexpected system error occurred at processing node", "gateway", "payment_execution", 1, 199900, "2026-03-05T15:00:00.000Z", "unclassified"),
        # EDGE CASE: sub_synth_amb_6 has NULL error_description
        ("sub_synth_amb_6", "evt_synth_amb_006", "payment.failed", "BAD_REQUEST_ERROR", "payment_failed", None, "bank", "payment_execution", 1, 249900, "2026-03-06T15:00:00.000Z", "unclassified"),

        # 3 Contradictory signals
        ("sub_synth_amb_7", "evt_synth_amb_007", "payment.failed", "BAD_REQUEST_ERROR", "payment_failed", "Card expired and insufficient balance in linked account", "bank", "payment_authorization", 1, 349900, "2026-03-07T15:00:00.000Z", "unclassified"),
        ("sub_synth_amb_7", "evt_synth_amb_008", "payment.failed", "GATEWAY_ERROR", "payment_risk_block", "Risk block triggered due to mandate inactive status", "gateway", "payment_authorization", 2, 349900, "2026-03-08T15:00:00.000Z", "unclassified"),
        ("sub_synth_amb_7", "evt_synth_amb_009", "payment.failed", "BAD_REQUEST_ERROR", "payment_failed", "E-commerce disabled on expired card", "issuer", "payment_authorization", 3, 349900, "2026-03-09T15:00:00.000Z", "unclassified"),
    ]

    inserted_count = 0
    category_counts = {}

    for item in events_data:
        sub_id, evt_id, event_type, err_code, err_reason, err_desc, err_source, err_step, attempt, amount, rx_at, category = item
        
        raw_json = build_raw_payload(event_type, sub_id, evt_id, amount, err_code, err_desc, err_source, err_step, err_reason)
        
        cursor.execute(
            """
            INSERT INTO failure_events (
                subscription_id, external_event_id, event_type, error_code, error_reason,
                error_description, error_source, error_step, attempt_number, raw_payload, received_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (sub_id, evt_id, event_type, err_code, err_reason, err_desc, err_source, err_step, attempt, raw_json, rx_at)
        )
        inserted_count += 1
        category_counts[category] = category_counts.get(category, 0) + 1

    conn.commit()
    print(f"[OK] Seeded {inserted_count} failure_events rows.")

    # 3. MANDATORY EDGE CASE: Test duplicate external_event_id rejection
    print("\n[EDGE CASE CHECK] Testing Duplicate Webhook Delivery Rejection (external_event_id = 'evt_synth_ins_001')...")
    try:
        cursor.execute(
            """
            INSERT INTO failure_events (
                subscription_id, external_event_id, event_type, error_code, error_reason,
                error_description, error_source, error_step, attempt_number, raw_payload, received_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "sub_synth_ins_1", "evt_synth_ins_001", "payment.failed", "BAD_REQUEST_ERROR",
                "payment_failed", "DUPLICATE DELIVERED WEBHOOK ATTEMPT", "bank", "payment_execution",
                1, '{"duplicate": true}', "2026-03-01T10:00:05.000Z"
            )
        )
        conn.commit()
        raise RuntimeError("[ERROR] DB failed to reject duplicate external_event_id!")
    except sqlite3.IntegrityError as e:
        print(f"[OK] Duplicate webhook insertion successfully REJECTED by database constraint!")
        print(f"   Literal SQLite Error Output: {e}")

    # 4. Verify Downstream Tables standard 0-count assertion
    downstream_tables = ["classifications", "decisions", "actions", "case_state", "audit_log"]
    print("\n[VERIFICATION] Confirming zero writes to downstream tables...")
    for tbl in downstream_tables:
        cursor.execute(f"SELECT count(*) FROM {tbl};")
        cnt = cursor.fetchone()[0]
        if cnt != 0:
            raise RuntimeError(f"[ERROR] Found {cnt} rows in downstream table '{tbl}'! Expected 0.")
        print(f"   Table '{tbl}': {cnt} rows [OK]")

    conn.close()

    print("\n" + "=" * 60)
    print("DATASET CATEGORY DISTRIBUTION SUMMARY")
    print("=" * 60)
    for cat, cnt in sorted(category_counts.items()):
        print(f"  - {cat}: {cnt} events")
    print(f"  TOTAL EVENTS: {sum(category_counts.values())} events")
    print("=" * 60)

    return category_counts

if __name__ == "__main__":
    generate_synthetic_data()
