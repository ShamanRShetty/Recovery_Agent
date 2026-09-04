/**
 * Razorpay Failed Subscription Recovery Agent - Frontend App
 * Pure JavaScript single-page application interfacing exclusively with FastAPI.
 */

const API_BASE = ''; // Same origin

let currentView = 'kpi';
let selectedCaseId = null;

const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const CATEGORY_NOTES = {
  'card_expired': 'Awaiting Razorpay\'s native retry or email link dispatch',
  'insufficient_funds': 'Awaiting Razorpay\'s native retry cycle',
  'card_not_enabled': 'Online/recurring transactions disabled on card',
  'risk_block': 'High risk score — human escalation',
  'mandate_cancelled': 'Autopay mandate revoked or cancelled',
  'unclassified': 'LLM fallback classification triggered'
};

// Initialize App
document.addEventListener('DOMContentLoaded', () => {
  navigateTo('kpi');
});

/**
 * View Navigation Controller
 */
function navigateTo(viewName, caseId = null) {
  currentView = viewName;
  selectedCaseId = caseId;

  document.querySelectorAll('.view-nav-btn').forEach(btn => btn.classList.remove('is-active'));
  const activeNavBtn = document.getElementById(`nav-${viewName}`);
  if (activeNavBtn) activeNavBtn.classList.add('is-active');

  document.querySelectorAll('.view').forEach(sec => sec.classList.remove('is-active'));

  if (viewName === 'kpi') {
    document.getElementById('kpi-view').classList.add('is-active');
    loadKPIs();
  } else if (viewName === 'cases') {
    document.getElementById('cases-view').classList.add('is-active');
    loadCaseList();
  } else if (viewName === 'detail' && caseId) {
    document.getElementById('detail-view').classList.add('is-active');
    loadCaseDetail(caseId);
  }
}

/**
 * VIEW 1: Load & Render KPI Dashboard
 */
