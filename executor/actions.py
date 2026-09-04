"""
Simulated Action Executor (Phase 4)
==================================

Layer Separation Rule:
- EXECUTION function only: takes a decision record and subscription context, executes the specified action.
- ZERO decision logic, zero re-classification, zero policy re-evaluation.
- 100% SIMULATED customer outreach (email/SMS), human review queue entries, and case closures.
- ZERO real network calls, zero external API requests, zero real email/SMS sends.
- ZERO automatic subscription cancellation logic.
"""

import json

# Static Message Templates per Category (No LLM copy generation)
NUDGE_TEMPLATES = {
    "card_expired": (
        "Action Required: Your card for subscription {subscription_id} has expired. "
        "Please update your payment method to ensure uninterrupted service."
    ),
    "card_not_enabled": (
        "Action Required: Online or recurring transactions are disabled on your card for subscription {subscription_id}. "
        "Please enable e-commerce / recurring permissions via your bank's mobile app."
    ),
    "insufficient_funds": (
        "Courtesy Reminder: A recent recurring payment for subscription {subscription_id} could not be processed due to insufficient account balance. "
        "Please ensure adequate account balance for upcoming charges."
    ),
    "default": (
        "Courtesy Notice: Please review your payment method status for subscription {subscription_id}."
    )
}

def execute_action(action_type, playbook_rule_id, category, subscription_id, attempt_number=1, case_status=None):
    """
    Executes a policy decision cleanly according to its specified action_type.

    Args:
        action_type (str): 'send_nudge', 'wait', 'escalate', or 'stop'
        playbook_rule_id (str): Playbook rule that triggered the decision
        category (str): Failure category
        subscription_id (str): Target subscription ID
        attempt_number (int): Payment failure attempt number
        case_status (str|None): Current status of the case ('open', 'recovered', 'escalated', 'stopped')

    Returns:
        tuple[int, str, str]: (simulated, result, payload_json)
        - simulated: 1 (always 1 for MVP)
        - result: 'success' or 'no_op'
        - payload_json: Formatted JSON string describing payload / audit details
    """
    if action_type == "send_nudge":
        template = NUDGE_TEMPLATES.get(category, NUDGE_TEMPLATES["default"])
        message_text = template.format(subscription_id=subscription_id)
        
        payload_dict = {
            "action": "send_nudge",
            "channel": "email_sms_simulated",
            "recipient_subscription_id": subscription_id,
            "category": category,
            "playbook_rule_id": playbook_rule_id,
            "message_text": message_text,
            "simulated": True
        }
        return (1, "success", json.dumps(payload_dict))

    elif action_type == "wait":
        payload_dict = {
            "action": "wait",
            "reason": "Awaiting Razorpay native retry engine",
            "attempt_number": attempt_number,
            "playbook_rule_id": playbook_rule_id,
            "customer_contacted": False
        }
        return (1, "no_op", json.dumps(payload_dict))

    elif action_type == "escalate":
        payload_dict = {
            "action": "escalate",
            "queue": "human_review_queue",
            "subscription_id": subscription_id,
            "escalation_reason": f"Escalated via playbook rule '{playbook_rule_id}'",
            "playbook_rule_id": playbook_rule_id,
            "category": category
        }
        return (1, "success", json.dumps(payload_dict))

    elif action_type == "stop":
        closure_type = "recovered_stop" if case_status == "recovered" else "terminal_stop"
        payload_dict = {
            "action": "stop",
            "closure_type": closure_type,
            "subscription_id": subscription_id,
            "case_status": case_status or "stopped",
            "playbook_rule_id": playbook_rule_id
        }
        return (1, "success", json.dumps(payload_dict))

    else:
        # Strict boundary enforcement: fail loudly on unrecognized action_type
        raise ValueError(f"Unrecognized action_type: '{action_type}'. Must be one of ('send_nudge', 'wait', 'escalate', 'stop').")
