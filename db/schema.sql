-- PRAGMA foreign_keys = ON; -- Enforced per-connection in application code

-- 1. Subscriptions Table
CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    plan_amount INTEGER NOT NULL CHECK (plan_amount > 0),
    currency TEXT NOT NULL DEFAULT 'INR',
    status TEXT NOT NULL CHECK (status IN ('active','pending','halted','cancelled')) DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- 2. Failure Events Table
CREATE TABLE IF NOT EXISTS failure_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id TEXT NOT NULL REFERENCES subscriptions(id),
    external_event_id TEXT NOT NULL UNIQUE, -- webhook idempotency key
    event_type TEXT NOT NULL CHECK (event_type IN ('payment.failed','subscription.pending','subscription.halted','subscription.activated','subscription.cancelled')),
    error_code TEXT,
    error_reason TEXT,
    error_description TEXT,
    error_source TEXT,
    error_step TEXT,
    attempt_number INTEGER NOT NULL DEFAULT 1 CHECK (attempt_number > 0),
    raw_payload TEXT, -- full original JSON payload for audit completeness
    received_at TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- 3. Classifications Table
CREATE TABLE IF NOT EXISTS classifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    failure_event_id INTEGER NOT NULL REFERENCES failure_events(id),
    category TEXT NOT NULL CHECK (category IN ('insufficient_funds','card_expired','card_not_enabled','risk_block','mandate_cancelled','unclassified')),
    method TEXT NOT NULL CHECK (method IN ('rule','llm')),
    confidence REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    llm_reasoning TEXT, -- nullable, only populated when method = 'llm'
    classified_at TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- 4. Decisions Table
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    classification_id INTEGER NOT NULL REFERENCES classifications(id),
    action_type TEXT NOT NULL CHECK (action_type IN ('send_nudge','wait','escalate','stop')),
    playbook_rule_id TEXT NOT NULL, -- traceability: which playbook rule fired
    decided_at TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- 5. Actions Table
CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id INTEGER NOT NULL REFERENCES decisions(id),
    action_type TEXT NOT NULL,
    simulated INTEGER NOT NULL CHECK (simulated IN (0,1)),
    payload TEXT, -- JSON describing what was "sent" or called
    result TEXT NOT NULL CHECK (result IN ('success','failed','no_op')),
    executed_at TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- 6. Case State Table
CREATE TABLE IF NOT EXISTS case_state (
    subscription_id TEXT PRIMARY KEY REFERENCES subscriptions(id),
    contact_count INTEGER NOT NULL DEFAULT 0 CHECK (contact_count >= 0 AND contact_count <= 2),
    status TEXT NOT NULL CHECK (status IN ('open','recovered','escalated','stopped')) DEFAULT 'open',
    last_category TEXT,
    last_updated TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- 7. Audit Log Table
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id TEXT NOT NULL REFERENCES subscriptions(id),
    event_summary TEXT NOT NULL,
    actor TEXT NOT NULL CHECK (actor IN ('system','llm','human')),
    timestamp TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- Indexes Required
CREATE INDEX IF NOT EXISTS idx_failure_events_subscription_id ON failure_events(subscription_id);
CREATE INDEX IF NOT EXISTS idx_classifications_failure_event_id ON classifications(failure_event_id);
CREATE INDEX IF NOT EXISTS idx_decisions_classification_id ON decisions(classification_id);
CREATE INDEX IF NOT EXISTS idx_actions_decision_id ON actions(decision_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_subscription_id ON audit_log(subscription_id);
