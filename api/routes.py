"""
API Routes Implementation (Phase 5)
===================================

Exposes REST API surface for:
1. POST /simulate/event - Event simulation & orchestrator triggering
2. GET /cases - Filtered list of recovery cases
3. GET /cases/{id} - Full audit trail for a specific subscription case
4. GET /metrics - Recovery engine operational metrics
5. POST /cases/{id}/human-review - Append human audit note and review case
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from db.init import get_db_connection
from pipeline.process_event import process_failure_event
from audit.logger import log_audit_entry
from classifier.rules import VALID_CATEGORIES

router = APIRouter()


# -----------------------------------------------------------------------------
# Request Schemas
# -----------------------------------------------------------------------------

class SimulateEventRequest(BaseModel):
    subscription_id: str = Field(..., description="Target subscription ID")
    event_type: str = Field("payment.failed", description="Razorpay event type")
    error_code: Optional[str] = Field(None, description="Razorpay error code")
    error_reason: Optional[str] = Field(None, description="Razorpay error reason")
    error_description: Optional[str] = Field(None, description="Razorpay error description")
    error_source: Optional[str] = Field(None, description="Razorpay error source")
    error_step: Optional[str] = Field(None, description="Razorpay error step")
    external_event_id: Optional[str] = Field(None, description="Optional external event ID (generated if omitted)")


class HumanReviewRequest(BaseModel):
    decision: str = Field(..., description="Human decision: 'approve' or 'override'")
    note: str = Field("", description="Narrative review note or justification")


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------

@router.post("/simulate/event")
def simulate_event(req: SimulateEventRequest):
    """
    Simulates a payment failure event by inserting a failure_events record 
    and running the single-event pipeline orchestrator.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%f")[:-3] + "Z"

        # 1. Ensure minimal subscription record exists
        cursor.execute("SELECT id FROM subscriptions WHERE id = ?", (req.subscription_id,))
        if not cursor.fetchone():
            cursor.execute(
                """
                INSERT INTO subscriptions (id, customer_id, plan_amount, currency, status, created_at)
                VALUES (?, ?, 1000, 'INR', 'active', ?)
                """,
                (req.subscription_id, f"cust_sim_{req.subscription_id}", now_iso)
            )

        # 2. Determine external_event_id
        ext_evt_id = req.external_event_id or f"evt_sim_{uuid.uuid4().hex}"

        # 3. Calculate attempt number
        cursor.execute(
            "SELECT COUNT(*) FROM failure_events WHERE subscription_id = ?",
            (req.subscription_id,)
        )
        attempt_number = cursor.fetchone()[0] + 1

        raw_payload = json.dumps(req.model_dump())

        # 4. Insert failure_events record with idempotency handling
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
                    req.subscription_id, ext_evt_id, req.event_type,
                    req.error_code, req.error_reason, req.error_description,
                    req.error_source, req.error_step, attempt_number,
                    raw_payload, now_iso
                )
            )
            failure_event_id = cursor.lastrowid
            conn.commit()
        except sqlite3.IntegrityError as e:
            err_msg = str(e)
            if "external_event_id" in err_msg or "UNIQUE" in err_msg.upper():
                raise HTTPException(
                    status_code=409,
                    detail=f"Event with external_event_id '{ext_evt_id}' already processed (duplicate event)."
                )
            raise HTTPException(status_code=500, detail=f"Database integrity error: {err_msg}")

        # 5. Process event end-to-end via orchestrator
        summary = process_failure_event(failure_event_id, conn=conn)

        return {
            "status": "processed",
            "case_id": req.subscription_id,
            "classification": summary["classification"],
            "decision": summary["decision"],
            "action": summary["action"]
        }

    finally:
        conn.close()


