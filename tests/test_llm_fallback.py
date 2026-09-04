"""
Unit Tests for Pure LLM Fallback Classifier (Phase 7 & 9)
=====================================================

Tests validation, error handling, response parsing, and pipeline gating in classifier/llm_fallback.py
and pipeline/process_event.py using MOCKED LLM API calls.
"""

import unittest
import json
import sqlite3
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError
from io import BytesIO

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from classifier.llm_fallback import classify_by_llm, _call_gemini_api
from pipeline.process_event import process_failure_event

def get_in_memory_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    schema_path = os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    return conn

class TestLLMFallbackClassifier(unittest.TestCase):

    @patch("classifier.llm_fallback._call_gemini_api")
    def test_valid_well_formed_json_response(self, mock_gemini):
        """Confirms a valid JSON response with allowed category and confidence is accepted."""
        mock_gemini.return_value = '{"category": "card_expired", "confidence": 0.85, "reasoning": "Explicit card expiry phrase found"}'
        
        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_gemini_key"}):
            category, confidence, reasoning = classify_by_llm(error_description="Card has expired")

        self.assertEqual(category, "card_expired")
        self.assertEqual(confidence, 0.85)
        self.assertEqual(reasoning, "Explicit card expiry phrase found")

    @patch("classifier.llm_fallback._call_gemini_api")
    def test_invalid_category_rejected(self, mock_gemini):
        """Confirms a category outside the 6 allowed values is rejected and falls back to unclassified/0.0."""
        mock_gemini.return_value = '{"category": "fraudulent_charge", "confidence": 0.90, "reasoning": "Unrecognized category"}'
        
        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_gemini_key"}):
            category, confidence, reasoning = classify_by_llm(error_description="Unrecognized error")

        self.assertEqual(category, "unclassified")
        self.assertEqual(confidence, 0.0)
        self.assertIn("Invalid category 'fraudulent_charge'", reasoning)

    @patch("classifier.llm_fallback._call_gemini_api")
    def test_confidence_out_of_range_rejected(self, mock_gemini):
        """Confirms confidence > 1.0 or < 0.0 is rejected and falls back to unclassified/0.0."""
        mock_gemini.return_value = '{"category": "insufficient_funds", "confidence": 1.5, "reasoning": "Inflated confidence"}'
        
        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_gemini_key"}):
            category, confidence, reasoning = classify_by_llm(error_description="Balance low")

        self.assertEqual(category, "unclassified")
        self.assertEqual(confidence, 0.0)
        self.assertIn("out of range", reasoning)

    @patch("classifier.llm_fallback._call_gemini_api")
    def test_non_json_garbled_response_rejected(self, mock_gemini):
        """Confirms non-JSON or garbled response is rejected cleanly."""
        mock_gemini.return_value = "Sorry, I cannot classify this payment error text."
        
        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_gemini_key"}):
            category, confidence, reasoning = classify_by_llm(error_description="Garbled")

        self.assertEqual(category, "unclassified")
        self.assertEqual(confidence, 0.0)
        self.assertIn("Malformed JSON", reasoning)

    @patch("classifier.llm_fallback._call_gemini_api")
    def test_network_api_exception_handled_safely(self, mock_gemini):
        """Confirms network error / API timeout exception is caught and falls back to unclassified/0.0."""
        mock_gemini.side_effect = RuntimeError("API service connection timeout")
        
        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_gemini_key"}):
            category, confidence, reasoning = classify_by_llm(error_description="Timeout test")

        self.assertEqual(category, "unclassified")
        self.assertEqual(confidence, 0.0)
        self.assertIn("LLM call failed: API service connection timeout", reasoning)

    def test_missing_api_key_handled_safely(self):
        """Confirms missing API key in environment returns unclassified/0.0 without attempting network call."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": "", "ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": ""}):
            category, confidence, reasoning = classify_by_llm(error_description="No key")

        self.assertEqual(category, "unclassified")
        self.assertEqual(confidence, 0.0)
        self.assertIn("No API key configured", reasoning)

    @patch("pipeline.process_event.classify_by_llm")
    def test_llm_never_invoked_when_rule_matches(self, mock_llm):
        """Confirms that when rules match (confidence=1.0), LLM fallback is NEVER called."""
        conn = get_in_memory_db()
        cursor = conn.cursor()

        # Insert subscription and failure event for card_expired (rule match)
        cursor.execute("INSERT INTO subscriptions (id, customer_id, plan_amount, currency, status, created_at) VALUES ('sub_gating_test', 'cust_1', 1000, 'INR', 'active', '2026-09-04T00:00:00Z')")
        cursor.execute(
            """
            INSERT INTO failure_events (subscription_id, external_event_id, event_type, error_code, error_reason, error_description, attempt_number, received_at)
            VALUES ('sub_gating_test', 'evt_gating_1', 'payment.failed', 'BAD_REQUEST', 'card_expired', 'Card has expired', 1, '2026-09-04T00:00:00Z')
            """
        )
        fe_id = cursor.lastrowid
        conn.commit()

        # Run process_failure_event
        process_failure_event(fe_id, conn=conn)

        # Assert LLM was never called
        mock_llm.assert_not_called()
        conn.close()


class TestGeminiApi404Retry(unittest.TestCase):
    """Finding #9: Direct test coverage for the 404-retry model fallback loop in _call_gemini_api."""

    @patch("classifier.llm_fallback.urllib.request.urlopen")
    def test_404_on_first_model_retries_to_second(self, mock_urlopen):
        """HTTP 404 on model 1 should silently continue to model 2 and return its response."""
        valid_response = json.dumps({
            "candidates": [{"content": {"parts": [{"text": '{"category": "card_expired", "confidence": 0.9, "reasoning": "test"}'}]}}]
        }).encode("utf-8")

        call_count = 0
        def side_effect(req, timeout=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise HTTPError(req.full_url, 404, "Not Found", {}, BytesIO(b""))
            mock_resp = MagicMock()
            mock_resp.read.return_value = valid_response
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        mock_urlopen.side_effect = side_effect

        result = _call_gemini_api("fake_key", "test input")
        self.assertIn("card_expired", result)
        self.assertEqual(call_count, 2)

    @patch("classifier.llm_fallback.urllib.request.urlopen")
    def test_non_404_http_error_fails_fast(self, mock_urlopen):
        """HTTP 429 (rate limit) on model 1 should raise immediately without trying model 2."""
        mock_urlopen.side_effect = HTTPError("http://example.com", 429, "Rate Limited", {}, BytesIO(b""))

        with self.assertRaises(HTTPError) as ctx:
            _call_gemini_api("fake_key", "test input")
        self.assertEqual(ctx.exception.code, 429)
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch("classifier.llm_fallback.urllib.request.urlopen")
    def test_all_models_404_raises_last_error(self, mock_urlopen):
        """If all 4 candidate models return 404, the last HTTPError should be raised."""
        mock_urlopen.side_effect = HTTPError("http://example.com", 404, "Not Found", {}, BytesIO(b""))

        with self.assertRaises(HTTPError) as ctx:
            _call_gemini_api("fake_key", "test input")
        self.assertEqual(ctx.exception.code, 404)
        self.assertEqual(mock_urlopen.call_count, 4)


if __name__ == "__main__":
    unittest.main()
