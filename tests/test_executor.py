import unittest
import json
import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from executor.actions import execute_action

class TestActionExecutor(unittest.TestCase):

    def test_send_nudge_execution(self):
        simulated, result, payload_json = execute_action(
            action_type="send_nudge",
            playbook_rule_id="ce_first_nudge",
            category="card_expired",
            subscription_id="sub_test_001",
            attempt_number=1,
            case_status="open"
        )
        self.assertEqual(simulated, 1)
        self.assertEqual(result, "success")
        
        payload = json.loads(payload_json)
        self.assertEqual(payload["action"], "send_nudge")
        self.assertEqual(payload["channel"], "email_sms_simulated")
        self.assertEqual(payload["recipient_subscription_id"], "sub_test_001")
        self.assertIn("has expired", payload["message_text"])

    def test_wait_execution_no_op(self):
        simulated, result, payload_json = execute_action(
            action_type="wait",
            playbook_rule_id="if_wait",
            category="insufficient_funds",
            subscription_id="sub_test_002",
            attempt_number=1,
            case_status="open"
        )
        self.assertEqual(simulated, 1)
        self.assertEqual(result, "no_op")
        
        payload = json.loads(payload_json)
        self.assertEqual(payload["action"], "wait")
        self.assertFalse(payload["customer_contacted"])
        self.assertNotIn("message_text", payload)
        self.assertIn("Awaiting Razorpay native retry", payload["reason"])

    def test_escalate_execution(self):
        simulated, result, payload_json = execute_action(
            action_type="escalate",
            playbook_rule_id="rb_always_human_review",
            category="risk_block",
            subscription_id="sub_test_003",
            attempt_number=1,
            case_status="open"
        )
        self.assertEqual(simulated, 1)
        self.assertEqual(result, "success")
        
        payload = json.loads(payload_json)
        self.assertEqual(payload["action"], "escalate")
        self.assertEqual(payload["queue"], "human_review_queue")
        self.assertIn("rb_always_human_review", payload["playbook_rule_id"])

    def test_stop_execution(self):
        simulated, result, payload_json = execute_action(
            action_type="stop",
            playbook_rule_id="mc_terminal_no_contact",
            category="mandate_cancelled",
            subscription_id="sub_test_004",
            attempt_number=1,
            case_status="stopped"
        )
        self.assertEqual(simulated, 1)
        self.assertEqual(result, "success")
        
        payload = json.loads(payload_json)
        self.assertEqual(payload["action"], "stop")
        self.assertEqual(payload["closure_type"], "terminal_stop")

    def test_invalid_action_type_raises_error(self):
        with self.assertRaises(ValueError) as ctx:
            execute_action(
                action_type="invalid_action_type",
                playbook_rule_id="rule_unknown",
                category="card_expired",
                subscription_id="sub_test_005",
                attempt_number=1,
                case_status="open"
            )
        self.assertIn("Unrecognized action_type", str(ctx.exception))

if __name__ == "__main__":
    unittest.main()