@router.get("/cases")
def get_cases(
    status: Optional[str] = Query(None, description="Filter by case state status"),
    category: Optional[str] = Query(None, description="Filter by last failure category")
):
    """
    Returns array of recovery cases matching optional status and category filters.
    """
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    try:
        query = """
            SELECT 
                cs.subscription_id, 
                cs.status, 
                cs.last_category, 
                cs.contact_count, 
                cs.last_updated
            FROM case_state cs
            JOIN subscriptions s ON cs.subscription_id = s.id
            WHERE 1=1
        """
        params = []
        if status:
            query += " AND cs.status = ?"
            params.append(status)
        if category:
            query += " AND cs.last_category = ?"
            params.append(category)

        query += " ORDER BY cs.last_updated DESC"

        cursor = conn.cursor()
        rows = cursor.execute(query, params).fetchall()

        return [dict(row) for row in rows]
    finally:
        conn.close()


@router.get("/cases/{id}")
def get_case_detail(id: str):
    """
    Returns full chronological audit trail for a subscription case.
    """
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()

        # 1. Fetch Subscription
        sub_row = cursor.execute(
            "SELECT id, customer_id, plan_amount, currency, status, created_at FROM subscriptions WHERE id = ?",
            (id,)
        ).fetchone()
        if not sub_row:
            raise HTTPException(status_code=404, detail=f"Case / Subscription '{id}' not found.")

        # 2. Fetch Case State
        cs_row = cursor.execute(
            "SELECT subscription_id, contact_count, status, last_category, last_updated FROM case_state WHERE subscription_id = ?",
            (id,)
        ).fetchone()

        # 3. Fetch Failure Events
        fe_rows = cursor.execute(
            """
            SELECT id, subscription_id, external_event_id, event_type, 
                   error_code, error_reason, error_description, error_source, 
                   error_step, attempt_number, raw_payload, received_at 
            FROM failure_events 
            WHERE subscription_id = ? 
            ORDER BY received_at ASC, id ASC
            """,
            (id,)
        ).fetchall()

        # 4. Fetch Classifications
        cl_rows = cursor.execute(
            """
            SELECT c.id, c.failure_event_id, c.category, c.method, c.confidence, c.llm_reasoning, c.classified_at 
            FROM classifications c 
            JOIN failure_events fe ON c.failure_event_id = fe.id 
            WHERE fe.subscription_id = ? 
            ORDER BY c.classified_at ASC, c.id ASC
            """,
            (id,)
        ).fetchall()

        # 5. Fetch Decisions
        dec_rows = cursor.execute(
            """
            SELECT d.id, d.classification_id, d.action_type, d.playbook_rule_id, d.decided_at 
            FROM decisions d 
            JOIN classifications c ON d.classification_id = c.id 
            JOIN failure_events fe ON c.failure_event_id = fe.id 
            WHERE fe.subscription_id = ? 
            ORDER BY d.decided_at ASC, d.id ASC
            """,
            (id,)
        ).fetchall()

        # 6. Fetch Actions
        act_rows = cursor.execute(
            """
            SELECT a.id, a.decision_id, a.action_type, a.simulated, a.payload, a.result, a.executed_at 
            FROM actions a 
            JOIN decisions d ON a.decision_id = d.id 
            JOIN classifications c ON d.classification_id = c.id 
            JOIN failure_events fe ON c.failure_event_id = fe.id 
            WHERE fe.subscription_id = ? 
            ORDER BY a.executed_at ASC, a.id ASC
            """,
            (id,)
        ).fetchall()

        parsed_actions = []
        for act in act_rows:
            act_dict = dict(act)
            if isinstance(act_dict["payload"], str):
                try:
                    act_dict["payload"] = json.loads(act_dict["payload"])
                except Exception:
                    pass
            act_dict["simulated"] = bool(act_dict["simulated"])
            parsed_actions.append(act_dict)

        # 7. Fetch Audit Log
        audit_rows = cursor.execute(
            """
            SELECT id, subscription_id, event_summary, actor, timestamp 
            FROM audit_log 
            WHERE subscription_id = ? 
            ORDER BY timestamp ASC, id ASC
            """,
            (id,)
        ).fetchall()

        return {
            "subscription": dict(sub_row),
            "case_state": dict(cs_row) if cs_row else None,
            "failure_events": [dict(r) for r in fe_rows],
            "classifications": [dict(r) for r in cl_rows],
            "decisions": [dict(r) for r in dec_rows],
            "actions": parsed_actions,
            "audit_log": [dict(r) for r in audit_rows]
        }
    finally:
        conn.close()


