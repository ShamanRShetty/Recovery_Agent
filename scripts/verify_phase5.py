"""
Verification Script for Phase 5 (API Backend & Single-Event Pipeline Orchestrator)
================================================------------------------------------

Executes all 6 mandatory verification steps specified in the Phase 5 requirements:
1. Confirm API boot status
2. POST /simulate/event (card_expired) & query DB rows across failure_events, classifications, decisions, actions, audit_log, case_state
3. POST /simulate/event (duplicate external_event_id) -> 409 Conflict
4. GET /cases and GET /cases/{id} for new subscription
5. GET /metrics -> verify false_decision_count is null
6. POST /cases/{id}/human-review on an escalated synthetic case -> show audit log entry
"""

import json
import sqlite3
import sys
import urllib.error
import urllib.request

BASE_URL = "http://127.0.0.1:8000"
DB_PATH = "db/recovery_agent.db"

def make_request(method, endpoint, payload=None):
    url = f"{BASE_URL}{endpoint}"
    data = json.dumps(payload).encode("utf-8") if payload else None
    headers = {"Content-Type": "application/json"} if payload else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
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
    print("PHASE 5 VERIFICATION RUNNER")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # STEP 1: Confirm API status
    # -------------------------------------------------------------------------
    print("\n--- STEP 1: API Boot & Root Endpoint Check ---")
    status, _ = make_request("GET", "/")
    print(f"HTTP Status: {status} (root serves HTML dashboard — expected 200)")

    # -------------------------------------------------------------------------
    # STEP 2: POST /simulate/event with new subscription (card_expired)
    # -------------------------------------------------------------------------
    print("\n--- STEP 2: POST /simulate/event (card_expired payload) ---")
    sub_id = "sub_phase5_test_expired_001"
    sim_payload = {
        "subscription_id": sub_id,
        "event_type": "payment.failed",
        "error_code": "BAD_REQUEST_ERROR",
        "error_reason": "card_expired",
        "error_description": "Card has expired. Please try another payment method.",
        "external_event_id": "evt_phase5_forced_unique_12345"
    }
    status, body = make_request("POST", "/simulate/event", sim_payload)
    print(f"HTTP Status: {status}")
    print(f"Response: {json.dumps(body, indent=2)}")

    # Query DB rows across all 6 tables for this subscription
    print("\n--- Database Rows Created for Step 2 ---")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("\n1. failure_events:")
    row = cursor.execute("SELECT * FROM failure_events WHERE subscription_id = ?", (sub_id,)).fetchone()
    print(json.dumps(dict(row), indent=2) if row else "None")

    print("\n2. classifications:")
    row = cursor.execute(
        "SELECT c.* FROM classifications c JOIN failure_events fe ON c.failure_event_id = fe.id WHERE fe.subscription_id = ?",
        (sub_id,)
    ).fetchone()
    print(json.dumps(dict(row), indent=2) if row else "None")

    print("\n3. decisions:")
    row = cursor.execute(
        "SELECT d.* FROM decisions d JOIN classifications c ON d.classification_id = c.id JOIN failure_events fe ON c.failure_event_id = fe.id WHERE fe.subscription_id = ?",
        (sub_id,)
    ).fetchone()
    print(json.dumps(dict(row), indent=2) if row else "None")

    print("\n4. actions:")
    row = cursor.execute(
        "SELECT a.* FROM actions a JOIN decisions d ON a.decision_id = d.id JOIN classifications c ON d.classification_id = c.id JOIN failure_events fe ON c.failure_event_id = fe.id WHERE fe.subscription_id = ?",
        (sub_id,)
    ).fetchone()
    if row:
        act_d = dict(row)
        if isinstance(act_d.get("payload"), str):
            act_d["payload"] = json.loads(act_d["payload"])
        print(json.dumps(act_d, indent=2))

    print("\n5. audit_log entries:")
    rows = cursor.execute("SELECT * FROM audit_log WHERE subscription_id = ? ORDER BY id ASC", (sub_id,)).fetchall()
    print(json.dumps([dict(r) for r in rows], indent=2))

    print("\n6. case_state row:")
    row = cursor.execute("SELECT * FROM case_state WHERE subscription_id = ?", (sub_id,)).fetchone()
    print(json.dumps(dict(row), indent=2) if row else "None")

    # -------------------------------------------------------------------------
    # STEP 3: Duplicate external_event_id -> 409 Conflict
    # -------------------------------------------------------------------------
    print("\n--- STEP 3: POST /simulate/event with duplicate external_event_id ---")
    status, body = make_request("POST", "/simulate/event", sim_payload)
    print(f"HTTP Status: {status} (Expected 409)")
    print(f"Response: {json.dumps(body, indent=2)}")

    # -------------------------------------------------------------------------
    # STEP 4: GET /cases and GET /cases/{id}
    # -------------------------------------------------------------------------
    print("\n--- STEP 4A: GET /cases (filtered by category=card_expired) ---")
    status, body = make_request("GET", f"/cases?category=card_expired")
    print(f"HTTP Status: {status}")
    print(f"Response: {json.dumps(body, indent=2)}")

    print(f"\n--- STEP 4B: GET /cases/{sub_id} ---")
    status, body = make_request("GET", f"/cases/{sub_id}")
    print(f"HTTP Status: {status}")
    print(f"Response: {json.dumps(body, indent=2)}")

    # -------------------------------------------------------------------------
    # STEP 5: GET /metrics
    # -------------------------------------------------------------------------
    print("\n--- STEP 5: GET /metrics ---")
    status, body = make_request("GET", "/metrics")
    print(f"HTTP Status: {status}")
    print(f"Response: {json.dumps(body, indent=2)}")

    # -------------------------------------------------------------------------
    # STEP 6: POST /cases/{id}/human-review on an escalated case (e.g. sub_synth_rsk_1)
    # -------------------------------------------------------------------------
    print("\n--- STEP 6: POST /cases/sub_synth_rsk_1/human-review (escalated synthetic case) ---")
    review_payload = {
        "decision": "approve",
        "note": "Approved risk escalation for manual high-value customer verification by compliance agent."
    }
    status, body = make_request("POST", "/cases/sub_synth_rsk_1/human-review", review_payload)
    print(f"HTTP Status: {status}")
    print(f"Response: {json.dumps(body, indent=2)}")

    print("\n--- Resulting Audit Log Entries for sub_synth_rsk_1 ---")
    rows = cursor.execute("SELECT * FROM audit_log WHERE subscription_id = 'sub_synth_rsk_1' ORDER BY id ASC", ()).fetchall()
    print(json.dumps([dict(r) for r in rows], indent=2))


    conn.close()

if __name__ == "__main__":
    run_verification()
