"""
Unit Tests for Webhook Signature Verification (Phase 6)
======================================================

Tests HMAC-SHA256 signature verification logic in api/webhook_security.py.
"""

import hashlib
import hmac

from api.webhook_security import verify_razorpay_signature

TEST_SECRET = "test_webhook_secret_key_12345"
TEST_BODY = b'{"event":"payment.failed","payload":{"payment":{"entity":{"id":"pay_123"}}}}'

# Compute valid signature for test triple
VALID_SIGNATURE = hmac.new(
    TEST_SECRET.encode("utf-8"),
    TEST_BODY,
    hashlib.sha256
).hexdigest()

def test_valid_signature_accepted():
    """Confirms valid signature header is accepted."""
    assert verify_razorpay_signature(TEST_BODY, VALID_SIGNATURE, TEST_SECRET) is True

def test_tampered_body_rejected():
    """Confirms tampered raw body is rejected even with original signature."""
    tampered_body = b'{"event":"payment.failed","payload":{"payment":{"entity":{"id":"pay_HACKED"}}}}'
    assert verify_razorpay_signature(tampered_body, VALID_SIGNATURE, TEST_SECRET) is False

def test_wrong_secret_rejected():
    """Confirms signature computed with a different secret is rejected."""
    wrong_secret = "wrong_secret_key_99999"
    assert verify_razorpay_signature(TEST_BODY, VALID_SIGNATURE, wrong_secret) is False

def test_missing_header_rejected():
    """Confirms missing or empty signature header is rejected."""
    assert verify_razorpay_signature(TEST_BODY, "", TEST_SECRET) is False
    assert verify_razorpay_signature(TEST_BODY, None, TEST_SECRET) is False

def test_empty_secret_or_body_rejected():
    """Confirms empty body or empty secret is rejected."""
    assert verify_razorpay_signature(b"", VALID_SIGNATURE, TEST_SECRET) is False
    assert verify_razorpay_signature(TEST_BODY, VALID_SIGNATURE, "") is False