@router.get("/metrics")
def get_metrics():
    """
    Computes system operational metrics from the current database state.
    """
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()

        # 1. Recovery rate by category
        cursor.execute(
            """
            SELECT 
                last_category, 
                COUNT(*) as total, 
                SUM(CASE WHEN status = 'recovered' THEN 1 ELSE 0 END) as recovered
            FROM case_state 
            WHERE last_category IS NOT NULL 
            GROUP BY last_category
            """
        )
        cat_stats = {row["last_category"]: row for row in cursor.fetchall()}

        recovery_rate_by_category = {}
        for cat in sorted(VALID_CATEGORIES):
            if cat in cat_stats:
                tot = cat_stats[cat]["total"]
                rec = cat_stats[cat]["recovered"]
                recovery_rate_by_category[cat] = round(rec / tot, 4) if tot > 0 else 0.0
            else:
                recovery_rate_by_category[cat] = 0.0

        # 2. Escalation rate
        cursor.execute(
            """
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'escalated' THEN 1 ELSE 0 END) as escalated
            FROM case_state
            """
        )
        esc_row = cursor.fetchone()
        total_cases = esc_row["total"] if esc_row else 0
        escalated_cases = esc_row["escalated"] if esc_row else 0
        escalation_rate = round(escalated_cases / total_cases, 4) if total_cases > 0 else 0.0

        # 3. Contacts avoided (cases with contact_count=0 that are NOT open)
        cursor.execute(
            """
            SELECT COUNT(*) 
            FROM case_state 
            WHERE status IN ('recovered', 'escalated', 'stopped') AND contact_count = 0
            """
        )
        contacts_avoided = cursor.fetchone()[0]

        # 4. Avg contacts per resolved case (status = 'recovered')
        cursor.execute(
            """
            SELECT AVG(contact_count) 
            FROM case_state 
            WHERE status = 'recovered'
            """
        )
        avg_contacts_row = cursor.fetchone()[0]
        avg_contacts_per_resolved_case = round(avg_contacts_row, 2) if avg_contacts_row is not None else 0.0

        # 5. False decision count
        # Hardcoded to None (JSON null): requires human-labeled gold standard dataset not yet implemented.
        false_decision_count = None

        return {
            "recovery_rate_by_category": recovery_rate_by_category,
            "escalation_rate": escalation_rate,
            "contacts_avoided": contacts_avoided,
            "avg_contacts_per_resolved_case": avg_contacts_per_resolved_case,
            "false_decision_count": false_decision_count
        }
    finally:
        conn.close()


@router.post("/cases/{id}/human-review")
def human_review_case(id: str, req: HumanReviewRequest):
    """
    Appends a human review audit note to a case and updates case state status if specified.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Verify case exists
        cursor.execute("SELECT id FROM subscriptions WHERE id = ?", (id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"Case / Subscription '{id}' not found.")

        # Log audit entry with actor='human'
        decision_clean = req.decision.strip().lower()
        audit_narrative = f"Human review ({req.decision}): {req.note}" if req.note else f"Human review ({req.decision})"
        log_audit_entry(conn, id, audit_narrative, actor="human")

        # Update case_state if override specifies explicit status or leave unchanged
        cursor.execute("SELECT status, last_category, contact_count FROM case_state WHERE subscription_id = ?", (id,))
        cs_row = cursor.fetchone()

        if cs_row:
            current_status = cs_row[0]
            new_status = current_status

            if decision_clean == "override" and req.note:
                note_lower = req.note.lower()
                if "recovered" in note_lower:
                    new_status = "recovered"
                elif "stopped" in note_lower:
                    new_status = "stopped"
                elif "escalated" in note_lower:
                    new_status = "escalated"
                elif "open" in note_lower:
                    new_status = "open"

            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%f")[:-3] + "Z"
            cursor.execute(
                """
                UPDATE case_state
                SET status = ?, last_updated = ?
                WHERE subscription_id = ?
                """,
                (new_status, now_iso, id)
            )
            conn.commit()

        return {"status": "updated"}
    finally:
        conn.close()
