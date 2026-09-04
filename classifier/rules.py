"""
Pure Deterministic Rule-Based Failure Classifier (Phase 2)
==========================================================

Layer Separation Rule:
- PURE function only: input arguments in, (category, confidence) tuple out.
- ZERO database access, file I/O, network calls, or side effects.
- ZERO imports from engine/, executor/, or audit/ layers.
- Fixed confidence = 1.0 for rule matches, confidence = 0.0 for unclassified.
- Returns ('unclassified', 0.0) if 0 rules match OR if multiple conflicting rules match.
"""

import re

# Category Constants
CATEGORY_INSUFFICIENT_FUNDS = "insufficient_funds"
CATEGORY_CARD_EXPIRED = "card_expired"
CATEGORY_CARD_NOT_ENABLED = "card_not_enabled"
CATEGORY_RISK_BLOCK = "risk_block"
CATEGORY_MANDATE_CANCELLED = "mandate_cancelled"
CATEGORY_UNCLASSIFIED = "unclassified"

# NOTE: Excludes \"unclassified\" because rules never produce it directly —
# unclassified is only returned as a fallback when zero or multiple categories match.
# The LLM fallback's VALID_CATEGORIES in llm_fallback.py includes \"unclassified\".
VALID_CATEGORIES = {
    CATEGORY_INSUFFICIENT_FUNDS,
    CATEGORY_CARD_EXPIRED,
    CATEGORY_CARD_NOT_ENABLED,
    CATEGORY_RISK_BLOCK,
    CATEGORY_MANDATE_CANCELLED,
}

def _check_insufficient_funds(reason, desc):
    if reason == "payment_failed" and desc:
        patterns = [
            r"\binsufficient balance\b",
            r"\blow balance\b",
            r"\baccount balance (low|insufficient)\b",
            r"\bbalance insufficient\b",
            r"\bbalance low\b",
            r"\binsufficient funds\b"
        ]
        if any(re.search(p, desc) for p in patterns):
            return True
    return False

def _check_card_expired(reason, desc):
    if reason == "card_expired":
        return True
    if desc:
        patterns = [
            r"\bcard (has )?expired\b",
            r"\bexpired card\b",
            r"\bcard expiry\b",
            r"\bexpiry date in past\b"
        ]
        if any(re.search(p, desc) for p in patterns):
            return True
    return False

def _check_card_not_enabled(reason, desc):
    if desc:
        patterns = [
            r"\bnot enabled on card\b",
            r"\bpermissions disabled on card\b",
            r"\bnot allowed on card type\b",
            r"\bdisabled by cardholder\b",
            r"\be-commerce (channel )?disabled\b",
            r"\binternational or e-commerce\b"
        ]
        if any(re.search(p, desc) for p in patterns):
            return True
    return False

def _check_risk_block(reason, desc):
    if reason == "payment_risk_block":
        return True
    if desc:
        patterns = [
            r"\brisk (transaction|engine|restriction|block)\b",
            r"\bfraud(ulent)? (prevention|activity|system)\b",
            r"\bblocked by fraud\b",
            r"\brisk block\b"
        ]
        if any(re.search(p, desc) for p in patterns):
            return True
    return False

def _check_mandate_cancelled(reason, desc):
    if reason == "mandate_inactive":
        return True
    if desc:
        patterns = [
            r"\bmandate (revoked|cancelled|registration|inactive|not active)\b",
            r"\bautopay mandate\b",
            r"\brecurring mandate\b"
        ]
        if any(re.search(p, desc) for p in patterns):
            return True
    return False

def classify_by_rules(error_code=None, error_reason=None, error_description=None, error_source=None, error_step=None):
    """
    Classifies a Razorpay payment failure event deterministically.
    
    Args:
        error_code (str|None): Razorpay error.code
        error_reason (str|None): Razorpay error.reason
        error_description (str|None): Razorpay error.description
        error_source (str|None): Razorpay error.source
        error_step (str|None): Razorpay error.step
        
    Returns:
        tuple[str, float]: (category, confidence)
        - Single unambiguous rule match: (category, 1.0)
        - Zero matches or contradictory signals: ('unclassified', 0.0)

    Note:
        Current rule set evaluates only ``error_reason`` and ``error_description``.
        The remaining arguments (``error_code``, ``error_source``, ``error_step``) are
        accepted for API symmetry with webhook payloads but are not evaluated in the
        MVP rule set.
    """
    reason = (error_reason or "").strip().lower()
    desc = (error_description or "").strip().lower() if error_description else None

    # Evaluate matches across all non-unclassified categories
    matches = set()
    
    if _check_insufficient_funds(reason, desc):
        matches.add(CATEGORY_INSUFFICIENT_FUNDS)
        
    if _check_card_expired(reason, desc):
        matches.add(CATEGORY_CARD_EXPIRED)
        
    if _check_card_not_enabled(reason, desc):
        matches.add(CATEGORY_CARD_NOT_ENABLED)
        
    if _check_risk_block(reason, desc):
        matches.add(CATEGORY_RISK_BLOCK)
        
    if _check_mandate_cancelled(reason, desc):
        matches.add(CATEGORY_MANDATE_CANCELLED)

    # Exactly one unambiguous category match -> return (category, 1.0)
    if len(matches) == 1:
        return (list(matches)[0], 1.0)
        
    # Zero matches OR multiple contradictory category matches -> return ('unclassified', 0.0)
    return (CATEGORY_UNCLASSIFIED, 0.0)
