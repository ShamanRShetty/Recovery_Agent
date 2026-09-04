import hashlib
import hmac
import json
import sqlite3
import unittest

def verify_math():
    print("=" * 80)
    print("1. BY-HAND HMAC-SHA256 SIGNATURE COMPUTATION VERIFICATION")
    print("=" * 80)
    secret = "my_test_razorpay_secret_key_2026"
    raw_body_bytes = b'{"entity":"event","event":"payment.failed","payload":{"payment":{"entity":{"id":"pay_123"}}}}'

    computed_sig = hmac.new(secret.encode('utf-8'), raw_body_bytes, hashlib.sha256).hexdigest()
    print(f"Secret: {secret}")
    print(f"Raw Body Bytes: {raw_body_bytes}")
    print(f"Computed HMAC-SHA256 Hex Digest: {computed_sig}")

    # Demonstrate difference if re-serialized vs raw body
    reserialized_bytes = json.dumps(json.loads(raw_body_bytes.decode('utf-8'))).encode('utf-8')
    reserialized_sig = hmac.new(secret.encode('utf-8'), reserialized_bytes, hashlib.sha256).hexdigest()
    print(f"Re-serialized Bytes: {reserialized_bytes}")
    print(f"Re-serialized HMAC Hex Digest: {reserialized_sig}")
    print(f"Signatures Match? {computed_sig == reserialized_sig} -> PROVES raw body capture is MANDATORY!")

    print("\n" + "=" * 80)
    print("2. RUNNING UNIT TEST SUITE (19 TESTS)")
    print("=" * 80)
    loader = unittest.TestLoader()
    suite = loader.discover("tests")
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)

    print("\n" + "=" * 80)
    print("3. CHECKING DATABASE FOR INGESTED EVENTS")
    print("=" * 80)
    conn = sqlite3.connect("db/recovery_agent.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    fe_rows = cursor.execute("SELECT id, subscription_id, external_event_id, event_type, error_reason, received_at FROM failure_events ORDER BY id DESC LIMIT 10").fetchall()
    print("Latest Failure Events in DB:")
    for row in fe_rows:
        print(dict(row))

    print("\nTotal Subscriptions:", cursor.execute("SELECT count(*) FROM subscriptions").fetchone()[0])
    print("Total Failure Events:", cursor.execute("SELECT count(*) FROM failure_events").fetchone()[0])
    print("Total Case State Rows:", cursor.execute("SELECT count(*) FROM case_state").fetchone()[0])

    conn.close()

if __name__ == "__main__":
    verify_math()
