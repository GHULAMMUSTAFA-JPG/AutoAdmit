// AutoAdmit Engine Frontend Application

const API_BASE = "";
let currentDrafts = [];
let selectedDraft = null;
let currentFilter = "ALL";
let lastDiscoveredUniversities = [];

// Retrieve saved authentication header from localStorage or prompt
let authHeader = localStorage.getItem("autoadmit_auth") || "";

function fetchWithAuth(url, options = {}) {
  options.headers = options.headers || {};
  if (authHeader) {
    options.headers["Authorization"] = authHeader;
  }
  if (!options.headers["Content-Type"] && options.method && options.method !== "GET") {
    options.headers["Content-Type"] = "application/json";
  }
  return fetch(url, options).then(res => {
    if (res.status === 401 && !url.includes("/login")) {
      showAuthOverlay("Session expired or unauthorized. Please enter system password.");
    }
    return res;
  });
}

function showAuthOverlay(msg = "") {
  const overlay = document.getElementById("auth-overlay");
  const errEl = document.getElementById("auth-error");
  if (overlay) {
    overlay.classList.remove("hidden");
    if (msg && errEl) {
      errEl.textContent = msg;
      errEl.classList.remove("hidden");
    } else if (errEl) {
      errEl.classList.add("hidden");
    }
    const pwdInput = document.getElementById("auth-password");
    if (pwdInput) {
      pwdInput.value = "";
      pwdInput.focus();
    }
  }
}

function hideAuthOverlay() {
  const overlay = document.getElementById("auth-overlay");
  if (overlay) {
    overlay.classList.add("hidden");
  }
}

async function submitPasswordLogin() {
  const pwdInput = document.getElementById("auth-password");
  const errEl = document.getElementById("auth-error");
  const password = pwdInput ? pwdInput.value.trim() : "";

  if (!password) {
    if (errEl) {
      errEl.textContent = "Please enter password.";
      errEl.classList.remove("hidden");
    }
    return;
  }

  try {
    const res = await fetch("/api/v1/system/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: password })
    });

    if (res.ok) {
      authHeader = "Basic " + btoa("admin:" + password);
      localStorage.setItem("autoadmit_auth", authHeader);
      hideAuthOverlay();
      syncCSTClock();
      loadUniversities();
      restoreSavedDiscoveredUniversities();
    } else {
      if (errEl) {
        errEl.textContent = "Invalid password. Access denied.";
        errEl.classList.remove("hidden");
      }
    }
  } catch (err) {
    if (errEl) {
      errEl.textContent = "Connection error: " + err;
      errEl.classList.remove("hidden");
    }
  }
}

function lockSession() {
  authHeader = "";
  localStorage.removeItem("autoadmit_auth");
  showAuthOverlay();
}

// Tab Titles Mapping
const tabTitles = {
  "tab-setup": "1. Campaign Setup & Resource Estimation",
  "tab-universities": "2. University Feasibility & Scholarship Directory",
  "tab-faculty": "3. Verified Faculty Supervisors Roster",
  "tab-review": "4. Email Review Workspace & Approval Staging",
  "tab-dispatch": "5. Outbox Dispatcher & Delivery Scheduler",
  "tab-analytics": "6. Campaign Analytics & Inbound Reply Tracker",
  "tab-terminal": "7. System Terminal & Live Log Streaming"
};

