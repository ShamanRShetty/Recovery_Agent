# Hardening Audit Findings Report

This report documents the robustness audit performed on the Razorpay Failed Subscription Recovery Agent codebase before live pitch demos.

## Summary of Findings by Risk Level

| Risk Level | Count | Focus Areas |
| :--- | :---: | :--- |
| **HIGH** | 3 | Blank subscription ID insertion, malformed webhook JSON crash, concurrent simulation race condition |
| **MEDIUM** | 2 | Human review allowed on non-escalated cases, incomplete KPI dashboard offline error states |
| **LOW** | 2 | HTML tag mismatch in case list error handler, un-disabled form fields during submission |
| **TOTAL** | **7** | |

---

## Detailed Findings

### Finding #1: `POST /simulate/event` accepts blank or whitespace `subscription_id`
* **Location**: `api/routes.py` (`SimulateEventRequest` Pydantic model & `simulate_event` endpoint)
* **Current behavior**: Submitting `POST /simulate/event` with `subscription_id=""` or `"   "` accepts the payload (`200 OK`) and inserts a blank subscription record into the database with `id=""` and `customer_id="cust_sim_"`. This creates corrupt case listings with empty table rows in the frontend UI.
* **Risk to demo**: **HIGH**
* **Proposed fix**: Add string validation (`min_length=1`, `strip_whitespace=True`) to `subscription_id` in `SimulateEventRequest` schema to reject empty/whitespace IDs with `422 Unprocessable Entity`.

### Finding #2: Human review form action allowed on non-escalated cases
* **Location**: `api/routes.py` (`human_review_case` endpoint)
* **Current behavior**: Calling `POST /cases/{id}/human-review` on a case with status `'open'`, `'recovered'`, or `'stopped'` succeeds (`200 OK`) and updates the case state status.
* **Risk to demo**: **MEDIUM**
* **Proposed fix**: Add a status check in `human_review_case` endpoint to verify that `case_state.status == 'escalated'` before accepting review actions, returning `HTTP 400 Bad Request` if the case is not escalated.

### Finding #3: Uncaught 500 Server Error on malformed non-object JSON webhook payloads
* **Location**: `api/webhook_translator.py` (`translate_razorpay_payload` function) & `api/webhooks.py`
* **Current behavior**: Sending a well-signed webhook request where the root JSON is a list (`[1, 2, 3]`), string, integer, or null causes `translate_razorpay_payload` to throw an uncaught `AttributeError: 'list' object has no attribute 'get'`, returning `HTTP 500 Internal Server Error` with stack trace.
* **Risk to demo**: **HIGH**
* **Proposed fix**: Add a type check in `translate_razorpay_payload` to verify `payload_json` is a dict. Return `HTTP 400 Bad Request` with `"Malformed webhook payload structure: root JSON must be an object"` if not a dictionary.

### Finding #4: Concurrent simulation requests for new subscription produce 500 Internal Server Error
* **Location**: `api/routes.py` (`simulate_event` endpoint)
* **Current behavior**: Sending two near-simultaneous `POST /simulate/event` requests for a non-existent subscription ID causes a race condition: both requests attempt to `INSERT INTO subscriptions`, triggering an uncaught `sqlite3.IntegrityError: UNIQUE constraint failed: subscriptions.id` on the second request (`HTTP 500 Internal Server Error`).
* **Risk to demo**: **HIGH**
* **Proposed fix**: Wrap the subscription `INSERT` in a `try-except sqlite3.IntegrityError` block or use `INSERT OR IGNORE INTO subscriptions` so concurrent simulations for new IDs succeed gracefully.

### Finding #5: HTML closing tag mismatch in frontend case list error rendering
* **Location**: `frontend/app.js` (`loadCaseList` function)
* **Current behavior**: When `loadCaseList` fails to fetch cases from backend, it sets `tbody.innerHTML = '<tr><td colspan="6" class="empty-note is-error">Failed to load case list from server.</div>'`. The opening tag is `<td>` but closing tag is `</div>`.
* **Risk to demo**: **LOW**
* **Proposed fix**: Fix closing tag to `</td></tr>` in `app.js`.

### Finding #6: Incomplete error state on KPI Dashboard tiles when API is unreachable
* **Location**: `frontend/app.js` (`loadKPIs` function)
* **Current behavior**: If the backend is down, `loadKPIs` catches the network error, sets `kpi-escalation-rate` to `"Error"` and shows an error in `kpi-category-list`, but leaves `kpi-contacts-avoided` and `kpi-avg-contacts` displaying `--` indefinitely.
* **Risk to demo**: **MEDIUM**
* **Proposed fix**: Set `kpi-contacts-avoided` and `kpi-avg-contacts` to `"Error"` / `"N/A"` inside the catch block in `loadKPIs` for unified error reporting across all KPI tiles.

### Finding #7: Input fields remain interactive during active form submission
* **Location**: `frontend/app.js` & `frontend/index.html` (`simulate-event-form` & `human-review-form`)
* **Current behavior**: During event simulation (which takes 1-2s if LLM fallback triggers), only the submit button is disabled. Input fields remain editable and interactive, which could lead to accidental secondary edits or clicks.
* **Risk to demo**: **LOW**
* **Proposed fix**: Disable all input and select elements in the form while a request is in-flight, re-enabling them in the `finally` block.
