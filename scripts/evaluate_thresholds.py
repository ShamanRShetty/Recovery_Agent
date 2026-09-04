"""
Offline Confidence Threshold Evaluation Script (Phase 7)
========================================================

Evaluates LLM classification performance across candidate confidence thresholds
(0.60, 0.75, 0.90) against the 9 deliberately ambiguous synthetic events from Phase 1.

Prints a structured analysis table comparing auto-actionable vs escalated case distributions.
"""

import os
import sqlite3
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.init import get_db_connection
from classifier.llm_fallback import classify_by_llm

AMBIGUOUS_EVENT_IDS = [
    "evt_synth_amb_001",
    "evt_synth_amb_002",
    "evt_synth_amb_003",
    "evt_synth_amb_004",
    "evt_synth_amb_005",
    "evt_synth_amb_006",
    "evt_synth_amb_007",
    "evt_synth_amb_008",
    "evt_synth_amb_009",
]

THRESHOLDS = [0.60, 0.75, 0.90]

def evaluate_thresholds():
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=" * 100)
    print("PHASE 7 OFFLINE CONFIDENCE THRESHOLD EVALUATION REPORT")
    print("=" * 100)

    results = []

    # Fetch 9 ambiguous events
    placeholders = ",".join(["?"] * len(AMBIGUOUS_EVENT_IDS))
    query = f"""
        SELECT id, subscription_id, external_event_id, error_code, error_reason, error_description, attempt_number
        FROM failure_events
        WHERE external_event_id IN ({placeholders})
        ORDER BY id ASC
    """
    rows = cursor.execute(query, AMBIGUOUS_EVENT_IDS).fetchall()

    if not rows:
        print("ERROR: Ambiguous synthetic events not found in database.")
        return

    print(f"\n[INFO] Evaluating {len(rows)} ambiguous synthetic events via classify_by_llm():\n")

    llm_outputs = []
    for row in rows:
        evt_id = row["external_event_id"]
        sub_id = row["subscription_id"]
        code = row["error_code"]
        reason = row["error_reason"]
        desc = row["error_description"]
        attempt = row["attempt_number"]

        cat, conf, reasoning = classify_by_llm(
            error_code=code,
            error_reason=reason,
            error_description=desc,
            attempt_number=attempt
        )

        llm_outputs.append({
            "external_event_id": evt_id,
            "subscription_id": sub_id,
            "error_description": desc or "(none)",
            "category": cat,
            "confidence": conf,
            "reasoning": reasoning
        })

    # Print LLM Outputs
    print(f"{'EVENT ID':<20} | {'CATEGORY':<20} | {'CONF':<6} | {'REASONING'}")
    print("-" * 100)
    for item in llm_outputs:
        print(f"{item['external_event_id']:<20} | {item['category']:<20} | {item['confidence']:<6.2f} | {item['reasoning']}")

    # Threshold Comparison Summary
    print("\n" + "=" * 100)
    print("THRESHOLD IMPACT COMPARISON SUMMARY (0.60 vs 0.75 vs 0.90)")
    print("=" * 100)

    for thresh in THRESHOLDS:
        auto_acted = 0
        escalated = 0
        print(f"\n--- Candidate Confidence Threshold = {thresh:.2f} ---")
        print(f"{'EVENT ID':<20} | {'CATEGORY':<20} | {'CONF':<6} | {'DECISION':<12} | {'MANUAL CORRECTNESS FLAG'}")
        print("-" * 100)

        for item in llm_outputs:
            is_auto = item["confidence"] >= thresh and item["category"] != "unclassified"
            if is_auto:
                auto_acted += 1
                dec_str = "AUTO_ACTION"
                flag_str = "[ ] True / False (Needs Human Review)"
            else:
                escalated += 1
                dec_str = "ESCALATED"
                flag_str = "[N/A - Escalated]"

            print(f"{item['external_event_id']:<20} | {item['category']:<20} | {item['confidence']:<6.2f} | {dec_str:<12} | {flag_str}")

        print(f"\nSummary for Threshold {thresh:.2f}: Auto-Acted = {auto_acted} / {len(llm_outputs)}, Escalated = {escalated} / {len(llm_outputs)}")

    conn.close()

if __name__ == "__main__":
    evaluate_thresholds()
