import unittest
import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from classifier.rules import (
    classify_by_rules,
    CATEGORY_INSUFFICIENT_FUNDS,
    CATEGORY_CARD_EXPIRED,
    CATEGORY_CARD_NOT_ENABLED,
    CATEGORY_RISK_BLOCK,
    CATEGORY_MANDATE_CANCELLED,
    CATEGORY_UNCLASSIFIED
)

class TestDeterministicClassifier(unittest.TestCase):

    def test_insufficient_funds_matching(self):
        cat, conf = classify_by_rules(
            error_code="BAD_REQUEST_ERROR",
            error_reason="payment_failed",
            error_description="Insufficient balance in customer account",
            error_source="bank",
            error_step="payment_execution"
        )
        self.assertEqual(cat, CATEGORY_INSUFFICIENT_FUNDS)
        self.assertEqual(conf, 1.0)

    def test_card_expired_matching(self):
        cat, conf = classify_by_rules(
            error_code="BAD_REQUEST_ERROR",
            error_reason="card_expired",
            error_description="Card has expired",
            error_source="issuer",
            error_step="payment_authorization"
        )
        self.assertEqual(cat, CATEGORY_CARD_EXPIRED)
        self.assertEqual(conf, 1.0)

    def test_card_not_enabled_matching(self):
        cat, conf = classify_by_rules(
            error_code="BAD_REQUEST_ERROR",
            error_reason="payment_failed",
            error_description="International or e-commerce transaction not enabled on card",
            error_source="bank",
            error_step="payment_authorization"
        )
        self.assertEqual(cat, CATEGORY_CARD_NOT_ENABLED)
        self.assertEqual(conf, 1.0)

    def test_risk_block_matching(self):
        cat, conf = classify_by_rules(
            error_code="GATEWAY_ERROR",
            error_reason="payment_risk_block",
            error_description="High risk transaction blocked by fraud prevention engine",
            error_source="gateway",
            error_step="payment_authorization"
        )
        self.assertEqual(cat, CATEGORY_RISK_BLOCK)
        self.assertEqual(conf, 1.0)

    def test_mandate_cancelled_matching(self):
        cat, conf = classify_by_rules(
            error_code="BAD_REQUEST_ERROR",
            error_reason="mandate_inactive",
            error_description="Mandate revoked by customer at bank",
            error_source="bank",
            error_step="mandate_validation"
        )
        self.assertEqual(cat, CATEGORY_MANDATE_CANCELLED)
        self.assertEqual(conf, 1.0)

    def test_unclassified_fallback_matching(self):
        cat, conf = classify_by_rules(
            error_code="SERVER_ERROR",
            error_reason="internal_error",
            error_description="Unknown bank code 999",
            error_source="bank",
            error_step="payment_execution"
        )
        self.assertEqual(cat, CATEGORY_UNCLASSIFIED)
        self.assertEqual(conf, 0.0)

    def test_null_and_empty_description_handling(self):
        # Test None error_description with non-specific reason
        cat1, conf1 = classify_by_rules(
            error_code="BAD_REQUEST_ERROR",
            error_reason="payment_failed",
            error_description=None
        )
        self.assertEqual(cat1, CATEGORY_UNCLASSIFIED)
        self.assertEqual(conf1, 0.0)

        # Test empty string error_description
        cat2, conf2 = classify_by_rules(
            error_code="BAD_REQUEST_ERROR",
            error_reason="payment_failed",
            error_description="   "
        )
        self.assertEqual(cat2, CATEGORY_UNCLASSIFIED)
        self.assertEqual(conf2, 0.0)

    def test_ambiguous_and_generic_input_returns_unclassified(self):
        cat, conf = classify_by_rules(
            error_code="BAD_REQUEST_ERROR",
            error_reason="payment_failed",
            error_description="transaction could not be completed"
        )
        self.assertEqual(cat, CATEGORY_UNCLASSIFIED)
        self.assertEqual(conf, 0.0)

    def test_contradictory_signals_return_unclassified(self):
        # Description hints at card expired AND insufficient balance
        cat, conf = classify_by_rules(
            error_code="BAD_REQUEST_ERROR",
            error_reason="payment_failed",
            error_description="Card expired and insufficient balance in linked account"
        )
        self.assertEqual(cat, CATEGORY_UNCLASSIFIED)
        self.assertEqual(conf, 0.0)

        # Contradictory signal 2: risk block reason + mandate cancelled description
        cat2, conf2 = classify_by_rules(
            error_code="GATEWAY_ERROR",
            error_reason="payment_risk_block",
            error_description="Mandate revoked by customer at bank"
        )
        self.assertEqual(cat2, CATEGORY_UNCLASSIFIED)
        self.assertEqual(conf2, 0.0)

if __name__ == "__main__":
    unittest.main()
