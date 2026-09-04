"""
Unit Tests for Razorpay Webhook Payload Translator (Phase 6)
============================================================

Tests mapping of nested Razorpay webhook payloads into flat failure_events fields.
"""

from api.webhook_translator import translate_razorpay_payload

def test_payment_failed_translation():
    """Confirms a realistic payment.failed payload maps all nested error and subscription fields correctly."""
    payload = {
        "entity": "event",
        "account_id": "acc_001",
        "event": "payment.failed",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_failed_999",
                    "amount": 150000,
                    "currency": "INR",
                    "status": "failed",
                    "order_id": "order_777",
                    "invoice_id": "inv_888",
                    "subscription_id": "sub_rzp_expired_1",
                    "error": {
                        "code": "BAD_REQUEST_ERROR",
                        "description": "Card has expired. Please try another card.",
                        "source": "bank",
                        "step": "payment_authorization",
                        "reason": "card_expired"
                    }
                }
            },
            "subscription": {
                "entity": {
                    "id": "sub_rzp_expired_1",
                    "status": "active"
                }
            }
        },
        "created_at": 1600000000
    }

    result = translate_razorpay_payload(payload)

    assert result["subscription_id"] == "sub_rzp_expired_1"
    assert result["event_type"] == "payment.failed"
    assert result["error_code"] == "BAD_REQUEST_ERROR"
    assert result["error_reason"] == "card_expired"
    assert result["error_description"] == "Card has expired. Please try another card."
    assert result["error_source"] == "bank"
    assert result["error_step"] == "payment_authorization"
    assert isinstance(result["raw_payload"], str)

def test_success_event_missing_error_object():
    """Confirms successful subscription events without an error object translate cleanly with NULLs."""
    payload = {
        "entity": "event",
        "account_id": "acc_001",
        "event": "subscription.activated",
        "contains": ["subscription"],
        "payload": {
            "subscription": {
                "entity": {
                    "id": "sub_rzp_active_100",
                    "status": "active"
                }
            }
        },
        "created_at": 1600000000
    }

    result = translate_razorpay_payload(payload)

    assert result["subscription_id"] == "sub_rzp_active_100"
    assert result["event_type"] == "subscription.activated"
    assert result["error_code"] is None
    assert result["error_reason"] is None
    assert result["error_description"] is None
    assert result["error_source"] is None
    assert result["error_step"] is None
    assert isinstance(result["raw_payload"], str)
