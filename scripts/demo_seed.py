"""
Demo Environment Reset & Seed Script (Phase 10)
=================================================

Idempotent one-command script to prepare the project for live/recorded pitch demos:
1. Re-initializes SQLite database schema (db/init.py).
2. Seeds 40 synthetic failure events across 23 subscriptions (scripts/generate_synthetic.py).
3. Runs the full pipeline (classify -> decide -> execute -> audit) across all failure events (pipeline/process_event.py).
4. Prints a summary of cases by status and outputs TWO demo-ready example subscription IDs (one recovered card_expired case, one escalated risk_block case).
"""

import os
import sqlite3
import sys

# Ensure UTF-8 output encoding on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.init import get_db_connection, init_db
from scripts.generate_synthetic import generate_synthetic_data
from pipeline.process_event import process_failure_event

def run_demo_seed():
    print("=" * 60)
    print("RAZORPAY RECOVERY AGENT — DEMO ENVIRONMENT SEEDING")
    print("=" * 60)

    # 1. Initialize DB Schema & Seed Synthetic Events
    generate_synthetic_data()

    # 2. Process all failure_events through the orchestrator pipeline
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM failure_events ORDER BY received_at ASC, id ASC")
    fe_ids = [row[0] for row in cursor.fetchall()]

    print(f"\n[PIPELINE PROCESSING] Processing {len(fe_ids)} failure events through end-to-end recovery agent...")
    processed_count = 0

    for fe_id in fe_ids:
        process_failure_event(fe_id, conn=conn)
        processed_count += 1

    print(f"[OK] Successfully processed {processed_count} events.")

    # 3. Query Final Database Metrics
    cursor.execute("SELECT status, COUNT(*) as cnt FROM case_state GROUP BY status")
    status_counts = {row[0]: row[1] for row in cursor.fetchall()}

    cursor.execute("SELECT last_category, COUNT(*) as cnt FROM case_state GROUP BY last_category")
    category_counts = {row[0]: row[1] for row in cursor.fetchall()}

    # 4. Find Demo-Ready Example Cases
    # Example A: Recovered card_expired case
    cursor.execute(
        """
        SELECT subscription_id 
        FROM case_state 
        WHERE last_category = 'card_expired' AND status = 'recovered'
        LIMIT 1
        """
    )
    recovered_row = cursor.fetchone()
    demo_recovered_id = recovered_row[0] if recovered_row else "sub_synth_exp_1"

    # Example B: Escalated risk_block case
    cursor.execute(
        """
        SELECT subscription_id 
        FROM case_state 
        WHERE last_category = 'risk_block' AND status = 'escalated'
        LIMIT 1
        """
    )
    escalated_row = cursor.fetchone()
    demo_escalated_id = escalated_row[0] if escalated_row else "sub_synth_rsk_1"

    conn.close()

    # 5. Output Demo Preparation Summary
    print("\n" + "=" * 60)
    print("DEMO ENVIRONMENT READY SUMMARY")
    print("=" * 60)
    print("Status Breakdown:")
    for st, count in sorted(status_counts.items()):
        print(f"  - {st}: {count} cases")

    print("\nCategory Breakdown:")
    for cat, count in sorted(category_counts.items()):
        print(f"  - {cat}: {count} cases")

    print("\n" + "-" * 60)
    print("PITCH DEMO RECOMMENDED CASE EXAMPLES:")
    print(f"  1. RECOVERED Card Expired Case ID: {demo_recovered_id}")
    print(f"     -> View in dashboard: GET /cases/{demo_recovered_id}")
    print(f"  2. ESCALATED Risk Block Case ID:  {demo_escalated_id}")
    print(f"     -> View in dashboard: GET /cases/{demo_escalated_id}")
    print("-" * 60)
    print("Start the backend & frontend server:")
    print("  python -m uvicorn api.main:app --port 8000")
    print("  Open browser to: http://127.0.0.1:8000/")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    run_demo_seed()
