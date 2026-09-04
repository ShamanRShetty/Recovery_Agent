# Confidence Threshold Evaluation & Analysis (Phase 7)

## Overview
The Failed Subscription Recovery Agent enforces a policy decision boundary based on classification confidence. When a payment failure event cannot be classified deterministically by the rule engine (`category='unclassified'`, `confidence=0.0`), the system invokes the LLM fallback classifier (`classifier/llm_fallback.py`).

The policy decision engine evaluates the resulting classification against `CONFIDENCE_THRESHOLD`:
- **If `confidence >= CONFIDENCE_THRESHOLD`**: The system triggers automated policy actions (e.g. `send_nudge` or `wait`).
- **If `confidence < CONFIDENCE_THRESHOLD`**: The system escalates the case to human review (`action='escalate'`, `playbook_rule_id='low_confidence_escalation'`).

---

## Why 0.75 is the MVP Default

`CONFIDENCE_THRESHOLD = 0.75` was established in `config.py` as an MVP default operating point for the following architectural reasons:

1. **Risk Mitigation against False Positives**: In financial subscription recovery, sending an incorrect automated outreach message (e.g., instructing a customer to change their card when their balance was simply low) erodes customer trust and increases churn.
2. **Safe Fallback to Human Review**: A threshold of 0.75 ensures that uncertain LLM classifications (confidence < 0.75) are safely routed to human operators without taking unverified automated actions.
3. **Operational Balance**: 0.75 strikes a balance between automated recovery coverage and risk avoidance before a gold-standard human-labeled dataset is collected.

---

## Offline Threshold Evaluation Methodology

`scripts/evaluate_thresholds.py` re-runs `classify_by_llm()` against the 9 deliberately ambiguous synthetic failure events created in Phase 1:
- **3 Vague Events**: Plausibly classifiable despite non-standard wording (e.g., issuer bank validation decline).
- **3 Uninterpretable Events**: Generic or missing error messages (e.g., "transaction could not be completed").
- **3 Contradictory Events**: Multi-cause or conflicting error descriptions (e.g., "Card expired and insufficient balance").

### Threshold Impact Analysis:
- **0.60 (Aggressive)**: Lowers the bar for automation, capturing more vague events automatically but increasing risk of false positive actions on ambiguous inputs.
- **0.75 (MVP Default)**: Requires strong model certainty before taking automated action. Vague/contradictory events fall below 0.75 and safely escalate.
- **0.90 (Conservative)**: Escalates almost all LLM outputs to human review unless the model returns near-absolute certainty.

---

## Verification & Execution

To re-run the threshold evaluation locally:

```bash
python scripts/evaluate_thresholds.py
```
