# System Architecture — Razorpay Failed Subscription Recovery Agent

> **Core Framing Principle**:
> *This agent classifies failure causes and manages customer-contact/escalation decisions; it does not control or time Razorpay's own retry engine.*

---

## 1. Executive Summary & Core Objective

The Razorpay Failed Subscription Recovery Agent is an AI-assisted, policy-governed backend engine and operational dashboard built to handle failed subscription payment events. It combines a deterministic rule-based classifier, a safe LLM fallback classifier (Google Gemini), a pure policy decision engine, structured action execution, an append-only audit trail, and a 3-screen operational dashboard.

---

## 2. End-to-End Pipeline Architecture

The recovery engine processes failure events through a strict 7-layer pipeline:

```
[ Webhook / Simulation Event ]
              │
              ▼
    1. INGESTION & IDEMPOTENCY (api/webhooks.py & api/routes.py)
              │
              ▼
    2. CLASSIFICATION (classifier/rules.py ──> classifier/llm_fallback.py)
              │
              ▼
    3. POLICY DECISION ENGINE (engine/policy.py)
              │
              ▼
    4. ACTION EXECUTOR (executor/actions.py)
              │
              ▼
    5. IMMUTABLE AUDIT LOGGER (audit/logger.py)
              │
              ▼
    6. CASE STATE MANAGER (engine/case_state.py)
              │
              ▼
    7. DASHBOARD & HUMAN REVIEW (api/routes.py & frontend/)
```

### Layer Details & Module Mapping

1. **Ingestion & Idempotency (`api/webhooks.py`, `api/routes.py`)**:
   - Signature verification using HMAC-SHA256 constant-time check (`api/webhook_security.py`).
   - Idempotency enforced via SQLite `UNIQUE` constraint on `failure_events.external_event_id`.
   - Re-delivered events with identical `external_event_id` return `200 duplicate_ignored`.

2. **Failure Classification (`classifier/rules.py`, `classifier/llm_fallback.py`)**:
   - **Deterministic Rule Engine**: Evaluates error reason and description against regex patterns for 5 standard categories (`card_expired`, `insufficient_funds`, `card_not_enabled`, `risk_block`, `mandate_cancelled`). Returns `(category, 1.0)` on unambiguous match.
   - **LLM Fallback Gating**: Invoked **ONLY** if the rule engine returns `('unclassified', 0.0)`. Calls Google Gemini REST API without customer PII, enforcing strict JSON output validation.

3. **Policy Decision Engine (`engine/policy.py`)**:
   - Pure, side-effect-free function `decide_action(category, confidence, case_state, subscription_status, attempt_number)`.
   - Enforces playbook rules:
     - `CONFIDENCE_THRESHOLD = 0.75`: Low confidence (<0.75) escalates immediately.
     - `risk_block`: Unconditionally escalates (`rb_always_human_review`) without reading `contact_count`.
     - `MAX_CONTACTS = 2`: Hard ceiling on customer contact outreach.

4. **Action Execution (`executor/actions.py`)**:
   - Executes policy decisions (`send_nudge`, `wait`, `escalate`, `stop`).
   - Generates simulated JSON payload structures (`simulated: true`). No live SMS/email credentials required.

5. **Immutable Audit Logging (`audit/logger.py`)**:
   - Writes 3 append-only log entries per processed event into `audit_log` (classification, decision, action).
   - Rows are never modified or deleted.

6. **Case State Persistence (`engine/case_state.py`)**:
   - Tracks `subscription_id`, `contact_count`, `status` (`open`, `recovered`, `escalated`, `stopped`), `last_category`, and `last_updated`.

7. **REST API & Operational Dashboard (`api/routes.py`, `frontend/`)**:
   - FastAPI endpoints: `GET /metrics`, `GET /cases`, `GET /cases/{id}`, `POST /simulate/event`, `POST /cases/{id}/human-review`.
   - 3-screen single-page frontend (KPI Dashboard, Case List, Case Detail with timeline & human review form).

---

## 3. Database Schema (SQLite)

The database schema (`db/schema.sql`) consists of 7 normalized tables with strict foreign key constraints (`PRAGMA foreign_keys = ON;`):

- **`subscriptions`**: `id`, `customer_id`, `plan_amount`, `currency`, `status`, `created_at`
- **`failure_events`**: `id`, `subscription_id`, `external_event_id` (UNIQUE), `event_type`, `error_code`, `error_reason`, `error_description`, `error_source`, `error_step`, `attempt_number`, `raw_payload`, `received_at`
- **`classifications`**: `id`, `failure_event_id`, `category`, `method` (`rule`/`llm`), `confidence`, `llm_reasoning`, `classified_at`
- **`decisions`**: `id`, `classification_id`, `action_type`, `playbook_rule_id`, `decided_at`
- **`actions`**: `id`, `decision_id`, `action_type`, `simulated`, `payload`, `result`, `executed_at`
- **`case_state`**: `subscription_id`, `contact_count`, `status`, `last_category`, `last_updated`
- **`audit_log`**: `id`, `subscription_id`, `event_summary`, `actor`, `timestamp`

---

## 4. Key Security & Compliance Rules

1. **Zero Customer PII Sent to LLM**:
   - Only technical error fields (`error_code`, `error_reason`, `error_description`, `error_source`, `error_step`, `attempt_number`) are passed to Gemini. Names, emails, card numbers, and phone numbers are strictly excluded.
2. **No Automated Subscription Cancellation**:
   - The agent never cancels customer subscriptions. Terminal actions are limited to `stop` (stopping active dunning) or `escalate` (transferring to human review).
3. **Contact Count Ceiling**:
   - `MAX_CONTACTS = 2`: No customer will ever receive more than 2 nudges for a failed subscription.
4. **Risk Block Human Review Guarantee**:
   - All `risk_block` events bypass automated outreach completely and escalate to human review immediately.
