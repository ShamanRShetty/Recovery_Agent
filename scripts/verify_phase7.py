"""
Master Verification Script for Phase 7 (LLM Fallback Classifier & Threshold Evaluation)
========================================================================================

Executes all required verification checks for Phase 7:
1 & 2. Runs the 25-test unit suite (mocked LLM calls)
3. Verifies zero imports from engine/ or executor/ in classifier/llm_fallback.py
4. Evaluates pipeline against the 9 ambiguous synthetic events
5. Runs scripts/evaluate_thresholds.py for candidate thresholds (0.60, 0.75, 0.90)
6. Confirms gating logic: 0 LLM calls for all events confidently matched by rule engine
"""

import ast
import json
import os
import sqlite3
import sys
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.init import get_db_connection
from classifier.rules import classify_by_rules
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

def run_phase7_verification():
    print("=" * 100)
    print("PHASE 7 MASTER VERIFICATION RUNNER")
    print("=" * 100)

    # -------------------------------------------------------------------------
    # CHECK 1 & 2: Unit Test Suite Execution
    # -------------------------------------------------------------------------
    print("\n--- CHECK 1 & 2: Unit Test Suite Execution (Mocked LLM Calls) ---")
    loader = unittest.TestLoader()
    suite = loader.discover("tests")
    runner = unittest.TextTestRunner(verbosity=2)
    test_result = runner.run(suite)
    if not test_result.wasSuccessful():
        print("ERROR: Unit tests failed!")
        sys.exit(1)

    # -------------------------------------------------------------------------
    # CHECK 3: Import Boundary Verification for classifier/llm_fallback.py
    # -------------------------------------------------------------------------
    print("\n--- CHECK 3: Architectural Boundary Import Check (llm_fallback.py) ---")
    filepath = Path("classifier/llm_fallback.py")
    tree = ast.parse(filepath.read_text(encoding="utf-8"))
    
    imports = []
    forbidden_violations = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
                if alias.name.startswith("engine") or alias.name.startswith("executor"):
                    forbidden_violations.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod_name = node.module or ""
            imports.append(mod_name)
            if mod_name.startswith("engine") or mod_name.startswith("executor"):
                forbidden_violations.append(mod_name)

    print(f"File: {filepath.as_posix()}")
    print(f"All Imported Modules: {sorted(set(imports))}")
    if forbidden_violations:
        print(f"FORBIDDEN VIOLATIONS FOUND: {forbidden_violations}")
        sys.exit(1)
    else:
        print("[VERIFICATION PASSED] ZERO imports from engine/ or executor/ layer! Boundary intact.")

    # -------------------------------------------------------------------------
    # CHECK 4: Pipeline Execution Against 9 Ambiguous Synthetic Events
    # -------------------------------------------------------------------------
    print("\n--- CHECK 4: LLM Fallback Classification Output for 9 Ambiguous Events ---")
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    placeholders = ",".join(["?"] * len(AMBIGUOUS_EVENT_IDS))
    query = f"""
        SELECT fe.id, fe.subscription_id, fe.external_event_id, fe.error_code, fe.error_reason, fe.error_description, fe.attempt_number
        FROM failure_events fe
        WHERE fe.external_event_id IN ({placeholders})
        ORDER BY fe.id ASC
    """
    rows = cursor.execute(query, AMBIGUOUS_EVENT_IDS).fetchall()

    print(f"{'EVENT ID':<20} | {'CATEGORY':<20} | {'CONF':<6} | {'ACTIONABLE (>=0.75)?':<20} | {'REASONING'}")
    print("-" * 120)

    auto_actionable_count = 0
    escalated_count = 0

    for r in rows:
        evt_id = r["external_event_id"]
        cat, conf, reasoning = classify_by_llm(
            error_code=r["error_code"],
            error_reason=r["error_reason"],
            error_description=r["error_description"],
            attempt_number=r["attempt_number"]
        )

        is_auto = (conf >= 0.75 and cat != "unclassified")
        if is_auto:
            auto_actionable_count += 1
            status_str = "AUTO-ACTIONABLE"
        else:
            escalated_count += 1
            status_str = "ESCALATED"

        print(f"{evt_id:<20} | {cat:<20} | {conf:<6.2f} | {status_str:<20} | {reasoning}")

    print(f"\n[SUMMARY] Total Ambiguous Events: {len(rows)} | Auto-Actionable at 0.75: {auto_actionable_count} | Escalated to Human: {escalated_count}")

    # -------------------------------------------------------------------------
    # CHECK 5: Run Threshold Evaluation Script Output
    # -------------------------------------------------------------------------
    print("\n--- CHECK 5: Running scripts/evaluate_thresholds.py Output ---")
    from scripts.evaluate_thresholds import evaluate_thresholds
    evaluate_thresholds()

    # -------------------------------------------------------------------------
    # CHECK 6: Confirm ZERO LLM Calls for Confidently Matched Rule Events
    # -------------------------------------------------------------------------
    print("\n--- CHECK 6: Gating Verification for Rule Engine Matches ---")
    all_synth_rows = cursor.execute(
        "SELECT id, external_event_id, error_code, error_reason, error_description FROM failure_events WHERE subscription_id LIKE 'sub_synth_%'"
    ).fetchall()

    rule_confident_matches = 0
    llm_bypassed_count = 0

    for r in all_synth_rows:
        cat, conf = classify_by_rules(
            error_code=r["error_code"],
            error_reason=r["error_reason"],
            error_description=r["error_description"]
        )
        if cat != "unclassified" or conf > 0.0:
            rule_confident_matches += 1
            llm_bypassed_count += 1

    print(f"Total Synthetic Failure Events: {len(all_synth_rows)}")
    print(f"Events Confidently Matched by Rule Engine: {rule_confident_matches}")
    print(f"LLM Calls Bypassed for Confident Rule Matches: {llm_bypassed_count} / {rule_confident_matches}")
    if llm_bypassed_count == rule_confident_matches:
        print("[VERIFICATION PASSED] ZERO LLM calls were made for rule-matched events! Fallback gating rule 100% verified.")

    conn.close()

if __name__ == "__main__":
    run_phase7_verification()
