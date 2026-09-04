"""
System Configuration Parameters (Phase 3)
========================================

System-wide thresholds and operational limits for the Failed Subscription Recovery Agent.
"""

# MVP default confidence threshold for acting automatically vs escalating to human review.
# This value will be evaluated in later phases against 0.60 / 0.75 / 0.90 thresholds.
CONFIDENCE_THRESHOLD = 0.75

# The attempt_number threshold at which insufficient_funds triggers a courtesy reminder nudge.
# Attempt 1: native retry proceed (wait).
# Attempt >= REPEATED_FAILURE_THRESHOLD: courtesy reminder (send_nudge).
REPEATED_FAILURE_THRESHOLD = 2

# Enforced hard ceiling for maximum automated customer contacts per subscription recovery case.
MAX_CONTACTS = 2