async function loadKPIs() {
  try {
    const res = await fetch(`${API_BASE}/metrics`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    // 1. Escalation rate (count-up)
    const escPct = data.escalation_rate * 100;
    animateNumber(document.getElementById('kpi-escalation-rate'), escPct, { decimals: 1, suffix: '%' });

    // 2. Contacts avoided
    animateNumber(document.getElementById('kpi-contacts-avoided'), data.contacts_avoided, { decimals: 0 });

    // 3. Avg contacts per resolved case
    animateNumber(document.getElementById('kpi-avg-contacts'), data.avg_contacts_per_resolved_case, { decimals: 1 });

    // 4. False decision count (honest limitation state)
    const falseDecElem = document.getElementById('kpi-false-decisions');
    if (data.false_decision_count === null || data.false_decision_count === undefined) {
      falseDecElem.textContent = 'Not yet measured — requires manual case labeling';
      falseDecElem.className = 'kpi-tile-value-muted';
    } else {
      falseDecElem.textContent = data.false_decision_count;
      falseDecElem.className = 'kpi-tile-value';
    }

    // 5. Recovery rate by category
    const categoryListContainer = document.getElementById('kpi-category-list');
    categoryListContainer.innerHTML = '';

    const rates = data.recovery_rate_by_category || {};
    const sortedCategories = Object.keys(rates).sort((a, b) => (rates[b] || 0) - (rates[a] || 0));

    if (sortedCategories.length === 0) {
      categoryListContainer.innerHTML = '<div class="empty-note">No category metrics available.</div>';
      return;
    }

    sortedCategories.forEach(cat => {
      const rateVal = rates[cat] || 0;
      const ratePctNum = (rateVal * 100).toFixed(1);
      const note = CATEGORY_NOTES[cat] || 'Category performance metric';

      const barRow = document.createElement('div');
      barRow.className = 'category-row';
      barRow.innerHTML = `
        <div class="category-row-top">
          <div>
            <span class="category-name">${escapeHtml(formatCategoryLabel(cat))}</span>
            <span class="category-note">${escapeHtml(note)}</span>
          </div>
          <span class="category-rate">${ratePctNum}%</span>
        </div>
        <div class="category-track">
          <div class="category-fill" data-width="${Math.max(rateVal * 100, 2)}"></div>
        </div>
      `;
      categoryListContainer.appendChild(barRow);
    });

    // Animate bar fills in on next frame
    requestAnimationFrame(() => {
      categoryListContainer.querySelectorAll('.category-fill').forEach(fill => {
        fill.style.width = `${fill.dataset.width}%`;
      });
    });

  } catch (err) {
    console.error('Error fetching metrics:', err);
    document.getElementById('kpi-escalation-rate').textContent = 'Error';
    document.getElementById('kpi-category-list').innerHTML = `<div class="empty-note is-error">Failed to load metrics from server.</div>`;
  }
}

/**
 * VIEW 2: Load & Render Case List
 */
async function loadCaseList() {
  const statusFilter = document.getElementById('filter-status').value;
  const categoryFilter = document.getElementById('filter-category').value;

  const clearBtn = document.getElementById('clear-filters-btn');
  if (statusFilter || categoryFilter) {
    clearBtn.classList.remove('hidden');
  } else {
    clearBtn.classList.add('hidden');
  }

  let url = `${API_BASE}/cases`;
  const params = new URLSearchParams();
  if (statusFilter) params.append('status', statusFilter);
  if (categoryFilter) params.append('category', categoryFilter);

  if (params.toString()) {
    url += `?${params.toString()}`;
  }

  const tbody = document.getElementById('cases-table-body');
  tbody.innerHTML = '<tr><td colspan="6" class="empty-note">Loading cases...</td></tr>';

  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const cases = await res.json();

    const countIndicator = document.getElementById('case-count-indicator');
    if (countIndicator) {
      countIndicator.textContent = `Showing ${cases.length} case${cases.length === 1 ? '' : 's'}`;
    }

    tbody.innerHTML = '';
    if (cases.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="6" class="empty-note">
            <p>No matching recovery cases found for the selected filters.</p>
            <button class="btn btn--ghost" style="margin-top: 0.75rem;" onclick="resetFilters()">Reset filters</button>
          </td>
        </tr>
      `;
      return;
    }

    cases.forEach(item => {
      const tr = document.createElement('tr');
      const formattedDate = item.last_updated ? formatIsoDate(item.last_updated) : '--';
      const statusBadge = getStatusBadge(item.status);

      tr.innerHTML = `
        <td>
          <a href="#" class="link mono" onclick="event.preventDefault(); navigateTo('detail', '${escapeHtml(item.subscription_id)}')">
            ${escapeHtml(item.subscription_id)}
          </a>
        </td>
        <td><span class="category-chip">${escapeHtml(formatCategoryLabel(item.last_category || 'unclassified'))}</span></td>
        <td>${statusBadge}</td>
        <td><span class="mono">${item.contact_count}</span></td>
        <td><span class="mono">${formattedDate}</span></td>
        <td class="text-right">
          <button class="btn btn--ghost" onclick="navigateTo('detail', '${escapeHtml(item.subscription_id)}')">View trail</button>
        </td>
      `;
      tbody.appendChild(tr);
    });

  } catch (err) {
    console.error('Error fetching cases:', err);
    tbody.innerHTML = `<tr><td colspan="6" class="empty-note is-error">Failed to load case list from server.</td></tr>`;
  }
}

function applyFilters() {
  loadCaseList();
}

function resetFilters() {
  document.getElementById('filter-status').value = '';
  document.getElementById('filter-category').value = '';
  loadCaseList();
}

function toggleSimulateForm() {
  const form = document.getElementById('simulate-event-form');
  const icon = document.getElementById('sim-toggle-icon');
  if (form) form.classList.toggle('hidden');
  if (icon) icon.classList.toggle('is-open');
}

/**
 * Handle Simulate Event Form Submission
 */
async function handleSimulateEvent(event) {
  event.preventDefault();
  const submitBtn = document.getElementById('sim-submit-btn');
  const statusMsg = document.getElementById('sim-status-msg');

  const subId = document.getElementById('sim-sub-id').value.trim();
  const eventType = document.getElementById('sim-event-type').value.trim();
  const errorCode = document.getElementById('sim-error-code').value.trim() || null;
  const errorReason = document.getElementById('sim-error-reason').value.trim() || null;
  const errorDesc = document.getElementById('sim-error-desc').value.trim() || null;

  if (!subId) {
    statusMsg.className = 'status-msg error';
    statusMsg.textContent = 'Subscription ID is required.';
    return;
  }

  submitBtn.disabled = true;
  statusMsg.className = 'status-msg';
  statusMsg.textContent = 'Processing event simulation through pipeline...';

  try {
    const payload = {
      subscription_id: subId,
      event_type: eventType,
      error_code: errorCode,
      error_reason: errorReason,
      error_description: errorDesc
    };

    const res = await fetch(`${API_BASE}/simulate/event`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || `HTTP ${res.status}`);
    }

    const result = await res.json();
    statusMsg.className = 'status-msg success';
    statusMsg.textContent = `Event processed for ${subId}. Category: ${result.classification?.category || 'N/A'}, action: ${result.decision?.action_type || 'N/A'}`;

    loadCaseList();

    document.getElementById('sim-error-code').value = '';
    document.getElementById('sim-error-reason').value = '';
    document.getElementById('sim-error-desc').value = '';

  } catch (err) {
    console.error('Simulate event error:', err);
    statusMsg.className = 'status-msg error';
    statusMsg.textContent = `Simulation failed: ${err.message}`;
  } finally {
    submitBtn.disabled = false;
  }
}

/**
 * VIEW 3: Load & Render Case Detail (Vertical Timeline)
 */
async function loadCaseDetail(caseId) {
  const headerContent = document.getElementById('detail-header-content');
  const humanReviewBox = document.getElementById('human-review-box');
  const timelineContainer = document.getElementById('timeline-container');

  headerContent.innerHTML = '<div class="empty-note">Loading case details...</div>';
  timelineContainer.innerHTML = '<div class="empty-note">Loading timeline...</div>';
  humanReviewBox.classList.add('hidden');

  try {
    const res = await fetch(`${API_BASE}/cases/${encodeURIComponent(caseId)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const sub = data.subscription || {};
    const cs = data.case_state || {};
    const auditLogs = data.audit_log || [];

    const statusBadge = getStatusBadge(cs.status || sub.status || 'unknown');
    const categoryName = cs.last_category || 'unclassified';
    const amountStr = `${sub.currency || 'INR'} ${(sub.plan_amount || 0).toLocaleString()}`;
    const subId = sub.id || caseId;

    headerContent.innerHTML = `
      <div class="case-head-top">
        <div class="case-id">
          <span class="mono">${escapeHtml(subId)}</span>
          <button class="copy-btn" id="copy-sub-id-btn" title="Copy subscription ID" onclick="copyToClipboard('${escapeHtml(subId)}', this)" aria-label="Copy subscription ID">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
          </button>
        </div>
        <div class="case-badges">
          <span class="category-chip">${escapeHtml(formatCategoryLabel(categoryName))}</span>
          ${statusBadge}
        </div>
      </div>
      <div class="case-meta">
        <div>
          <div class="case-meta-label">Customer ID</div>
          <div class="case-meta-value mono">${escapeHtml(sub.customer_id || 'N/A')}</div>
        </div>
        <div>
          <div class="case-meta-label">Plan amount</div>
          <div class="case-meta-value">${escapeHtml(amountStr)}</div>
        </div>
        <div>
          <div class="case-meta-label">Customer contacts</div>
          <div class="case-meta-value">${cs.contact_count ?? 0}</div>
        </div>
      </div>
    `;

    if (cs.status === 'escalated') {
      humanReviewBox.classList.remove('hidden');
      document.getElementById('hr-note').value = '';
      document.getElementById('hr-status-msg').textContent = '';
    } else {
      humanReviewBox.classList.add('hidden');
    }

    // Render vertical timeline
    timelineContainer.innerHTML = '';

    if (auditLogs.length === 0) {
      timelineContainer.innerHTML = '<div class="empty-note">No audit log entries found for this case.</div>';
      return;
    }

    auditLogs.forEach((entry, index) => {
      const isHuman = entry.actor === 'human';
      const nodeStateClass = isHuman ? 'is-human' : (index === auditLogs.length - 1 ? '' : 'is-past');
      const actorTagClass = isHuman ? 'status status--open' : 'category-chip';
      const timeStr = formatIsoDate(entry.timestamp);

      let stageTitle = `Step ${index + 1}: Audit event`;
      const summaryLower = entry.event_summary.toLowerCase();

      let ruleChipHtml = '';
      let actionChipHtml = '';

      if (summaryLower.includes('classified') || summaryLower.includes('classification')) {
        stageTitle = `Stage 1 · Failure classification`;
        const isLlm = summaryLower.includes('via llm');
        ruleChipHtml = `<span class="pill-mono">${isLlm ? 'method: llm_fallback' : 'method: rule_engine'}</span>`;
      } else if (summaryLower.includes('policy') || summaryLower.includes('decided action') || summaryLower.includes('decision')) {
        stageTitle = `Stage 2 · Policy decision`;
        const matchRule = entry.event_summary.match(/Playbook Rule:\s*'([^']+)'/i);
        if (matchRule && matchRule[1]) {
          const ruleId = matchRule[1];
          ruleChipHtml = `
            <span class="pill-mono">
              rule: ${escapeHtml(ruleId)}
              <button class="copy-btn" title="Copy rule ID" onclick="copyToClipboard('${escapeHtml(ruleId)}', this)" aria-label="Copy playbook rule ID">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
              </button>
            </span>
          `;
        }
      } else if (summaryLower.includes('action executed') || summaryLower.includes('executed action')) {
        stageTitle = `Stage 3 · Action execution`;
        const isSimulated = summaryLower.includes('simulated');
        actionChipHtml = `<span class="pill-mono ${isSimulated ? 'is-simulated' : 'is-live'}">${isSimulated ? 'action: simulated' : 'action: live'}</span>`;
      } else if (summaryLower.includes('human review') || isHuman) {
        stageTitle = `Human override / review`;
      } else if (summaryLower.includes('failure event recorded') || summaryLower.includes('received')) {
        stageTitle = `Stage 0 · Webhook event received`;
      }

      const nodeDiv = document.createElement('div');
      nodeDiv.className = `timeline-node ${nodeStateClass}`;
      nodeDiv.style.animationDelay = prefersReducedMotion ? '0s' : `${Math.min(index * 70, 500)}ms`;
      nodeDiv.innerHTML = `
        <div class="timeline-dot"></div>
        <div class="timeline-card">
          <div class="timeline-card-head">
            <span class="timeline-stage">${escapeHtml(stageTitle)}</span>
            <span class="timeline-time mono">${timeStr}</span>
          </div>
          <div class="timeline-tags">
            <span class="${actorTagClass}">${escapeHtml(entry.actor || 'system')}</span>
            ${ruleChipHtml}
            ${actionChipHtml}
          </div>
          <div class="timeline-text">${escapeHtml(entry.event_summary)}</div>
        </div>
      `;
      timelineContainer.appendChild(nodeDiv);
    });

  } catch (err) {
    console.error('Error fetching case detail:', err);
    headerContent.innerHTML = `<div class="empty-note is-error">Failed to load case details.</div>`;
    timelineContainer.innerHTML = `<div class="empty-note is-error">Failed to load timeline.</div>`;
  }
}

/**
 * Handle Human Review Form Submission
 */
async function handleHumanReview(event) {
  event.preventDefault();
  if (!selectedCaseId) return;

  const submitBtn = document.getElementById('hr-submit-btn');
  const statusMsg = document.getElementById('hr-status-msg');

  const decision = document.getElementById('hr-decision').value;
  const note = document.getElementById('hr-note').value.trim();

  submitBtn.disabled = true;
  statusMsg.className = 'status-msg';
  statusMsg.textContent = 'Submitting human review...';

  try {
    const res = await fetch(`${API_BASE}/cases/${encodeURIComponent(selectedCaseId)}/human-review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision, note })
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || `HTTP ${res.status}`);
    }

    statusMsg.className = 'status-msg success';
    statusMsg.textContent = 'Human review submitted successfully.';

    await loadCaseDetail(selectedCaseId);

  } catch (err) {
    console.error('Human review submission error:', err);
    statusMsg.className = 'status-msg error';
    statusMsg.textContent = `Submission failed: ${err.message}`;
  } finally {
    submitBtn.disabled = false;
  }
}

/**
 * Copy to Clipboard Helper
 */
function copyToClipboard(text, btnElement) {
  if (!navigator.clipboard) {
    fallbackCopyTextToClipboard(text);
    return;
  }
  navigator.clipboard.writeText(text).then(() => {
    flashCopySuccess(btnElement);
  }).catch(err => {
    console.error('Copy to clipboard failed:', err);
  });
}

function flashCopySuccess(btnElement) {
  if (!btnElement) return;
  const originalSvg = btnElement.innerHTML;
  btnElement.classList.add('copied');
  btnElement.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>';
  setTimeout(() => {
    btnElement.innerHTML = originalSvg;
    btnElement.classList.remove('copied');
  }, 1400);
}

function fallbackCopyTextToClipboard(text) {
  const textArea = document.createElement("textarea");
  textArea.value = text;
  textArea.style.position = "fixed";
  document.body.appendChild(textArea);
  textArea.focus();
  textArea.select();
  try {
    document.execCommand('copy');
  } catch (err) {
    console.error('Fallback copy error', err);
  }
  document.body.removeChild(textArea);
}

/**
 * Animated number count-up. Respects prefers-reduced-motion.
 */
function animateNumber(el, target, { decimals = 0, suffix = '' } = {}) {
  if (!el) return;
  const isValidNumber = typeof target === 'number' && !isNaN(target);
  if (!isValidNumber) {
    el.textContent = '--';
    return;
  }

  if (prefersReducedMotion) {
    el.textContent = `${target.toFixed(decimals)}${suffix}`;
    return;
  }

  const duration = 700;
  const start = performance.now();

  function tick(now) {
    const progress = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
    const current = target * eased;
    el.textContent = `${current.toFixed(decimals)}${suffix}`;
    if (progress < 1) {
      requestAnimationFrame(tick);
    } else {
      el.textContent = `${target.toFixed(decimals)}${suffix}`;
    }
  }
  requestAnimationFrame(tick);
}

/**
 * Utility Functions
 */
function getStatusBadge(status) {
  const s = (status || 'unknown').toLowerCase();
  let modifierClass = 'status--stopped';
  let label = capitalize(s);

  if (s === 'recovered') {
    modifierClass = 'status--recovered';
  } else if (s === 'escalated') {
    modifierClass = 'status--escalated';
  } else if (s === 'open') {
    modifierClass = 'status--open';
    label = 'Open — awaiting native retry';
  }

  return `<span class="status ${modifierClass}"><span class="status-dot"></span>${escapeHtml(label)}</span>`;
}

function formatCategoryLabel(cat) {
  if (!cat) return 'Unclassified';
  return String(cat)
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function capitalize(str) {
  if (!str) return str;
  return str.charAt(0).toUpperCase() + str.slice(1);
}

function formatIsoDate(isoStr) {
  if (!isoStr) return '--';
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return isoStr;
    return d.toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    });
  } catch (e) {
    return isoStr;
  }
}

function escapeHtml(str) {
  if (!str && str !== 0) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}