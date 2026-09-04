"""
Single-Event Pipeline Orchestrator (Phase 7)
==============================================

Orchestrates the end-to-end processing sequence for a SINGLE failure_events row:
1. classify_by_rules() -> if unclassified/0.0 -> classify_by_llm() -> classifications table
2. decide_action() -> decisions table
3. execute_action() -> actions table
4. log_audit_entry() x3 -> audit_log table
5. update_case_state() -> case_state table

Layer Separation Rule:
- Calls existing functions in sequence.
- NO inline rules, policy logic, or action templates.
- LLM is strictly fallback-only for unclassified rule outputs.
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone



from db.init import get_db_connection
from classifier.rules import classify_by_rules
from classifier.llm_fallback import classify_by_llm
from engine.policy import decide_action
from engine.case_state import get_or_create_case_state, update_case_state
from executor.actions import execute_action
from audit.logger import log_audit_entry

def process_failure_event(failure_event_id: int, conn: sqlite3.Connection = None) -> dict:
    """
    Executes the end-to-end pipeline sequence for a single failure event.

    Args:
        failure_event_id (int): Primary key ID of row in failure_events table.
        conn (sqlite3.Connection|None): Optional existing SQLite database connection.

    Returns:
        dict: Case summary containing status, case_id, classification, decision, action, and case_state.
    """
    close_conn_on_exit = False
    if conn is None:
        conn = get_db_connection()
        close_conn_on_exit = True

    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Fetch failure event record
        cursor.execute(
            """
            SELECT id, subscription_id, external_event_id, event_type, 
                   error_code, error_reason, error_description, error_source, 
                   error_step, attempt_number
            FROM failure_events
            WHERE id = ?
            """,
            (failure_event_id,)
        )
        fe = cursor.fetchone()
        if not fe:
            raise ValueError(f"Failure event with ID {failure_event_id} not found.")

        fe_dict = dict(fe)

        sub_id = fe_dict["subscription_id"]
        ext_evt_id = fe_dict["external_event_id"]
        attempt_number = fe_dict["attempt_number"]
        event_type = fe_dict["event_type"]

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%f")[:-3] + "Z"

        # 1. Classification (Rule Engine First -> LLM Fallback if Unclassified)
        category, confidence = classify_by_rules(
            error_code=fe_dict["error_code"],
            error_reason=fe_dict["error_reason"],
            error_description=fe_dict["error_description"],
            error_source=fe_dict["error_source"],
            error_step=fe_dict["error_step"]
        )

        method = "rule"
        llm_reasoning = None

        # Fallback to LLM ONLY if rule engine returned unclassified / 0.0 confidence
        if category == "unclassified" and confidence == 0.0:
            category, confidence, llm_reasoning = classify_by_llm(
                error_code=fe_dict["error_code"],
                error_reason=fe_dict["error_reason"],
                error_description=fe_dict["error_description"],
                error_source=fe_dict["error_source"],
                error_step=fe_dict["error_step"],
                attempt_number=attempt_number
            )
            method = "llm"

        cursor.execute(
            """
            INSERT INTO classifications (failure_event_id, category, method, confidence, llm_reasoning, classified_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (failure_event_id, category, method, confidence, llm_reasoning, now_iso)
        )
        classification_id = cursor.lastrowid

        # 2. Policy Engine Decision
        current_case_state = get_or_create_case_state(conn, sub_id)

        cursor.execute("SELECT status FROM subscriptions WHERE id = ?", (sub_id,))
        sub_row = cursor.fetchone()
        sub_status = sub_row[0] if sub_row else "active"

        action_type, playbook_rule_id = decide_action(
            category=category,
            confidence=confidence,
            case_state=current_case_state,
            subscription_status=sub_status,
            attempt_number=attempt_number
        )

        cursor.execute(
            """
            INSERT INTO decisions (classification_id, action_type, playbook_rule_id, decided_at)
            VALUES (?, ?, ?, ?)
            """,
            (classification_id, action_type, playbook_rule_id, now_iso)
        )
        decision_id = cursor.lastrowid

        # 3. Action Execution
        simulated, result, payload_json = execute_action(
            action_type=action_type,
            playbook_rule_id=playbook_rule_id,
            category=category,
            subscription_id=sub_id,
            attempt_number=attempt_number,
            case_status=current_case_state.get("status")
        )

        cursor.execute(
            """
            INSERT INTO actions (decision_id, action_type, simulated, payload, result, executed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (decision_id, action_type, simulated, payload_json, result, now_iso)
        )
        action_id = cursor.lastrowid

        # 4. Audit Log Entries (x3)
        if method == "llm":
            summary_class = (
                f"Classified failure event '{ext_evt_id}' for subscription '{sub_id}' "
                f"as category '{category}' via LLM engine with confidence {confidence:.2f}. "
                f"Reasoning: {llm_reasoning}"
            )
            class_actor = "llm"
        else:
            summary_class = (
                f"Classified failure event '{ext_evt_id}' for subscription '{sub_id}' "
                f"as category '{category}' via rule engine with confidence {confidence:.2f}."
            )
            class_actor = "system"

        log_audit_entry(conn, sub_id, summary_class, actor=class_actor)

        summary_decision = (
            f"Policy engine evaluated subscription '{sub_id}': "
            f"decided action '{action_type}' (Playbook Rule: '{playbook_rule_id}')."
        )
        log_audit_entry(conn, sub_id, summary_decision, actor="system")

        summary_action = (
            f"Action executed: '{action_type}' (simulated) for subscription '{sub_id}', "
            f"result: {result}."
        )
        log_audit_entry(conn, sub_id, summary_action, actor="system")

        # 5. Case State Update
        updated_case_state = update_case_state(
            conn=conn,
            subscription_id=sub_id,
            action_type=action_type,
            category=category,
            subscription_status=sub_status
        )

        conn.commit()

        parsed_payload = json.loads(payload_json) if isinstance(payload_json, str) else payload_json

        return {
            "status": "processed",
            "case_id": sub_id,
            "classification": {
                "id": classification_id,
                "failure_event_id": failure_event_id,
                "category": category,
                "method": method,
                "confidence": confidence,
                "llm_reasoning": llm_reasoning,
                "classified_at": now_iso
            },
            "decision": {
                "id": decision_id,
                "classification_id": classification_id,
                "action_type": action_type,
                "playbook_rule_id": playbook_rule_id,
                "decided_at": now_iso
            },
            "action": {
                "id": action_id,
                "decision_id": decision_id,
                "action_type": action_type,
                "simulated": bool(simulated),
                "result": result,
                "payload": parsed_payload,
                "executed_at": now_iso
            },
            "case_state": updated_case_state
        }
    finally:
        if close_conn_on_exit:
            conn.close()
