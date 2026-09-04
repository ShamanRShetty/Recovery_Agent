"""
Pure Policy Decision Engine (Phase 3)
=====================================

Layer Separation Rule:
- PURE function only: (category, confidence, case_state/context) in -> (action_type, playbook_rule_id) out.
- ZERO database access, file I/O, network calls, or side effects.
- ZERO imports from executor/ or audit/ layers.
- ZERO retry-timing control or Razorpay API calls.
- Risk block category NEVER inspects contact_count.
"""

from config import CONFIDENCE_THRESHOLD, REPEATED_FAILURE_THRESHOLD, MAX_CONTACTS

# Allowed Action Types
ACTION_SEND_NUDGE = "send_nudge"
ACTION_WAIT = "wait"
ACTION_ESCALATE = "escalate"
ACTION_STOP = "stop"

VALID_ACTION_TYPES = {ACTION_SEND_NUDGE, ACTION_WAIT, ACTION_ESCALATE, ACTION_STOP}

def decide_action(category, confidence, case_state=None, subscription_status=None, attempt_number=1):
    """
    Pure policy decision function implementing playbook rules per failure category.

    Args:
        category (str): Failure category ('insufficient_funds', 'card_expired', etc.)
        confidence (float): Classification confidence [0.0 - 1.0]
        case_state (dict|object|None): Case state object/dict with contact_count, etc.
        subscription_status (str|None): Current status of subscription ('active', 'pending', 'halted', 'cancelled')
        attempt_number (int): Payment failure attempt number from event

    Returns:
        tuple[str, str]: (action_type, playbook_rule_id)
    """
    # 1. GLOBAL RULE: Low confidence escalation (checked first)
    if confidence < CONFIDENCE_THRESHOLD:
        return (ACTION_ESCALATE, "low_confidence_escalation")

    # 2. RISK BLOCK: Unconditional early return (MUST NOT read contact_count)
    if category == "risk_block":
        return (ACTION_ESCALATE, "rb_always_human_review")

    # 3. MANDATE CANCELLED: Terminal stop (no customer contact)
    if category == "mandate_cancelled":
        return (ACTION_STOP, "mc_terminal_no_contact")

    # Extract contact_count safely for categories that use it
    if isinstance(case_state, dict):
        contact_count = case_state.get("contact_count", 0)
    elif hasattr(case_state, "contact_count"):
        contact_count = case_state.contact_count
    else:
        contact_count = 0

    sub_status = (subscription_status or "pending").strip().lower()

    # 4. INSUFFICIENT FUNDS
    if category == "insufficient_funds":
        if sub_status == "active":
            return (ACTION_STOP, "if_recovered")
        if sub_status == "halted":
            return (ACTION_ESCALATE, "if_retries_exhausted")
        if contact_count >= MAX_CONTACTS:
            return (ACTION_ESCALATE, "if_contact_limit_reached")
        
        if attempt_number == 1:
            return (ACTION_WAIT, "if_wait")

        if attempt_number >= REPEATED_FAILURE_THRESHOLD and contact_count == 0 and sub_status == "pending":
            return (ACTION_SEND_NUDGE, "if_courtesy_reminder")
        
        return (ACTION_WAIT, "if_wait")

    # 5. CARD EXPIRED
    if category == "card_expired":
        if sub_status == "active":
            return (ACTION_STOP, "ce_recovered")
        if contact_count >= MAX_CONTACTS:
            return (ACTION_ESCALATE, "ce_contact_limit_reached")
        if contact_count == 0:
            return (ACTION_SEND_NUDGE, "ce_first_nudge")
        if contact_count == 1:
            return (ACTION_SEND_NUDGE, "ce_second_nudge")

    # 6. CARD NOT ENABLED
    if category == "card_not_enabled":
        if sub_status == "active":
            return (ACTION_STOP, "cne_recovered")
        if contact_count == 0:
            return (ACTION_SEND_NUDGE, "cne_instructional_message")
        if contact_count >= 1:
            return (ACTION_ESCALATE, "cne_single_nudge_limit")

    # 7. UNCLASSIFIED FALLBACK
    return (ACTION_ESCALATE, "unclassified_fallback_escalation")
