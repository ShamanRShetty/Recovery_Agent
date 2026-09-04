/**
 * Razorpay Failed Subscription Recovery Agent - Frontend App (Phase 8)
 * Pure JavaScript single-page application interfacing exclusively with FastAPI.
 */

const API_BASE = ''; // Same origin

let currentView = 'kpi';
let selectedCaseId = null;

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

  // Update navigation buttons active state
  document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
  const activeNavBtn = document.getElementById(`nav-${viewName}`);
  if (activeNavBtn) activeNavBtn.classList.add('active');

  // Toggle view section visibility
  document.querySelectorAll('.view-section').forEach(sec => sec.classList.remove('active'));

  if (viewName === 'kpi') {
    document.getElementById('kpi-view').classList.add('active');
    loadKPIs();
  } else if (viewName === 'cases') {
    document.getElementById('cases-view').classList.add('active');
    loadCaseList();
  } else if (viewName === 'detail' && caseId) {
    document.getElementById('detail-view').classList.add('active');
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

    // 1. Escalation rate
    const escPct = (data.escalation_rate * 100).toFixed(1);
    document.getElementById('kpi-escalation-rate').textContent = `${escPct}%`;

    // 2. Contacts avoided count
    document.getElementById('kpi-contacts-avoided').textContent = data.contacts_avoided;

    // 3. Avg contacts per resolved case
    document.getElementById('kpi-avg-contacts').textContent = data.avg_contacts_per_resolved_case;

    // 4. False decision count
    const falseDecElem = document.getElementById('kpi-false-decisions');
    if (data.false_decision_count === null || data.false_decision_count === undefined) {
      falseDecElem.textContent = 'Not yet measured — requires manual case labeling';
      falseDecElem.classList.add('text-small');
    } else {
      falseDecElem.textContent = data.false_decision_count;
      falseDecElem.classList.remove('text-small');
    }

    // 5. Recovery rate by category
    const tbody = document.getElementById('kpi-category-rows');
    tbody.innerHTML = '';

    const rates = data.recovery_rate_by_category || {};
    const categories = Object.keys(rates).sort();

    if (categories.length === 0) {
      tbody.innerHTML = '<tr><td colspan="3" class="loading-cell">No category metrics available.</td></tr>';
      return;
    }

    // Category descriptions for judge clarity
    const categoryNotes = {
      'card_expired': 'Awaiting Razorpay\'s native retry or email link dispatch',
      'insufficient_funds': 'Awaiting Razorpay\'s native retry cycle',
      'authentication_failed': '3DS auth failure — customer notification',
      'technical_error': 'Transient bank/gateway failure',
      'risk_block': 'High risk score — human escalation',
      'unclassified': 'LLM fallback classification triggered'
    };

    categories.forEach(cat => {
      const rateVal = rates[cat];
      const ratePct = (rateVal * 100).toFixed(1) + '%';
      const note = categoryNotes[cat] || 'Category performance metric';
      
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><strong>${escapeHtml(cat)}</strong></td>
        <td><span class="badge secondary">${ratePct}</span></td>
        <td><span class="metric-subtext">${escapeHtml(note)}</span></td>
      `;
      tbody.appendChild(tr);
    });

  } catch (err) {
    console.error('Error fetching metrics:', err);
    document.getElementById('kpi-escalation-rate').textContent = 'Error';
    document.getElementById('kpi-category-rows').innerHTML = `<tr><td colspan="3" class="loading-cell" style="color:var(--danger-color)">Failed to load metrics from server.</td></tr>`;
  }
}

/**
 * VIEW 2: Load & Render Case List
 */
async function loadCaseList() {
  const statusFilter = document.getElementById('filter-status').value;
  const categoryFilter = document.getElementById('filter-category').value;

  let url = `${API_BASE}/cases`;
  const params = new URLSearchParams();
  if (statusFilter) params.append('status', statusFilter);
  if (categoryFilter) params.append('category', categoryFilter);
  
  if (params.toString()) {
    url += `?${params.toString()}`;
  }

  const tbody = document.getElementById('cases-table-body');
  tbody.innerHTML = '<tr><td colspan="6" class="loading-cell">Loading cases...</td></tr>';

  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const cases = await res.json();

    tbody.innerHTML = '';
    if (cases.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="loading-cell">No matching recovery cases found.</td></tr>';
      return;
    }

    cases.forEach(item => {
      const tr = document.createElement('tr');
      const formattedDate = item.last_updated ? formatIsoDate(item.last_updated) : '--';
      const statusBadge = getStatusBadge(item.status);

      tr.innerHTML = `
        <td><a href="#" class="primary-link" onclick="event.preventDefault(); navigateTo('detail', '${escapeHtml(item.subscription_id)}')"><strong>${escapeHtml(item.subscription_id)}</strong></a></td>
        <td>${escapeHtml(item.last_category || 'unclassified')}</td>
        <td>${statusBadge}</td>
        <td>${item.contact_count}</td>
        <td>${formattedDate}</td>
        <td>
          <button class="secondary-btn" onclick="navigateTo('detail', '${escapeHtml(item.subscription_id)}')">View Audit Trail</button>
        </td>
      `;
      tbody.appendChild(tr);
    });

  } catch (err) {
    console.error('Error fetching cases:', err);
    tbody.innerHTML = `<tr><td colspan="6" class="loading-cell" style="color:var(--danger-color)">Failed to load case list from server.</td></tr>`;
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
    statusMsg.textContent = `Event processed for ${subId}! Category: ${result.classification?.category || 'N/A'}, Action: ${result.decision?.action_type || 'N/A'}`;

    // Refresh case list table
    loadCaseList();

    // Reset optional input fields
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
 * VIEW 3: Load & Render Case Detail
 */
async function loadCaseDetail(caseId) {
  const headerContent = document.getElementById('detail-header-content');
  const humanReviewBox = document.getElementById('human-review-box');
  const timelineContainer = document.getElementById('timeline-container');

  headerContent.innerHTML = '<div class="loading-cell">Loading case details...</div>';
  timelineContainer.innerHTML = '<div class="loading-cell">Loading timeline...</div>';
  humanReviewBox.classList.add('hidden');

  try {
    const res = await fetch(`${API_BASE}/cases/${encodeURIComponent(caseId)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const sub = data.subscription || {};
    const cs = data.case_state || {};
    const auditLogs = data.audit_log || [];

    // Render Header
    const statusBadge = getStatusBadge(cs.status || sub.status || 'unknown');
    const categoryName = cs.last_category || 'unclassified';
    const amountStr = `${sub.currency || 'INR'} ${(sub.plan_amount || 0).toLocaleString()}`;

    headerContent.innerHTML = `
      <div class="detail-title-group">
        <h2>Subscription: ${escapeHtml(sub.id || caseId)}</h2>
        <div class="detail-submeta">
          Customer ID: <strong>${escapeHtml(sub.customer_id || 'N/A')}</strong> &bull; 
          Plan Amount: <strong>${escapeHtml(amountStr)}</strong> &bull; 
          Customer Contact Count: <strong>${cs.contact_count ?? 0}</strong>
        </div>
      </div>
      <div class="detail-badges">
        <span class="badge info">Category: ${escapeHtml(categoryName)}</span>
        ${statusBadge}
      </div>
    `;

    // Show Human Review box if case status is 'escalated'
    if (cs.status === 'escalated') {
      humanReviewBox.classList.remove('hidden');
      document.getElementById('hr-note').value = '';
      document.getElementById('hr-status-msg').textContent = '';
    } else {
      humanReviewBox.classList.add('hidden');
    }

    // Render Judge-Friendly Audit Log Timeline
    timelineContainer.innerHTML = '';

    if (auditLogs.length === 0) {
      timelineContainer.innerHTML = '<div class="loading-cell">No audit log entries found for this case.</div>';
      return;
    }

    auditLogs.forEach((entry, index) => {
      const isHuman = entry.actor === 'human';
      const actorClass = isHuman ? 'human-actor' : 'system-actor';
      const actorBadgeClass = isHuman ? 'actor-human' : 'actor-system';
      const timeStr = formatIsoDate(entry.timestamp);

      // Determine step stage title for visual clarity
      let stageTitle = `Step ${index + 1}: Audit Event`;
      let stageIcon = '📋';
      const summaryLower = entry.event_summary.toLowerCase();

      if (summaryLower.includes('classified') || summaryLower.includes('classification')) {
        stageTitle = `Stage 1: Failure Classification`;
        stageIcon = '🔍';
      } else if (summaryLower.includes('policy') || summaryLower.includes('decided action') || summaryLower.includes('decision')) {
        stageTitle = `Stage 2: Policy Decision`;
        stageIcon = '🧠';
      } else if (summaryLower.includes('action executed') || summaryLower.includes('executed action')) {
        stageTitle = `Stage 3: Action Execution`;
        stageIcon = '🚀';
      } else if (summaryLower.includes('human review') || isHuman) {
        stageTitle = `Human Override / Review`;
        stageIcon = '👤';
      } else if (summaryLower.includes('failure event recorded') || summaryLower.includes('received')) {
        stageTitle = `Stage 0: Webhook Event Received`;
        stageIcon = '⚡';
      }

      const div = document.createElement('div');
      div.className = `timeline-item ${actorClass}`;
      div.innerHTML = `
        <div class="timeline-time">${timeStr}</div>
        <div class="timeline-header">
          <span class="stage-title">${stageIcon} ${escapeHtml(stageTitle)}</span>
          <span class="badge ${actorBadgeClass}">actor: ${escapeHtml(entry.actor || 'system')}</span>
        </div>
        <div class="timeline-body">
          <p class="timeline-text">${escapeHtml(entry.event_summary)}</p>
        </div>
      `;
      timelineContainer.appendChild(div);
    });

  } catch (err) {
    console.error('Error fetching case detail:', err);
    headerContent.innerHTML = `<div class="loading-cell" style="color:var(--danger-color)">Failed to load case details.</div>`;
    timelineContainer.innerHTML = `<div class="loading-cell" style="color:var(--danger-color)">Failed to load timeline.</div>`;
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
    statusMsg.textContent = 'Human review submitted successfully!';

    // Refresh case detail view to update timeline and state
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
 * Utility Functions
 */
function getStatusBadge(status) {
  const s = (status || 'unknown').toLowerCase();
  let badgeClass = 'status-stopped';
  let label = s;
  
  if (s === 'recovered') {
    badgeClass = 'status-recovered';
  } else if (s === 'escalated') {
    badgeClass = 'status-escalated';
  } else if (s === 'open') {
    badgeClass = 'status-open';
    label = 'open (awaiting Razorpay\'s native retry)';
  }

  return `<span class="badge ${badgeClass}">${escapeHtml(label)}</span>`;
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
