import urllib.request
import urllib.error
import json
import sqlite3

BASE_URL = "http://127.0.0.1:8000"

def post(url, data):
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read())

def verify_live():
    print('=== 5. POST /cases/sub_synth_rsk_1/human-review ===')
    review_payload = {
        'decision': 'approve',
        'note': 'Manual verification complete. Risk block decision validated by compliance officer.'
    }
    code, body = post(f'{BASE_URL}/cases/sub_synth_rsk_1/human-review', review_payload)
    print(f'HTTP Code: {code}')
    print(json.dumps(body, indent=2))

    conn = sqlite3.connect('db/recovery_agent.db')
    cursor = conn.cursor()

    print('\n=== Audit log entries for sub_synth_rsk_1 ===')
    rows = cursor.execute("SELECT id, subscription_id, event_summary, actor, timestamp FROM audit_log WHERE subscription_id = 'sub_synth_rsk_1' ORDER BY id ASC").fetchall()
    for r in rows:
        print(r)

    print('\n=== Phase 1-4 Dataset Integrity Verification ===')
    synth_subs = cursor.execute("SELECT count(*) FROM subscriptions WHERE id LIKE 'sub_synth_%'").fetchone()[0]
    synth_fe = cursor.execute("SELECT count(*) FROM failure_events WHERE subscription_id LIKE 'sub_synth_%'").fetchone()[0]
    synth_cl = cursor.execute("SELECT count(*) FROM classifications c JOIN failure_events fe ON c.failure_event_id = fe.id WHERE fe.subscription_id LIKE 'sub_synth_%'").fetchone()[0]
    synth_dec = cursor.execute("SELECT count(*) FROM decisions d JOIN classifications c ON d.classification_id = c.id JOIN failure_events fe ON c.failure_event_id = fe.id WHERE fe.subscription_id LIKE 'sub_synth_%'").fetchone()[0]
    synth_act = cursor.execute("SELECT count(*) FROM actions a JOIN decisions d ON a.decision_id = d.id JOIN classifications c ON d.classification_id = c.id JOIN failure_events fe ON c.failure_event_id = fe.id WHERE fe.subscription_id LIKE 'sub_synth_%'").fetchone()[0]
    synth_cs = cursor.execute("SELECT count(*) FROM case_state WHERE subscription_id LIKE 'sub_synth_%'").fetchone()[0]

    print(f'Phase 1-4 Subscriptions Count: {synth_subs} (Expected: 28)')
    print(f'Phase 1-4 Failure Events Count: {synth_fe} (Expected: 40)')
    print(f'Phase 1-4 Classifications Count: {synth_cl} (Expected: 40)')
    print(f'Phase 1-4 Decisions Count: {synth_dec} (Expected: 40)')
    print(f'Phase 1-4 Actions Count: {synth_act} (Expected: 40)')
    print(f'Phase 1-4 Case State Count: {synth_cs} (Expected: 28)')

    conn.close()

if __name__ == '__main__':
    verify_live()
