"""
Razorpay Real Webhook Handler (Phase 6)
========================================

Ingests real Razorpay webhook events:
1. Captures unparsed raw request body before JSON parsing.
2. Validates X-Razorpay-Signature using HMAC-SHA256 constant-time check.
3. Translates nested payload into flat failure_events fields.
4. Enforces idempotency via X-Razorpay-Event-Id UNIQUE constraint (returns 200 duplicate_ignored).
5. Triggers pipeline orchestrator (pipeline/process_event.py) for new events.
"""

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from db.init import get_db_connection
from api.webhook_security import verify_razorpay_signature
from api.webhook_translator import translate_razorpay_payload
from pipeline.process_event import process_failure_event

# Automatically load .env file if present in project root
env_file = Path(__file__).resolve().parent.parent / ".env"
if env_file.exists():
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip().strip("'\""))

logger = logging.getLogger("razorpay_webhooks")
router = APIRouter()

@router.post("/webhooks/razorpay")
async def handle_razorpay_webhook(request: Request):
    """
    Ingests and signature-verifies incoming Razorpay webhooks.
    """
    # 1. Read unparsed raw request body BEFORE any JSON processing
    raw_body = await request.body()

    signature_header = request.headers.get("X-Razorpay-Signature") or request.headers.get("x-razorpay-signature")
    event_id_header = request.headers.get("X-Razorpay-Event-Id") or request.headers.get("x-razorpay-event-id")
    webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "").strip()

    # 2. Signature verification & diagnostic console logging
    if not verify_razorpay_signature(raw_body, signature_header, webhook_secret):
        if not webhook_secret:
            logger.warning(
                "Rejected Razorpay webhook: RAZORPAY_WEBHOOK_SECRET environment variable is empty or not set! "
                "Please set RAZORPAY_WEBHOOK_SECRET in your environment or in a .env file."
            )
            print("\n[WEBHOOK REJECTION DIAGNOSTIC] RAZORPAY_WEBHOOK_SECRET is empty/not set on the server!")
            print("Action needed: Create a .env file in project root with RAZORPAY_WEBHOOK_SECRET=your_secret_here\n")
        elif not signature_header:
            logger.warning("Rejected Razorpay webhook: Missing X-Razorpay-Signature header in request.")
            print("\n[WEBHOOK REJECTION DIAGNOSTIC] Incoming request did not contain X-Razorpay-Signature header.\n")
        else:
            logger.warning("Rejected Razorpay webhook: HMAC signature mismatch.")
            print("\n[WEBHOOK REJECTION DIAGNOSTIC] Signature mismatch!")
            print("Action needed: Ensure RAZORPAY_WEBHOOK_SECRET matches the Secret set in Razorpay Dashboard > Settings > Webhooks.\n")

        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"status": "rejected", "detail": "Invalid webhook signature"}
        )

    # 3. Parse JSON body
    try:
        payload_json = json.loads(raw_body.decode("utf-8"))
    except Exception as e:
        logger.error(f"Failed to parse webhook JSON body: {e}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"status": "rejected", "detail": "Malformed JSON payload"}
        )

    # 4. Translate Razorpay payload to flat failure_events structure
    translated = translate_razorpay_payload(payload_json)
    sub_id = translated["subscription_id"]

    # 5. Determine external_event_id from X-Razorpay-Event-Id header
    ext_evt_id = event_id_header or f"evt_rzp_{uuid.uuid4().hex}"

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%f")[:-3] + "Z"

        # 6. Ensure minimal subscription record exists
        cursor.execute("SELECT id FROM subscriptions WHERE id = ?", (sub_id,))
        if not cursor.fetchone():
            cursor.execute(
                """
                INSERT INTO subscriptions (id, customer_id, plan_amount, currency, status, created_at)
                VALUES (?, ?, 1000, 'INR', 'active', ?)
                """,
                (sub_id, f"cust_rzp_{sub_id}", now_iso)
            )

        # 7. Calculate attempt number
        cursor.execute(
            "SELECT COUNT(*) FROM failure_events WHERE subscription_id = ?",
            (sub_id,)
        )
        attempt_number = cursor.fetchone()[0] + 1

        # 8. Attempt insert into failure_events table (Idempotency enforcement)
        try:
            cursor.execute(
                """
                INSERT INTO failure_events (
                    subscription_id, external_event_id, event_type, 
                    error_code, error_reason, error_description, 
                    error_source, error_step, attempt_number, 
                    raw_payload, received_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sub_id, ext_evt_id, translated["event_type"],
                    translated["error_code"], translated["error_reason"],
                    translated["error_description"], translated["error_source"],
                    translated["error_step"], attempt_number,
                    translated["raw_payload"], now_iso
                )
            )
            failure_event_id = cursor.lastrowid
            conn.commit()
        except sqlite3.IntegrityError as e:
            err_msg = str(e)
            if "external_event_id" in err_msg or "UNIQUE" in err_msg.upper():
                logger.info(f"Duplicate Razorpay event '{ext_evt_id}' received and ignored.")
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content={"status": "duplicate_ignored"}
                )
            raise

        # 9. Trigger single-event pipeline orchestrator
        process_failure_event(failure_event_id, conn=conn)

        print(f"\n[WEBHOOK SUCCESS] Successfully processed Razorpay event '{ext_evt_id}' for subscription '{sub_id}'!\n")

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "processed", "case_id": sub_id}
        )

    finally:
        conn.close()