// Tab Switching
function switchTab(tabId, clickedBtn = null) {
  document.querySelectorAll(".tab-content").forEach(el => el.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach(el => el.classList.remove("active"));
  document.querySelectorAll(".tab-btn").forEach(el => el.classList.remove("active"));

  const target = document.getElementById(tabId);
  if (target) target.classList.add("active");

  const titleEl = document.getElementById("current-view-title");
  if (titleEl && tabTitles[tabId]) {
    titleEl.textContent = tabTitles[tabId];
  }

  // Highlight active button
  const btn = clickedBtn || (typeof event !== "undefined" && event ? event.target.closest(".nav-item, .tab-btn") : null);
  if (btn) {
    btn.classList.add("active");
  } else {
    document.querySelectorAll(".nav-item").forEach(item => {
      const oc = item.getAttribute("onclick");
      if (oc && oc.includes(tabId)) {
        item.classList.add("active");
      }
    });
  }

  // Load relevant data on tab open
  if (tabId === "tab-universities") loadUniversities();
  if (tabId === "tab-faculty") loadFaculty();
  if (tabId === "tab-review") loadDrafts();
  if (tabId === "tab-dispatch") loadDispatchQueue();
  if (tabId === "tab-analytics") loadAnalytics();
}

// Safety Controls Toggling
async function toggleMasterGate() {
  const btn = document.getElementById("btn-master-gate");
  const currentlyActive = btn.classList.contains("gate-active");
  const newState = !currentlyActive;

  try {
    const res = await fetchWithAuth("/api/v1/system/safety-toggle", {
      method: "POST",
      body: JSON.stringify({ master_gate_active: newState })
    });
    const data = await res.json();
    updateGateUI(data.master_gate_active);
  } catch (err) {
    alert("Error updating Master Kill-Switch: " + err);
  }
}

async function toggleSandboxMode() {
  const btn = document.getElementById("btn-sandbox-mode");
  const currentlyOn = btn.classList.contains("sandbox-on");
  const newState = !currentlyOn;

  try {
    const res = await fetchWithAuth("/api/v1/system/safety-toggle", {
      method: "POST",
      body: JSON.stringify({ sandbox_mode: newState })
    });
    const data = await res.json();
    updateSandboxUI(data.sandbox_mode);
  } catch (err) {
    alert("Error updating Sandbox Mode: " + err);
  }
}

function updateGateUI(isActive) {
  const btn = document.getElementById("btn-master-gate");
  if (isActive) {
    btn.className = "btn-toggle gate-active";
    btn.textContent = "ACTIVE (SAFE)";
  } else {
    btn.className = "btn-toggle gate-inactive";
    btn.textContent = "INACTIVE (LIVE)";
  }
}

function updateSandboxUI(isOn) {
  const btn = document.getElementById("btn-sandbox-mode");
  if (isOn) {
    btn.className = "btn-toggle sandbox-on";
    btn.textContent = "ON";
  } else {
    btn.className = "btn-toggle sandbox-off";
    btn.textContent = "OFF";
  }
}

// Live CST Clock
async function syncCSTClock() {
  try {
    const res = await fetchWithAuth("/api/v1/dispatch/cst-status");
    const data = await res.json();
    document.getElementById("cst-clock").textContent = data.cst_time.split(" ")[1] + " CST";
    const badge = document.getElementById("cst-window-badge");
    if (data.is_within_cst_window) {
      badge.className = "badge window-open";
      badge.textContent = "CST Window: ACTIVE (09:00-16:30)";
    } else {
      badge.className = "badge window-closed";
      badge.textContent = "CST Window: PAUSED (Off-Hours)";
    }
    updateGateUI(data.master_gate_active);
    updateSandboxUI(data.sandbox_mode);
  } catch (err) {
    console.error("CST sync error:", err);
  }
}

// Tab 1 Discovery Mode Switcher
function switchDiscoveryMode(mode) {
  const btnAuto = document.getElementById("btn-mode-auto");
  const btnManual = document.getElementById("btn-mode-manual");
  const autoBox = document.getElementById("mode-auto-container");
  const manualBox = document.getElementById("mode-manual-container");

  if (mode === "auto") {
    if (btnAuto) btnAuto.className = "btn btn-primary mr-2";
    if (btnManual) btnManual.className = "btn btn-secondary";
    if (autoBox) autoBox.classList.remove("hidden");
    if (manualBox) manualBox.classList.add("hidden");
  } else {
    if (btnAuto) btnAuto.className = "btn btn-secondary mr-2";
    if (btnManual) btnManual.className = "btn btn-primary";
    if (autoBox) autoBox.classList.add("hidden");
    if (manualBox) manualBox.classList.remove("hidden");
  }
}

// Render Matched Endpoints with numbering & row index
function renderMatchedEndpoints(universities) {
  const countEl = document.getElementById("matched-univ-count");
  if (countEl) countEl.textContent = universities.length;

  const tbody = document.getElementById("matched-endpoints-tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  universities.forEach((u, idx) => {
    const tr = document.createElement("tr");
    const endpointsHtml = (u.department_endpoints || []).map(ep => 
      `<div style="margin-bottom: 3px;"><span class="badge version">${ep.name}</span> <code style="font-size: 0.75rem;">${ep.url}</code></div>`
    ).join("");

    tr.innerHTML = `
      <td style="text-align: center; font-weight: bold; color: var(--accent);">${idx + 1}</td>
      <td><strong>${u.name}</strong> <span style="font-size: 0.8rem; color: #888;">(${u.chinese_name || ""})</span></td>
      <td><span class="badge ${u.region === 'Beijing' || u.region === 'Shanghai' ? 'status-staged' : 'status-sent'}">${u.region}</span></td>
      <td><span class="badge ${u.tier.includes('Dream') ? 'warning' : 'version'}">${u.tier}</span></td>
      <td>${endpointsHtml}</td>
    `;
    tbody.appendChild(tr);
  });

  const container = document.getElementById("discovered-endpoints-container");
  if (container) {
    if (universities.length > 0) {
      container.classList.remove("hidden");
    } else {
      container.classList.add("hidden");
    }
  }
}

