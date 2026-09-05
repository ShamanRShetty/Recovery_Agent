"""
Razorpay Webhook Payload Translator (Phase 6)
==============================================

Translates nested Razorpay webhook payload JSON into the flat column structure
expected by the failure_events database table.
"""

import json
from typing import Any, Dict

def translate_razorpay_payload(payload_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Translates a Razorpay webhook JSON payload into flat failure_events dictionary.

    Args:
        payload_json (dict): Parsed JSON dictionary from raw webhook request body.

    Returns:
        dict: Translated dictionary containing:
            - subscription_id (str)
            - event_type (str)
            - error_code (str|None)
            - error_reason (str|None)
            - error_description (str|None)
            - error_source (str|None)
            - error_step (str|None)
            - raw_payload (str)
    """
    if not isinstance(payload_json, dict):
        raise ValueError("Malformed webhook payload structure: root JSON must be an object")

    event_type = payload_json.get("event", "payment.failed")
    payload_obj = payload_json.get("payload", {}) if isinstance(payload_json.get("payload"), dict) else {}

    payment_entity = payload_obj.get("payment", {}).get("entity", {}) if isinstance(payload_obj.get("payment"), dict) else {}
    sub_entity = payload_obj.get("subscription", {}).get("entity", {}) if isinstance(payload_obj.get("subscription"), dict) else {}

    # Extract subscription_id from subscription entity or payment entity
    subscription_id = (
        sub_entity.get("id") or 
        payment_entity.get("subscription_id") or 
        payload_json.get("subscription_id") or 
        "sub_unknown"
    )

    # Extract error sub-object or direct error fields from payment entity
    error_obj = payment_entity.get("error", {}) if isinstance(payment_entity.get("error"), dict) else {}

    error_code = error_obj.get("code") or payment_entity.get("error_code")
    error_reason = error_obj.get("reason") or payment_entity.get("error_reason")
    error_description = error_obj.get("description") or payment_entity.get("error_description")
    error_source = error_obj.get("source") or payment_entity.get("error_source")
    error_step = error_obj.get("step") or payment_entity.get("error_step")

    # Serialize raw JSON payload completely for audit completeness
    raw_payload_str = json.dumps(payload_json)

    return {
        "subscription_id": subscription_id,
        "event_type": event_type,
        "error_code": error_code,
        "error_reason": error_reason,
        "error_description": error_description,
        "error_source": error_source,
        "error_step": error_step,
        "raw_payload": raw_payload_str
    }
