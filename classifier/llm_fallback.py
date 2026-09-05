"""
Pure LLM Fallback Classifier (Phase 7)
=====================================

Provides an LLM-based failure classification fallback for ambiguous payment failure events
that returned ('unclassified', 0.0) from the deterministic rule classifier.

CRITICAL ARCHITECTURAL BOUNDARY:
- NO imports from engine/ or executor/.
- Receives raw event error fields ONLY (NO PII: no customer_id, name, card number, email, or phone).
- Returns ONLY (category, confidence, reasoning).
- STRICT VALIDATION: returns ('unclassified', 0.0, 'LLM response failed validation: <details>') on any validation failure.
"""

import json
import logging
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Tuple

# Automatically load .env file if present
env_file = Path(__file__).resolve().parent.parent / ".env"
if env_file.exists():
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip().strip("'\""))

logger = logging.getLogger("llm_fallback")

# Allowed 6 categories ONLY - Never introduce a 7th
# NOTE: Includes "unclassified" because the LLM may legitimately return it as a classification.
# The rule engine's VALID_CATEGORIES in rules.py excludes "unclassified" since rules never produce it.
VALID_CATEGORIES = {
    "insufficient_funds",
    "card_expired",
    "card_not_enabled",
    "risk_block",
    "mandate_cancelled",
    "unclassified",
}

SYSTEM_PROMPT = """You are an expert payment failure classification engine.
Your task is to analyze Razorpay payment failure event details and classify the failure into EXACTLY ONE of the following 6 categories:
1. insufficient_funds - Balance insufficient, low balance, or account balance error
2. card_expired - Card has expired, expiry date in past, or card expiry error
3. card_not_enabled - Online, e-commerce, or recurring transactions disabled on card
4. risk_block - Risk engine block, fraud prevention, or security restriction
5. mandate_cancelled - Autopay/recurring mandate revoked, inactive, or cancelled
6. unclassified - Ambiguous, uninterpretable, contradictory, or system/generic error

STRICT OUTPUT RULES:
- Output MUST be valid JSON only. Do NOT include markdown formatting, code blocks, or extra text.
- JSON must contain these exact keys: "category", "confidence", "reasoning".
- "category" MUST be one of: ["insufficient_funds", "card_expired", "card_not_enabled", "risk_block", "mandate_cancelled", "unclassified"].
- "confidence" MUST be a float between 0.0 and 1.0 reflecting genuine uncertainty.
- DO NOT inflate confidence to appear decisive. Prefer confidence < 0.50 and category "unclassified" when input is ambiguous or contradictory.
- "reasoning" MUST be a short string explaining your decision.
"""

import time

def _call_gemini_api(api_key: str, user_text: str) -> str:
    """Calls Google Gemini REST API across available model endpoints with rate-limit retries."""
    candidate_models = ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro", "gemini-flash-latest"]
    last_err = None

    for model in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": f"{SYSTEM_PROMPT}\n\nInput Event:\n{user_text}"}
                    ]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.1
            }
        }
        req_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=req_bytes, headers={"Content-Type": "application/json"}, method="POST")

        # Retry loop for 429 / 503 rate limits / transient outages
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    res_dict = json.loads(resp.read().decode("utf-8"))
                    candidates = res_dict.get("candidates", [])
                    if not candidates:
                        raise ValueError("Empty response candidates from Gemini API.")
                    return candidates[0]["content"]["parts"][0]["text"]
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    last_err = e
                    break  # Try next candidate model
                elif e.code in (429, 503) and attempt < 2:
                    time.sleep(1.5 * (attempt + 1))  # Exponential backoff delay
                    continue
                last_err = e
                raise e
            except Exception as e:
                last_err = e
                raise e

    if last_err:
        raise last_err
    raise RuntimeError("Failed to reach Gemini API model endpoints.")