// Tab 1: Automated Regional & Rank Discovery
async function runRegionalFilter() {
  const regionSelect = document.getElementById("filter-regions");
  const selectedRegions = Array.from(regionSelect.selectedOptions).map(o => o.value);
  const tier = document.getElementById("filter-tier").value;
  const discipline = document.getElementById("filter-discipline").value;
  const keywordInput = document.getElementById("filter-keyword");
  const keyword = keywordInput ? keywordInput.value.trim() : null;

  const payload = {
    regions: selectedRegions.includes("All") ? null : selectedRegions,
    tiers: tier === "All" ? null : [tier],
    discipline: discipline,
    keyword: keyword || null
  };

  try {
    const res = await fetchWithAuth("/api/v1/discovery/filter", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    const universities = await res.json();
    lastDiscoveredUniversities = universities;

    // Save to localStorage so they persist across page reloads!
    localStorage.setItem("autoadmit_discovered_universities", JSON.stringify(universities));

    renderMatchedEndpoints(universities);
  } catch (err) {
    alert("Error discovering universities: " + err);
  }
}

function clearDiscoveredUniversities() {
  lastDiscoveredUniversities = [];
  localStorage.removeItem("autoadmit_discovered_universities");
  renderMatchedEndpoints([]);
}

function restoreSavedDiscoveredUniversities() {
  const saved = localStorage.getItem("autoadmit_discovered_universities");
  if (saved) {
    try {
      lastDiscoveredUniversities = JSON.parse(saved);
      if (Array.isArray(lastDiscoveredUniversities) && lastDiscoveredUniversities.length > 0) {
        renderMatchedEndpoints(lastDiscoveredUniversities);
      }
    } catch (e) {
      console.error("Error restoring saved universities:", e);
    }
  }
}

// Tab 1: Prepare Pre-Run Estimate for Matched Universities
async function prepareEstimateForMatched() {
  if (!lastDiscoveredUniversities || lastDiscoveredUniversities.length === 0) {
    alert("No universities matched. Run search first.");
    return;
  }

  // Flatten all endpoints
  const allEndpoints = [];
  lastDiscoveredUniversities.forEach(u => {
    (u.department_endpoints || []).forEach(ep => {
      allEndpoints.push(ep);
    });
  });

  try {
    const res = await fetchWithAuth("/api/v1/discovery/estimate", {
      method: "POST",
      body: JSON.stringify(allEndpoints)
    });
    const est = await res.json();

    const univEl = document.getElementById("est-univs");
    if (univEl) univEl.textContent = lastDiscoveredUniversities.length;
    document.getElementById("est-depts").textContent = est.total_target_departments;
    document.getElementById("est-pages").textContent = est.estimated_pages_to_crawl;
    document.getElementById("est-faculty").textContent = est.estimated_faculty_count;
    document.getElementById("est-tokens").textContent = est.estimated_gemini_tokens.toLocaleString();
    document.getElementById("est-runtime").textContent = est.estimated_runtime_seconds + "s";

    const card = document.getElementById("cost-estimate-card");
    if (card) card.classList.remove("hidden");
    document.getElementById("gate-status-text").textContent = "LOCKED (Approval Required)";
  } catch (err) {
    alert("Error generating estimate: " + err);
  }
}

function calculateCostEstimateFromUrls() {
  calculateCostEstimate();
}

// Tab 1: Calculate Pre-Run Cost Estimate (Direct URLs)
async function calculateCostEstimate() {
  const text = document.getElementById("intake-urls").value.trim();
  const urls = text.split("\n").map(u => u.trim()).filter(u => u.length > 0);
  
  if (urls.length === 0) {
    alert("Please provide at least one target department URL.");
    return;
  }

  const endpoints = urls.map(u => ({
    name: "School of Computer Science",
    url: u
  }));

  try {
    const res = await fetchWithAuth("/api/v1/discovery/estimate", {
      method: "POST",
      body: JSON.stringify(endpoints)
    });
    const est = await res.json();

    const univEl = document.getElementById("est-univs");
    if (univEl) univEl.textContent = "1+";
    document.getElementById("est-depts").textContent = est.total_target_departments;
    document.getElementById("est-pages").textContent = est.estimated_pages_to_crawl;
    document.getElementById("est-faculty").textContent = est.estimated_faculty_count;
    document.getElementById("est-tokens").textContent = est.estimated_gemini_tokens.toLocaleString();
    document.getElementById("est-runtime").textContent = est.estimated_runtime_seconds + "s";
    
    const card = document.getElementById("cost-estimate-card");
    card.classList.remove("hidden");
    document.getElementById("gate-status-text").textContent = "LOCKED (Approval Required)";
  } catch (err) {
    alert("Error calculating estimate: " + err);
  }
}

// Approve Gate & Start Parallel Discovery / Extraction
async function approveCostGate() {
  try {
    const res = await fetchWithAuth("/api/v1/discovery/approve", { method: "POST" });
    const est = await res.json();
    if (est.is_approved) {
      document.getElementById("gate-status-text").textContent = "UNLOCKED & APPROVED";
      alert("Cost Gate Approved! Launching parallel scraping workers for Master's supervisors (硕导).");
      
      if (lastDiscoveredUniversities && lastDiscoveredUniversities.length > 0) {
        // Multi-university parallel harvest
        const targets = lastDiscoveredUniversities.map(u => ({
          university_name: u.name,
          department_name: "School of Computer Science & AI",
          department_urls: (u.department_endpoints || []).map(ep => ep.url)
        }));

        await fetchWithAuth("/api/v1/professors/harvest-batch", {
          method: "POST",
          body: JSON.stringify({ targets: targets })
        });
      } else {
        const text = document.getElementById("intake-urls").value.trim();
        const urls = text.split("\n").map(u => u.trim()).filter(u => u.length > 0);
        
        await fetchWithAuth("/api/v1/professors/harvest", {
          method: "POST",
          body: JSON.stringify({
            department_urls: urls,
            university_name: "Target University",
            department_name: "School of Computer Science"
          })
        });
      }
      loadFaculty();
    }
  } catch (err) {
    alert("Error approving cost gate: " + err);
  }
}

// Tab 2: Universities Directory
async function loadUniversities() {
  try {
    const res = await fetchWithAuth("/api/v1/discovery/universities");
    const universities = await res.json();
    const tbody = document.getElementById("universities-tbody");
    tbody.innerHTML = "";

    universities.forEach(u => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${u.name}</strong></td>
        <td>${u.chinese_name || "-"}</td>
        <td><code>${u.domain}</code></td>
        <td>${u.cs_ranking ? "#" + u.cs_ranking : "Top 50"}</td>
        <td><span class="badge ${u.tier.includes('Dream') ? 'warning' : 'version'}">${u.tier}</span></td>
        <td>${u.scholarships_available.join(", ")}</td>
        <td>${u.application_fee_rmb === 0 ? '<span class="badge window-open">0 RMB (Free)</span>' : u.application_fee_rmb + ' RMB'}</td>
        <td style="max-width: 250px; font-size: 0.8rem;">${u.feasibility_notes}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error("Error loading universities:", err);
  }
}

// Tab 3: Faculty Roster
async function loadFaculty() {
  try {
    const res = await fetchWithAuth("/api/v1/professors");
    const faculty = await res.json();
    const tbody = document.getElementById("faculty-tbody");
    tbody.innerHTML = "";

    if (faculty.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted);">No supervisors scraped yet. Approve a discovery intake run to populate.</td></tr>`;
      return;
    }

    faculty.forEach(f => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${f.name}</strong> ${f.native_name ? '(' + f.native_name + ')' : ''}</td>
        <td>${f.university}</td>
        <td>${f.department}</td>
        <td><span class="badge window-open">${f.qualification}</span></td>
        <td><code>${f.email}</code></td>
        <td>${f.research_areas.join(", ")}</td>
        <td><code title="${f.content_hash}">${f.content_hash.substring(0, 8)}...</code></td>
        <td><a href="${f.source_url}" target="_blank" style="color: var(--accent-blue);">Profile ↗</a></td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error("Error loading faculty:", err);
  }
}

// Tab 4: Email Review Workspace
async function loadDrafts() {
  try {
    const res = await fetchWithAuth("/api/v1/drafts");
    currentDrafts = await res.json();
    const select = document.getElementById("select-draft");
    select.innerHTML = `<option value="">-- Choose a pending draft (${currentDrafts.length} total) --</option>`;

    currentDrafts.forEach(d => {
      const opt = document.createElement("option");
      opt.value = d.id;
      opt.textContent = `[${d.status}] ${d.recipient_name} — ${d.university}`;
      select.appendChild(opt);
    });

    if (currentDrafts.length > 0 && !selectedDraft) {
      select.value = currentDrafts[0].id;
      onDraftSelected();
    }
  } catch (err) {
    console.error("Error loading drafts:", err);
  }
}

function onDraftSelected() {
  const select = document.getElementById("select-draft");
  const draftId = select.value;
  selectedDraft = currentDrafts.find(d => d.id === draftId);

  if (selectedDraft) {
    document.getElementById("rev-prof-name").textContent = selectedDraft.recipient_name;
    document.getElementById("rev-prof-univ").textContent = selectedDraft.university;
    document.getElementById("rev-prof-email").textContent = selectedDraft.recipient_email;
    document.getElementById("rev-prof-digest").textContent = selectedDraft.research_digest;

    document.getElementById("rev-subject").value = selectedDraft.subject_line;
    document.getElementById("rev-body").value = selectedDraft.body_text;
    document.getElementById("draft-status-badge").textContent = selectedDraft.status;
    updateWordCount();
  }
}

function updateWordCount() {
  const text = document.getElementById("rev-body").value.trim();
  const words = text ? text.split(/\s+/).length : 0;
  const countEl = document.getElementById("word-count");
  countEl.textContent = words;
  if (words > 200) {
    countEl.style.color = "var(--accent-red)";
  } else {
    countEl.style.color = "var(--accent-green)";
  }
}

async function approveCurrentDraft() {
  if (!selectedDraft) return alert("Select a draft first.");
  const subject = document.getElementById("rev-subject").value;
  const body = document.getElementById("rev-body").value;

  try {
    const res = await fetchWithAuth(`/api/v1/drafts/${selectedDraft.id}/approve`, {
      method: "POST",
      body: JSON.stringify({ subject_line: subject, body_text: body })
    });
    const updated = await res.json();
    alert(`Draft approved! Staged for dispatch as ${updated.status}.`);
    loadDrafts();
  } catch (err) {
    alert("Approval error: " + err);
  }
}

async function rejectCurrentDraft() {
  if (!selectedDraft) return alert("Select a draft first.");
  const reason = prompt("Enter reason for discarding draft:", "Poor research alignment");
  if (!reason) return;

  try {
    await fetchWithAuth(`/api/v1/drafts/${selectedDraft.id}/reject`, {
      method: "POST",
      body: JSON.stringify({ rejection_reason: reason })
    });
    alert("Draft discarded.");
    loadDrafts();
  } catch (err) {
    alert("Rejection error: " + err);
  }
}

async function regenerateCurrentDraft() {
  if (!selectedDraft) return alert("Select a draft first.");
  try {
    const res = await fetchWithAuth(`/api/v1/drafts/${selectedDraft.id}/regenerate`, { method: "POST" });
    const refreshed = await res.json();
    selectedDraft = refreshed;
    document.getElementById("rev-prof-digest").textContent = refreshed.research_digest;
    document.getElementById("rev-subject").value = refreshed.subject_line;
    document.getElementById("rev-body").value = refreshed.body_text;
    updateWordCount();
    alert("Draft regenerated via Gemini!");
  } catch (err) {
    alert("Regeneration error: " + err);
  }
}

// Tab 5: Dispatch Queue
async function loadDispatchQueue() {
  try {
    const res = await fetchWithAuth("/api/v1/dispatch/queue");
    const queue = await res.json();
    document.getElementById("approved-count").textContent = queue.length;
    const tbody = document.getElementById("dispatch-tbody");
    tbody.innerHTML = "";

    if (queue.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">No drafts in APPROVED state. Review and approve drafts in Tab 4 first.</td></tr>`;
      return;
    }

    queue.forEach(d => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><code>${d.id.substring(0, 8)}...</code></td>
        <td>${d.recipient_name} &lt;${d.recipient_email}&gt;</td>
        <td>${d.university}</td>
        <td>${d.subject_line}</td>
        <td><span class="badge window-open">${d.status}</span></td>
        <td><button class="btn btn-primary" onclick="sendSingleDraft('${d.id}')">Send Now</button></td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error("Error loading queue:", err);
  }
}

async function sendSingleDraft(draftId) {
  try {
    const res = await fetchWithAuth(`/api/v1/dispatch/send-single/${draftId}`, { method: "POST" });
    if (!res.ok) {
      const errData = await res.json();
      alert(`Dispatch Blocked: ${errData.detail}`);
      return;
    }
    const data = await res.json();
    alert(`Success! Dispatched draft ${draftId} to ${data.recipient_email} (Message-ID: ${data.message_id})`);
    loadDispatchQueue();
  } catch (err) {
    alert("Dispatch error: " + err);
  }
}

async function sendBatch(dryRun) {
  try {
    const res = await fetchWithAuth("/api/v1/dispatch/send-batch", {
      method: "POST",
      body: JSON.stringify({ send_all_approved: true, dry_run: dryRun })
    });
    if (!res.ok) {
      const err = await res.json();
      alert(`Batch Blocked: ${err.detail}`);
      return;
    }
    const sent = await res.json();
    alert(`Batch execution finished! Dispatched ${sent.length} emails.`);
    loadDispatchQueue();
  } catch (err) {
    alert("Batch error: " + err);
  }
}

// Tab 6: Analytics
async function loadAnalytics() {
  try {
    const res = await fetchWithAuth("/api/v1/track/analytics");
    const a = await res.json();
    document.getElementById("metric-discovered").textContent = a.total_professors_discovered;
    document.getElementById("metric-approved").textContent = a.total_drafts_approved;
    document.getElementById("metric-sent").textContent = a.total_sent;
    document.getElementById("metric-opened").textContent = a.total_opened_pixel;
    document.getElementById("metric-replies").textContent = a.total_replies_received;
    document.getElementById("metric-latency").textContent = a.average_reply_latency_hours + "h";
  } catch (err) {
    console.error("Error loading analytics:", err);
  }
}

async function pollIMAPReplies() {
  try {
    const res = await fetchWithAuth("/api/v1/track/poll-replies", { method: "POST" });
    const replies = await res.json();
    alert(`Polled IMAP inbox. Found ${replies.length} replies.`);
    loadAnalytics();
  } catch (err) {
    alert("IMAP poll error: " + err);
  }
}

// Tab 7: Terminal & WebSocket Logs
let socket = null;
function initWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/logs`;
  
  socket = new WebSocket(wsUrl);
  socket.onmessage = function (event) {
    try {
      const log = JSON.parse(event.data);
      appendLog(log);
    } catch (e) {
      appendRaw(event.data);
    }
  };

  socket.onclose = function () {
    if (authHeader) {
      setTimeout(initWebSocket, 4000);
    }
  };
}

function appendLog(log) {
  if (currentFilter !== "ALL" && log.module !== currentFilter) return;
  const terminal = document.getElementById("terminal-window");
  const line = document.createElement("div");
  line.className = `terminal-line ${log.level.toLowerCase()}`;
  line.textContent = `[${log.timestamp || new Date().toISOString().split("T")[1].slice(0, 8)}] [${log.level}] [${log.module}]: ${log.message}`;
  terminal.appendChild(line);
  terminal.scrollTop = terminal.scrollHeight;
}

function appendRaw(text) {
  const terminal = document.getElementById("terminal-window");
  const line = document.createElement("div");
  line.className = "terminal-line";
  line.textContent = text;
  terminal.appendChild(line);
  terminal.scrollTop = terminal.scrollHeight;
}

function clearTerminal() {
  document.getElementById("terminal-window").innerHTML = "";
}

function filterLogs() {
  currentFilter = document.getElementById("log-filter").value;
}

// Initial Bootstrapping
window.addEventListener("DOMContentLoaded", async () => {
  restoreSavedDiscoveredUniversities();
  if (authHeader) {
    try {
      const res = await fetchWithAuth("/api/v1/system/health");
      if (res.ok) {
        hideAuthOverlay();
        syncCSTClock();
        setInterval(syncCSTClock, 10000);
        initWebSocket();
        return;
      }
    } catch (e) {}
  }
  showAuthOverlay();
  setInterval(syncCSTClock, 10000);
  initWebSocket();
});

