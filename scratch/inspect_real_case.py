import json
import sqlite3

def inspect_real_case(subscription_id):
    conn = sqlite3.connect("db/recovery_agent.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    sub = cursor.execute("SELECT * FROM subscriptions WHERE id = ?", (subscription_id,)).fetchone()
    cs = cursor.execute("SELECT * FROM case_state WHERE subscription_id = ?", (subscription_id,)).fetchone()
    fe_list = cursor.execute("SELECT * FROM failure_events WHERE subscription_id = ?", (subscription_id,)).fetchall()
    cl_list = cursor.execute("SELECT c.* FROM classifications c JOIN failure_events fe ON c.failure_event_id = fe.id WHERE fe.subscription_id = ?", (subscription_id,)).fetchall()
    dec_list = cursor.execute("SELECT d.* FROM decisions d JOIN classifications c ON d.classification_id = c.id JOIN failure_events fe ON c.failure_event_id = fe.id WHERE fe.subscription_id = ?", (subscription_id,)).fetchall()
    act_list = cursor.execute("SELECT a.* FROM actions a JOIN decisions d ON a.decision_id = d.id JOIN classifications c ON d.classification_id = c.id JOIN failure_events fe ON c.failure_event_id = fe.id WHERE fe.subscription_id = ?", (subscription_id,)).fetchall()
    audit_list = cursor.execute("SELECT * FROM audit_log WHERE subscription_id = ?", (subscription_id,)).fetchall()

    trail = {
        "subscription": dict(sub) if sub else None,
        "case_state": dict(cs) if cs else None,
        "failure_events": [dict(f) for f in fe_list],
        "classifications": [dict(c) for c in cl_list],
        "decisions": [dict(d) for d in dec_list],
        "actions": [dict(a) for a in act_list],
        "audit_log": [dict(a) for a in audit_list]
    }

    print(json.dumps(trail, indent=2))
    conn.close()

if __name__ == "__main__":
    inspect_real_case("sub_TXDg8j2n1ntNrY")
