"""
Append-Only Audit Logger (Phase 4)
==================================

Manages database writes for the audit_log table in SQLite.
Records human-readable, append-only narrative entries for every classification,
policy decision, and action execution step.
"""

import sqlite3
from datetime import datetime, timezone

VALID_ACTORS = {"system", "llm", "human"}

def log_audit_entry(conn, subscription_id, event_summary, actor="system"):
    """
    Inserts a single append-only audit log record.

    Args:
        conn (sqlite3.Connection): Database connection
        subscription_id (str): Target subscription ID
        event_summary (str): Plain English narrative summary of event step
        actor (str): Must be one of ('system', 'llm', 'human')

    Returns:
        int: ID of inserted audit_log row
    """
    if actor not in VALID_ACTORS:
        raise ValueError(f"Invalid actor '{actor}'. Must be one of {VALID_ACTORS}")

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%f")[:-3] + "Z"
    
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO audit_log (subscription_id, event_summary, actor, timestamp)
        VALUES (?, ?, ?, ?)
        """,
        (subscription_id, event_summary, actor, now_iso)
    )
    return cursor.lastrowid
