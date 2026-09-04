import unittest
import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import CONFIDENCE_THRESHOLD
from engine.policy import (
    decide_action,
    ACTION_SEND_NUDGE,
    ACTION_WAIT,
    ACTION_ESCALATE,
    ACTION_STOP
)

class TestPolicyEngine(unittest.TestCase):

    def test_global_low_confidence_escalation(self):
        # Confidence < 0.75 must escalate regardless of category or state
        action, rule = decide_action(
            category="insufficient_funds",
            confidence=0.50,
            case_state={"contact_count": 0},
            subscription_status="pending",
            attempt_number=1
        )
        self.assertEqual(action, ACTION_ESCALATE)
        self.assertEqual(rule, "low_confidence_escalation")

        # Zero confidence (unclassified rows)
        action_uncl, rule_uncl = decide_action(
            category="unclassified",
            confidence=0.0,
            case_state={"contact_count": 0},
            subscription_status="pending",
            attempt_number=1
        )
        self.assertEqual(action_uncl, ACTION_ESCALATE)
        self.assertEqual(rule_uncl, "low_confidence_escalation")

    def test_risk_block_never_checks_contact_count(self):
        """
        RIGOROUS STRUCTURAL PROOF:
        Tests all combinations of contact_count, subscription_status, attempt_number,
        and malformed/missing case_state objects.
        Risk block MUST ALWAYS return ('escalate', 'rb_always_human_review') with ZERO exceptions.
        """
        contact_counts_to_test = [0, 1, 2, 3, 5, 10, 999, -1, None]
        statuses_to_test = ["active", "pending", "halted", "cancelled", "unknown", None, ""]
        attempts_to_test = [1, 2, 5, 10, 100]
        case_states_to_test = [
            None,
            {},
            {"contact_count": 0},
            {"contact_count": 99},
            "malformed_string_state",
            12345
        ]

        total_tested_combinations = 0

        for contacts in contact_counts_to_test:
            for status in statuses_to_test:
                for attempt in attempts_to_test:
                    for cs in case_states_to_test:
                        # Override contact_count in dict state if applicable
                        state_arg = cs
                        if isinstance(cs, dict) and contacts is not None:
                            state_arg = {"contact_count": contacts}

                        action, rule = decide_action(
                            category="risk_block",
                            confidence=1.0,
                            case_state=state_arg,
                            subscription_status=status,
                            attempt_number=attempt
                        )

                        self.assertEqual(
                            action, ACTION_ESCALATE,
                            f"Risk block failed safety check for state={state_arg}, status={status}, attempt={attempt}. Got action={action}"
                        )
                        self.assertEqual(
                            rule, "rb_always_human_review",
                            f"Risk block failed rule ID check for state={state_arg}, status={status}. Got rule={rule}"
                        )
                        self.assertNotEqual(action, ACTION_SEND_NUDGE, "Risk block must NEVER trigger automated nudge!")
                        self.assertNotEqual(action, ACTION_WAIT, "Risk block must NEVER trigger wait!")
                        self.assertNotEqual(action, ACTION_STOP, "Risk block must NEVER trigger stop!")
                        
                        total_tested_combinations += 1

        print(f"\n[RISK_BLOCK PROOF] Successfully verified risk_block safety across {total_tested_combinations} input combinations.")

    def test_mandate_cancelled_terminal_stop(self):
        action, rule = decide_action(
            category="mandate_cancelled",
            confidence=1.0,
            case_state={"contact_count": 0},
            subscription_status="cancelled",
            attempt_number=1
        )
        self.assertEqual(action, ACTION_STOP)
        self.assertEqual(rule, "mc_terminal_no_contact")

    def test_insufficient_funds_sequence(self):
        # Attempt 1 -> wait
        a1, r1 = decide_action("insufficient_funds", 1.0, {"contact_count": 0}, "pending", attempt_number=1)
        self.assertEqual(a1, ACTION_WAIT)
        self.assertEqual(r1, "if_wait")

        # Attempt 2, contact_count 0 -> send_nudge (courtesy reminder)
        a2, r2 = decide_action("insufficient_funds", 1.0, {"contact_count": 0}, "pending", attempt_number=2)
        self.assertEqual(a2, ACTION_SEND_NUDGE)
        self.assertEqual(r2, "if_courtesy_reminder")

        # Halted subscription -> escalate
        a3, r3 = decide_action("insufficient_funds", 1.0, {"contact_count": 1}, "halted", attempt_number=4)
        self.assertEqual(a3, ACTION_ESCALATE)
        self.assertEqual(r3, "if_retries_exhausted")

        # Active subscription -> stop (recovered)
        a4, r4 = decide_action("insufficient_funds", 1.0, {"contact_count": 1}, "active", attempt_number=2)
        self.assertEqual(a4, ACTION_STOP)
        self.assertEqual(r4, "if_recovered")

        # Contact limit reached -> escalate
        a5, r5 = decide_action("insufficient_funds", 1.0, {"contact_count": 2}, "pending", attempt_number=3)
        self.assertEqual(a5, ACTION_ESCALATE)
        self.assertEqual(r5, "if_contact_limit_reached")

    def test_card_expired_sequence(self):
        # Contact 0 -> first nudge
        a0, r0 = decide_action("card_expired", 1.0, {"contact_count": 0}, "pending", 1)
        self.assertEqual(a0, ACTION_SEND_NUDGE)
        self.assertEqual(r0, "ce_first_nudge")

        # Contact 1 -> second nudge
        a1, r1 = decide_action("card_expired", 1.0, {"contact_count": 1}, "pending", 2)
        self.assertEqual(a1, ACTION_SEND_NUDGE)
        self.assertEqual(r1, "ce_second_nudge")

        # Contact 2 -> escalate (contact limit reached)
        a2, r2 = decide_action("card_expired", 1.0, {"contact_count": 2}, "pending", 3)
        self.assertEqual(a2, ACTION_ESCALATE)
        self.assertEqual(r2, "ce_contact_limit_reached")

    def test_card_not_enabled_sequence(self):
        # Contact 0 -> instructional nudge
        a0, r0 = decide_action("card_not_enabled", 1.0, {"contact_count": 0}, "pending", 1)
        self.assertEqual(a0, ACTION_SEND_NUDGE)
        self.assertEqual(r0, "cne_instructional_message")

        # Contact 1 -> escalate (single nudge limit)
        a1, r1 = decide_action("card_not_enabled", 1.0, {"contact_count": 1}, "pending", 2)
        self.assertEqual(a1, ACTION_ESCALATE)
        self.assertEqual(r1, "cne_single_nudge_limit")

if __name__ == "__main__":
    unittest.main()