def _call_anthropic_api(api_key: str, user_text: str) -> str:
    """Calls Anthropic Claude Messages API."""
    url = "https://api.anthropic.com/v1/messages"
    payload = {
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 300,
        "system": SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": f"Classify this failure event:\n{user_text}"}
        ]
    }
    req_bytes = json.dumps(payload).encode("utf-8")
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    req = urllib.request.Request(url, data=req_bytes, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=25) as resp:
        res_dict = json.loads(resp.read().decode("utf-8"))
        content = res_dict.get("content", [])
        if not content:
            raise ValueError("Empty content from Anthropic API.")
        return content[0]["text"]

def _call_openai_api(api_key: str, user_text: str) -> str:
    """Calls OpenAI Chat Completions API."""
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": "gpt-4o-mini",
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Classify this failure event:\n{user_text}"}
        ],
        "response_format": {"type": "json_object"}
    }
    req_bytes = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    req = urllib.request.Request(url, data=req_bytes, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=25) as resp:
        res_dict = json.loads(resp.read().decode("utf-8"))
        choices = res_dict.get("choices", [])
        if not choices:
            raise ValueError("Empty choices from OpenAI API.")
        return choices[0]["message"]["content"]

def classify_by_llm(
    error_code: str = None,
    error_reason: str = None,
    error_description: str = None,
    error_source: str = None,
    error_step: str = None,
    attempt_number: int = 1
) -> Tuple[str, float, str]:
    """
    Classifies an ambiguous payment failure event via LLM fallback.

    NO PII is passed to the LLM.

    Returns:
        tuple[str, float, str]: (category, confidence, reasoning)
    """
    event_context = {
        "error_code": error_code or "NONE",
        "error_reason": error_reason or "NONE",
        "error_description": error_description or "NONE",
        "error_source": error_source or "NONE",
        "error_step": error_step or "NONE",
        "attempt_number": attempt_number
    }
    user_text = json.dumps(event_context, indent=2)

    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()

    raw_response_text = None
    try:
        if gemini_key:
            raw_response_text = _call_gemini_api(gemini_key, user_text)
        elif anthropic_key:
            raw_response_text = _call_anthropic_api(anthropic_key, user_text)
        elif openai_key:
            raw_response_text = _call_openai_api(openai_key, user_text)
        else:
            return ("unclassified", 0.0, "LLM call failed: No API key configured in GEMINI_API_KEY or ANTHROPIC_API_KEY")
    except Exception as e:
        logger.error(f"LLM API call failed: {e}")
        return ("unclassified", 0.0, f"LLM call failed: {str(e)}")

    cleaned_text = raw_response_text.strip()
    if cleaned_text.startswith("```"):
        cleaned_text = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned_text)
        cleaned_text = re.sub(r"\n?```$", "", cleaned_text).strip()

    try:
        data = json.loads(cleaned_text)
    except Exception as e:
        return ("unclassified", 0.0, f"LLM response failed validation: Malformed JSON ({str(e)})")

    if not isinstance(data, dict):
        return ("unclassified", 0.0, "LLM response failed validation: Response is not a JSON object")

    category = data.get("category")
    confidence = data.get("confidence")
    reasoning = data.get("reasoning")

    if category not in VALID_CATEGORIES:
        return ("unclassified", 0.0, f"LLM response failed validation: Invalid category '{category}'")

    try:
        conf_float = float(confidence)
        if conf_float < 0.0 or conf_float > 1.0:
            return ("unclassified", 0.0, f"LLM response failed validation: Confidence {conf_float} out of range [0.0, 1.0]")
    except (TypeError, ValueError):
        return ("unclassified", 0.0, f"LLM response failed validation: Confidence '{confidence}' is not a valid float")

    if not reasoning or not isinstance(reasoning, str) or not reasoning.strip():
        return ("unclassified", 0.0, "LLM response failed validation: Reasoning string is missing or empty")

    return (category, conf_float, str(reasoning).strip())
