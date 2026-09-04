"""
Case State Persistence Manager (Phase 3)
========================================

Manages database reads and writes for the case_state table in SQLite.
Kept strictly separate from pure policy decision engine (engine/policy.py).
"""

import sqlite3
from datetime import datetime, timezone

def get_or_create_case_state(conn, subscription_id):
    """
    Fetches the existing case_state record for a subscription_id,
    or creates an initial record with contact_count=0 and status='open'.

    Returns:
        dict: case_state record as a dictionary
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT subscription_id, contact_count, status, last_category, last_updated FROM case_state WHERE subscription_id = ?",
        (subscription_id,)
    )
    row = cursor.fetchone()
    
    if row:
        if isinstance(row, sqlite3.Row):
            return dict(row)
        return {
            "subscription_id": row[0],
            "contact_count": row[1],
            "status": row[2],
            "last_category": row[3],
            "last_updated": row[4]
        }
    
    # Initialize initial state record
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%f")[:-3] + "Z"
    cursor.execute(
        """
        INSERT INTO case_state (subscription_id, contact_count, status, last_category, last_updated)
        VALUES (?, 0, 'open', NULL, ?)
        """,
        (subscription_id, now_iso)
    )
    conn.commit()
    
    return {
        "subscription_id": subscription_id,
        "contact_count": 0,
        "status": "open",
        "last_category": None,
        "last_updated": now_iso
    }

def update_case_state(conn, subscription_id, action_type, category, subscription_status=None):
    """
    Updates the case_state row after a decision is made.
    
    State transition rules:
    - action_type == 'send_nudge': increment contact_count by 1
    - action_type == 'escalate': set status = 'escalated'
    - action_type == 'stop' & subscription_status == 'active': set status = 'recovered'
    - action_type == 'stop' & subscription_status != 'active': set status = 'stopped'
    - updates last_category and last_updated timestamp
    """
    current_state = get_or_create_case_state(conn, subscription_id)
    
    new_contact_count = current_state["contact_count"]
    new_status = current_state["status"]
    
    if action_type == "send_nudge":
        # 2 must match MAX_CONTACTS in config.py and the CHECK constraint in db/schema.sql
        new_contact_count = min(current_state["contact_count"] + 1, 2)
    elif action_type == "escalate":
        new_status = "escalated"
    elif action_type == "stop":
        if subscription_status == "active":
            new_status = "recovered"
        else:
            new_status = "stopped"

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%f")[:-3] + "Z"
    
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE case_state
        SET contact_count = ?, status = ?, last_category = ?, last_updated = ?
        WHERE subscription_id = ?
        """,
        (new_contact_count, new_status, category, now_iso, subscription_id)
    )
    conn.commit()
    
    return {
        "subscription_id": subscription_id,
        "contact_count": new_contact_count,
        "status": new_status,
        "last_category": category,
        "last_updated": now_iso
    }
