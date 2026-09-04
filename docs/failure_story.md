# Architecture Failure & Recovery Story (Hackathon Pitch Defense)

> **Instructions for Pitch Presenter**:
> *Failure Recovery is an explicit judging criterion for this hackathon.*
> Use the template below to draft your personal 1-minute narrative for the video pitch.
> Select one of the 4 candidate build moments from our actual engineering trajectory listed below, fill in your personal reflections, and use it during your demo video recording.

---

## Pitch Template: Technical Failure & Recovery

### 1. What Broke
*[Describe the exact bug, breaking state, or unexpected failure encountered during the build]*

### 2. How I Noticed
*[Describe the exact test failure, webhook rejection log, HTTP status error, or diagnostic symptom that surfaced the issue]*

### 3. What I Tried First (and why it didn't work)
*[Describe your initial hypothesis or naive fix, and explain technically why it failed or created side effects]*

### 4. What Actually Fixed It
*[Explain the root cause fix, architectural guardrail, or code change that permanently resolved the issue]*

### 5. What I'd Do Differently
*[Share a 1-sentence engineering takeaway regarding system design, layer separation, or test-driven validation]*

---

## Real Candidate Technical Failure Moments from Build History

Select ONE of these four real engineering challenges encountered during Phases 0–9 to frame your pitch story:

### Candidate A: Webhook HMAC Signature Mismatch (Phase 6)
- **What Broke**: Real Razorpay webhooks were rejected with `400 Bad Request` ("Invalid webhook signature") despite using the correct secret key.
- **Root Cause**: The webhook handler initially parsed the JSON body into a dictionary before verification, then re-serialized it back to a string with `json.dumps()`. Re-serialization altered whitespace formatting and key ordering, changing the computed HMAC-SHA256 digest.
- **The Fix**: Modified `api/webhooks.py` to capture `raw_body = await request.body()` directly from the incoming HTTP stream BEFORE any JSON parsing, passing raw bytes to constant-time HMAC verification (`hmac.compare_digest`).

### Candidate B: SQLite Foreign Key Constraints on Teardown (Phase 0/9)
- **What Broke**: Database re-initialization scripts failed with `sqlite3.IntegrityError: FOREIGN KEY constraint failed` when resetting tables for testing.
- **Root Cause**: SQLite foreign key enforcement was explicitly enabled (`PRAGMA foreign_keys = ON;`), but table deletion scripts attempted to delete `subscriptions` or `failure_events` before clearing dependent child tables (`classifications`, `decisions`, `actions`, `case_state`, `audit_log`).
- **The Fix**: Reordered deletion scripts in `scripts/generate_synthetic.py` and `scripts/demo_seed.py` to purge child tables in exact reverse dependency order before clearing parent records, ensuring 100% relational integrity.

### Candidate C: Ungated LLM Fallback Calls (Phase 7)
- **What Broke**: Early orchestrator tests attempted to invoke Google Gemini on every failure event, wasting API quota and introducing latency on deterministic events.
- **Root Cause**: The orchestrator pipeline lacked strict gating between the deterministic rule engine and the LLM fallback layer.
- **The Fix**: Enforced strict architectural gating in `pipeline/process_event.py`: `classify_by_llm()` is called ONLY if `classify_by_rules()` returns `('unclassified', 0.0)`. Confident rule matches (`1.0`) bypass the LLM completely.

### Candidate D: Causal Overstatement & Terminology Framing (Phase 5/8)
- **What Broke**: Initial UI designs displayed "Total Amount Recovered" as a hero metric, which overstated the recovery agent's causal contribution by counting native bank retries as agent recoveries.
- **Root Cause**: Failure to separate the agent's active contact interventions (e.g. dunning email for expired cards) from Razorpay's passive native retries (e.g. insufficient funds retries).
- **The Fix**: Removed "Amount Recovered" hero metrics from the dashboard, updated status copy to explicitly state `"open (awaiting Razorpay's native retry)"`, and restricted recovered metrics strictly to cases where the agent's policy rules reached terminal resolution.
