# AI-Assisted Failed Subscription Recovery Agent for Razorpay

An intelligent, policy-governed recovery agent and operational dashboard for managing Razorpay subscription payment failures. The system automates failure classification using deterministic rules with a safe Google Gemini LLM fallback, enforces strict customer-contact compliance ceilings ($2$ contacts max), logs immutable audit trails, and provides a 3-screen operational dashboard for human review and event simulation.

> **CRITICAL DISCLOSURE & SYSTEM FRAMING**:
> **This agent classifies failure causes and manages customer-contact/escalation decisions; it does not control or time Razorpay's own retry engine.**

---

## Quickstart (Run Locally in Minutes)

Follow these exact copy-pasteable commands to initialize the database, seed synthetic data, process all recovery lifecycles, and launch the server:

### 1. Clone & Set Up Environment
```bash
git clone https://github.com/your-username/razorpay-recovery-agent.git
cd razorpay-recovery-agent

# Create and activate virtual environment
python -m venv venv
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
# source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create environment configuration
cp .env.example .env
```
*(Optional: Open `.env` and set `GEMINI_API_KEY=your_key` to test live LLM fallback classification. The system runs fully without an API key using pure rule classification).*

### 2. Reset & Seed Demo Environment (Single Command)
```bash
python scripts/demo_seed.py
```
This command initializes the SQLite schema (`db/recovery_agent.db`), seeds 40 synthetic events across 23 subscriptions, processes all events through the orchestrator pipeline, and prints two recommended case IDs for demoing (`card_expired` recovered case and `risk_block` escalated case).

### 3. Launch Web Server & Dashboard
```bash
python -m uvicorn api.main:app --port 8000
```
Open your browser to: **`http://127.0.0.1:8000/`**

---

## Architecture at a Glance

The recovery engine operates as a strict 7-layer pipeline:

$$\text{Event Ingestion} \longrightarrow \text{Classification} \longrightarrow \text{Policy Decision} \longrightarrow \text{Action Execution} \longrightarrow \text{Audit Logging} \longrightarrow \text{Case State} \longrightarrow \text{Dashboard}$$

For complete architectural details, module maps, and database schemas, see **[`docs/architecture.md`](docs/architecture.md)**.

---

## What's Real vs. Simulated

| Component | Status | Implementation Details |
| :--- | :---: | :--- |
| **Real Razorpay Webhooks** | **YES** | Signature-verified (`X-Razorpay-Signature`) and idempotent (`X-Razorpay-Event-Id`) at `/webhooks/razorpay`. |
| **Real LLM Classification** | **YES** | Google Gemini REST API invoked safely when rule classifier returns `('unclassified', 0.0)`. |
| **Real Customer Outreach (Email/SMS)** | **NO** | **Simulated only**. Actions produce structured JSON payloads (`simulated: true`) logged to audit trail. |
| **Real Razorpay Retry Schedule Control** | **NO** | **Not possible**. Retry timing is controlled natively by Razorpay's billing engine. |

---

## Verification & Documentation Links

- **Validation Report**: See **[`docs/validation_report.md`](docs/validation_report.md)** for full pass/fail evidence across all 37 unit/integration tests and documented technical limitations.
- **Failure Recovery Story**: See **[`docs/failure_story.md`](docs/failure_story.md)** for pitch video defense and candidate build challenges.
