"""
Razorpay Webhook Signature Verification (Phase 6)
===============================================

Computes HMAC-SHA256 hex digest of raw request body and verifies it against
the X-Razorpay-Signature header using constant-time comparison.
"""

import hashlib
import hmac

def verify_razorpay_signature(raw_body: bytes, signature_header: str, secret: str) -> bool:
    """
    Verifies the HMAC-SHA256 signature of a Razorpay webhook payload.

    Args:
        raw_body (bytes): Unparsed raw request body bytes.
        signature_header (str|None): Value of X-Razorpay-Signature header.
        secret (str|None): Razorpay webhook secret configured in environment.

    Returns:
        bool: True if signature is valid, False otherwise.
    """
    if not raw_body or not signature_header or not secret:
        return False

    try:
        secret_bytes = secret.encode("utf-8")
        expected_signature = hmac.new(
            secret_bytes,
            raw_body,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected_signature, signature_header.strip())
    except Exception:
        return False
