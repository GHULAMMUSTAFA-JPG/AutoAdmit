// AutoAdmit Enterprise Engine Frontend Application

const API_BASE = "";
let currentDrafts = [];
let selectedDraft = null;
let currentFilter = "ALL";
let lastDiscoveredUniversities = [];
let activeDiscoverySource = "combined";

// Authentication state management
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
      loadAllData();
      initScrollSpy();
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

// Enterprise Top Navigation Smooth Jump
function smoothJump(event, targetId) {
  if (event) event.preventDefault();
  const target = document.getElementById(targetId);
  if (target) {
    const headerOffset = 110;
    const elementPosition = target.getBoundingClientRect().top;
    const offsetPosition = elementPosition + window.pageYOffset - headerOffset;

    window.scrollTo({
      top: offsetPosition,
      behavior: "smooth"
    });
  }

  document.querySelectorAll(".nav-tab").forEach(tab => tab.classList.remove("active"));
  if (event && event.currentTarget) {
    event.currentTarget.classList.add("active");
  }
}

// Setup ScrollSpy using standard window scroll observer
function initScrollSpy() {
  const sections = document.querySelectorAll(".page-section");
  const navTabs = document.querySelectorAll(".nav-tab");
  if (!sections || sections.length === 0) return;

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const id = entry.target.id;
        navTabs.forEach(tab => {
          const href = tab.getAttribute("href");
          if (href === `#${id}`) {
            tab.classList.add("active");
          } else {
            tab.classList.remove("active");
          }
        });
      }
    });
  }, {
    root: null,
    rootMargin: "-20% 0px -70% 0px",
    threshold: 0
  });

  sections.forEach(s => observer.observe(s));
}

// Global Data Loader (Loads strictly fresh live state, no sample seed restoration)
function loadAllData() {
  loadUniversities();
  loadFaculty();
  loadPrompts();
  loadDrafts();
  loadDispatchQueue();
  loadAnalytics();
  loadInboundReplies();
}

// Safety Controls
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
  if (!btn) return;
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
  if (!btn) return;
  if (isOn) {
    btn.className = "btn-toggle sandbox-on";
    btn.textContent = "ON";
  } else {
    btn.className = "btn-toggle sandbox-off";
    btn.textContent = "OFF";
  }
}

// Live CST Clock: Runs smoothly in local JS (Zero Network Overhead / No HTTP Polling)
function startLocalCSTClock() {
  function tick() {
    const now = new Date();
    const timeStr = now.toLocaleTimeString("en-GB", {
      timeZone: "Asia/Shanghai",
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit"
    });
    const clockEl = document.getElementById("cst-clock");
    if (clockEl) {
      clockEl.textContent = timeStr + " CST";
    }

    const [hStr, mStr] = timeStr.split(":");
    const totalMinutes = parseInt(hStr, 10) * 60 + parseInt(mStr, 10);
    const isWithinWindow = totalMinutes >= (9 * 60) && totalMinutes <= (16 * 60 + 30);
    const badge = document.getElementById("cst-window-badge");
    if (badge) {
      if (isWithinWindow) {
        badge.className = "badge window-open";
        badge.textContent = "ACTIVE (09:00-16:30)";
      } else {
        badge.className = "badge window-closed";
        badge.textContent = "PAUSED (Off-Hours)";
      }
    }
  }
  tick();
  setInterval(tick, 1000);
}

// Initial Sync of Server Gate States (Called once on boot, not repeatedly polled)
async function syncCSTClock() {
  try {
    const res = await fetchWithAuth("/api/v1/dispatch/cst-status");
    const data = await res.json();
    updateGateUI(data.master_gate_active);
    updateSandboxUI(data.sandbox_mode);
  } catch (err) {
    console.error("Server gate sync error:", err);
  }
}

// ADR-0001 Multi-Source Selector
function setDiscoverySource(source) {
  activeDiscoverySource = source;
  document.querySelectorAll(".source-pill").forEach(p => p.classList.remove("active"));
  
  const activeBtn = document.getElementById(`src-${source}`);
  if (activeBtn) activeBtn.classList.add("active");

  const autoBox = document.getElementById("mode-auto-container");
  const manualBox = document.getElementById("mode-manual-container");

  if (source === "manual") {
    if (autoBox) autoBox.classList.add("hidden");
    if (manualBox) manualBox.classList.remove("hidden");
  } else {
    if (autoBox) autoBox.classList.remove("hidden");
    if (manualBox) manualBox.classList.add("hidden");
  }
}

// ============================================================================
// Color Badge & Formatting Helpers (Tiers, Regions, Pipeline Statuses)
// ============================================================================
let inlineLogsBuffer = [];
let allDirectoryUniversities = [];
let filteredPortalUniversities = [];

function getTierBadgeClass(tierStr) {
  if (!tierStr) return "badge-tier-3";
  if (tierStr.includes("Tier 1") || tierStr.includes("Dream")) return "badge-tier-1";
  if (tierStr.includes("Tier 2") || tierStr.includes("Target")) return "badge-tier-2";
  return "badge-tier-3";
}

function getRegionBadgeClass(region) {
  if (!region) return "badge-region-default";
  const north = ["Beijing", "Tianjin", "Hebei", "Shanxi", "Shandong"];
  const east = ["Shanghai", "Jiangsu", "Zhejiang", "Anhui", "Fujian", "Jiangxi"];
  const central = ["Hubei", "Hunan", "Henan"];
  const west = ["Sichuan", "Chongqing", "Shaanxi", "Gansu", "Yunnan", "Xinjiang"];
  const south = ["Guangdong", "Guangxi"];
  const northeast = ["Heilongjiang", "Liaoning", "Jilin"];
  if (north.includes(region)) return "badge-region-north";
  if (east.includes(region)) return "badge-region-east";
  if (central.includes(region)) return "badge-region-central";
  if (west.includes(region)) return "badge-region-west";
  if (south.includes(region)) return "badge-region-south";
  if (northeast.includes(region)) return "badge-region-northeast";
  return "badge-region-default";
}

function getPipelineStatusBadge(status) {
  const s = status || "Pending Live Check";
  if (s === "Professor Extraction Completed") return `<span class="badge badge-status-extracted">✓ Supervisors Extracted</span>`;
  if (s === "Faculty Page Found") return `<span class="badge badge-status-faculty">✓ Faculty Page Found</span>`;
  if (s === "Department URL Found") return `<span class="badge badge-status-dept">✓ Dept URL Found</span>`;
  if (s === "Department URL Not Found") return `<span class="badge badge-status-missing">⚠ Dept URL Not Found</span>`;
  if (s === "Requires Manual Review") return `<span class="badge badge-status-manual">✗ Manual Review</span>`;
  if (s === "Homepage Verified" || s === "University Homepage Verified") {
    return `<span class="badge badge-status-verified">● Homepage Verified</span>`;
  }
  return `<span class="badge badge-status-pending" title="Not live-probed yet. Click 'Find Dept' or 'Resolve Real Dept Links' or launch Worker Pool to verify live.">⏳ Pending Live Check</span>`;
}

// Table Row Block Limits & Drag-to-Resize Controller
const tableRowLimits = {
  portals: 10,
  matrix: 10,
  faculty: 10
};

function renderTableSkeleton(tbodyId, colCount = 8, rowCount = 8) {
  const tbody = document.getElementById(tbodyId);
  if (!tbody) return;
  let html = "";
  for (let r = 0; r < rowCount; r++) {
    html += `<tr class="skeleton-row">`;
    for (let c = 0; c < colCount; c++) {
      const wClass = c === 0 ? "w-sm" : (c % 3 === 0 ? "badge-shape" : (c % 2 === 0 ? "w-lg" : "w-md"));
      html += `<td><div class="skeleton-bar ${wClass}"></div></td>`;
    }
    html += `</tr>`;
  }
  tbody.innerHTML = html;
}

function onTableLimitChange(tableKey, val) {
  tableRowLimits[tableKey] = val === "ALL" ? 99999 : (parseInt(val, 10) || 10);
  const viewMap = {
    portals: "portals-table-view",
    matrix: "matrix-table-view",
    faculty: "faculty-table-view"
  };
  const viewEl = document.getElementById(viewMap[tableKey]);
  if (viewEl) {
    if (tableRowLimits[tableKey] <= 10) viewEl.style.maxHeight = "430px";
    else if (tableRowLimits[tableKey] <= 25) viewEl.style.maxHeight = "680px";
    else viewEl.style.maxHeight = "860px";
  }
  if (tableKey === "portals") applyPortalsTableFilter();
  if (tableKey === "matrix") applyMatrixTableFilter();
  if (tableKey === "faculty") applyFacultyTableFilter();
}

function initTableDragResizers() {
  const handles = document.querySelectorAll(".table-resize-handle");
  handles.forEach(handle => {
    let startY = 0;
    let startHeight = 430;
    const targetId = handle.getAttribute("data-target");
    const tableKey = handle.getAttribute("data-table");

    const onMouseMove = (e) => {
      const container = document.getElementById(targetId);
      if (!container) return;
      const deltaY = e.clientY - startY;
      const newHeight = Math.max(240, Math.min(1400, startHeight + deltaY));
      container.style.maxHeight = `${newHeight}px`;

      // Automatically increase rendered row block as user drags taller
      const neededRows = Math.max(10, Math.ceil((newHeight - 44) / 38));
      if (tableKey && neededRows > tableRowLimits[tableKey]) {
        tableRowLimits[tableKey] = neededRows;
        const selMap = { portals: "portal-limit-select", matrix: "matrix-limit-select", faculty: "faculty-limit-select" };
        const selEl = document.getElementById(selMap[tableKey]);
        if (selEl) {
          if (neededRows > 100) selEl.value = "ALL";
          else if (neededRows > 50) selEl.value = "100";
          else if (neededRows > 25) selEl.value = "50";
          else if (neededRows > 10) selEl.value = "25";
        }
        if (tableKey === "portals") applyPortalsTableFilter();
        if (tableKey === "matrix") applyMatrixTableFilter();
        if (tableKey === "faculty") applyFacultyTableFilter();
      }
    };

    const onMouseUp = () => {
      handle.classList.remove("dragging");
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };

    handle.addEventListener("mousedown", (e) => {
      e.preventDefault();
      const container = document.getElementById(targetId);
      if (!container) return;
      startY = e.clientY;
      startHeight = container.getBoundingClientRect().height || 430;
      handle.classList.add("dragging");
      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    });
  });
}

function populateRegionFilterDropdown(selectId, universities) {
  const select = document.getElementById(selectId);
  if (!select) return;
  const currentVal = select.value || "All";
  const counts = {};
  (universities || []).forEach(u => {
    const r = u.region || "National";
    counts[r] = (counts[r] || 0) + 1;
  });
  const sortedRegions = Object.keys(counts).sort();
  select.innerHTML = `<option value="All">All Regions (${(universities || []).length})</option>`;
  sortedRegions.forEach(r => {
    const opt = document.createElement("option");
    opt.value = r;
    opt.textContent = `${r} (${counts[r]})`;
    select.appendChild(opt);
  });
  if (sortedRegions.includes(currentVal)) {
    select.value = currentVal;
  }
}

function sortUniversityList(list, sortMode) {
  const copy = [...list];
  const tierRank = t => (t && t.includes("Tier 1") ? 1 : (t && t.includes("Tier 2") ? 2 : 3));
  copy.sort((a, b) => {
    if (sortMode === "region-asc") {
      const rComp = (a.region || "ZZZ").localeCompare(b.region || "ZZZ");
      if (rComp !== 0) return rComp;
      const tComp = tierRank(a.tier) - tierRank(b.tier);
      if (tComp !== 0) return tComp;
      return (a.name || "").localeCompare(b.name || "");
    }
    if (sortMode === "region-desc") {
      const rComp = (b.region || "").localeCompare(a.region || "");
      if (rComp !== 0) return rComp;
      return (a.name || "").localeCompare(b.name || "");
    }
    if (sortMode === "tier-asc") {
      const tComp = tierRank(a.tier) - tierRank(b.tier);
      if (tComp !== 0) return tComp;
      return (a.region || "").localeCompare(b.region || "");
    }
    if (sortMode === "name-asc") {
      return (a.name || "").localeCompare(b.name || "");
    }
    if (sortMode === "status-asc") {
      return (a.pipeline_status || "").localeCompare(b.pipeline_status || "");
    }
    if (sortMode === "fee-asc") {
      const fa = a.application_fee_rmb === 0 ? 0 : 500;
      const fb = b.application_fee_rmb === 0 ? 0 : 500;
      if (fa !== fb) return fa - fb;
      return (a.region || "").localeCompare(b.region || "");
    }
    return 0;
  });
  return copy;
}

// View Switchers (Toggle between Table and Live Logs in the same space)
function switchPortalsView(mode) {
  const tableBtn = document.getElementById("btn-view-portals-table");
  const logsBtn = document.getElementById("btn-view-portals-logs");
  const tableView = document.getElementById("portals-table-view");
  const toolbar = document.getElementById("portals-filter-toolbar");
  const logsView = document.getElementById("portals-logs-view");

  if (mode === "logs") {
    if (tableBtn) tableBtn.classList.remove("active");
    if (logsBtn) logsBtn.classList.add("active");
    if (tableView) tableView.classList.add("hidden");
    if (toolbar) toolbar.classList.add("hidden");
    if (logsView) logsView.classList.remove("hidden");
    renderInlineLogs();
  } else {
    if (logsBtn) logsBtn.classList.remove("active");
    if (tableBtn) tableBtn.classList.add("active");
    if (logsView) logsView.classList.add("hidden");
    if (toolbar) toolbar.classList.remove("hidden");
    if (tableView) tableView.classList.remove("hidden");
  }
}

function switchMatrixView(mode) {
  const tableBtn = document.getElementById("btn-view-matrix-table");
  const logsBtn = document.getElementById("btn-view-matrix-logs");
  const tableView = document.getElementById("matrix-table-view");
  const toolbar = document.getElementById("matrix-filter-toolbar");
  const logsView = document.getElementById("matrix-logs-view");

  if (mode === "logs") {
    if (tableBtn) tableBtn.classList.remove("active");
    if (logsBtn) logsBtn.classList.add("active");
    if (tableView) tableView.classList.add("hidden");
    if (toolbar) toolbar.classList.add("hidden");
    if (logsView) logsView.classList.remove("hidden");
    renderInlineLogs();
  } else {
    if (logsBtn) logsBtn.classList.remove("active");
    if (tableBtn) tableBtn.classList.add("active");
    if (logsView) logsView.classList.add("hidden");
    if (toolbar) toolbar.classList.remove("hidden");
    if (tableView) tableView.classList.remove("hidden");
  }
}

function switchFacultyView(mode) {
  const tableBtn = document.getElementById("btn-view-faculty-table");
  const logsBtn = document.getElementById("btn-view-faculty-logs");
  const tableView = document.getElementById("faculty-table-view");
  const toolbar = document.getElementById("faculty-filter-toolbar");
  const logsView = document.getElementById("faculty-logs-view");

  if (mode === "logs") {
    if (tableBtn) tableBtn.classList.remove("active");
    if (logsBtn) logsBtn.classList.add("active");
    if (tableView) tableView.classList.add("hidden");
    if (toolbar) toolbar.classList.add("hidden");
    if (logsView) logsView.classList.remove("hidden");
    renderInlineLogs();
  } else {
    if (logsBtn) logsBtn.classList.remove("active");
    if (tableBtn) tableBtn.classList.add("active");
    if (logsView) logsView.classList.add("hidden");
    if (toolbar) toolbar.classList.remove("hidden");
    if (tableView) tableView.classList.remove("hidden");
  }
}

function pushInlineLog(level, module, message) {
  const ts = new Date().toLocaleTimeString("en-GB", { hour12: false });
  inlineLogsBuffer.push({ timestamp: ts, level: level || "INFO", module: module || "Discovery", message: message });
  if (inlineLogsBuffer.length > 500) inlineLogsBuffer.shift();
  const counter = document.getElementById("live-log-counter");
  if (counter) counter.textContent = inlineLogsBuffer.length;
  renderInlineLogs();
}

function renderInlineLogs() {
  const stream1 = document.getElementById("inline-logs-stream");
  const stream2 = document.getElementById("matrix-logs-stream");
  const stream3 = document.getElementById("faculty-logs-stream");
  const kwInput = document.getElementById("inline-log-search");
  const kw = kwInput ? kwInput.value.toLowerCase().trim() : "";

  const filtered = inlineLogsBuffer.filter(item => {
    if (!kw) return true;
    return (item.message || "").toLowerCase().includes(kw) || (item.module || "").toLowerCase().includes(kw);
  });

  const html = filtered.length === 0
    ? `<div class="log-entry info">[SYSTEM] No matching log entries yet.</div>`
    : filtered.map(item => {
        let cls = "info";
        if (item.message.includes("✓") || item.level === "SUCCESS") cls = "found";
        else if (item.level === "WARNING" || item.message.includes("⚠") || item.message.includes("✗")) cls = "warning";
        else if (item.level === "ERROR") cls = "error";
        return `<div class="log-entry ${cls}">[${item.timestamp}] [${item.module}] ${item.message}</div>`;
      }).join("");

  if (stream1) {
    stream1.innerHTML = html;
    stream1.scrollTop = stream1.scrollHeight;
  }
  if (stream2) {
    stream2.innerHTML = html;
    stream2.scrollTop = stream2.scrollHeight;
  }
  if (stream3) {
    stream3.innerHTML = html;
    stream3.scrollTop = stream3.scrollHeight;
  }
}

function clearInlineLogs() {
  inlineLogsBuffer = [];
  const counter = document.getElementById("live-log-counter");
  if (counter) counter.textContent = "0";
  renderInlineLogs();
}

function setPortalsSort(mode) {
  const sel = document.getElementById("portal-sort-select");
  if (!sel) return;
  if (sel.value === "region-asc" && mode === "region-asc") {
    sel.value = "region-desc";
  } else {
    sel.value = mode;
  }
  applyPortalsTableFilter();
}

function renderMatchedEndpoints(universities) {
  lastDiscoveredUniversities = universities || [];
  populateRegionFilterDropdown("portal-region-filter", lastDiscoveredUniversities);
  applyPortalsTableFilter();

  const container = document.getElementById("discovered-endpoints-container");
  if (container) {
    if (lastDiscoveredUniversities.length > 0) container.classList.remove("hidden");
    else container.classList.add("hidden");
  }
}

function applyPortalsTableFilter() {
  const searchVal = (document.getElementById("portal-search-input")?.value || "").toLowerCase().trim();
  const regionVal = document.getElementById("portal-region-filter")?.value || "All";
  const tierVal = document.getElementById("portal-tier-filter")?.value || "All";
  const sortVal = document.getElementById("portal-sort-select")?.value || "region-asc";

  let filtered = (lastDiscoveredUniversities || []).filter(u => {
    if (regionVal !== "All" && u.region !== regionVal) return false;
    if (tierVal !== "All" && u.tier !== tierVal) return false;
    if (searchVal) {
      const m = (u.name || "").toLowerCase().includes(searchVal) ||
                (u.chinese_name || "").toLowerCase().includes(searchVal) ||
                (u.domain || "").toLowerCase().includes(searchVal) ||
                (u.region || "").toLowerCase().includes(searchVal);
      if (!m) return false;
    }
    return true;
  });

  filtered = sortUniversityList(filtered, sortVal);
  filteredPortalUniversities = filtered;

  const countEl = document.getElementById("matched-univ-count");
  if (countEl) countEl.textContent = `${filtered.length} / ${lastDiscoveredUniversities.length}`;

  const tbody = document.getElementById("matched-endpoints-tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  if (filtered.length === 0) {
    const showLbl = document.getElementById("portals-showing-label");
    if (showLbl) showLbl.textContent = "Showing 0 rows";
    tbody.innerHTML = `
      <tr>
        <td colspan="8" class="empty-state-cell">
          <div class="empty-state">
            <span class="empty-icon">🔎</span>
            <h4>No Matching Universities</h4>
            <p>Adjust your search text, region filter, or tier filter above.</p>
          </div>
        </td>
      </tr>
    `;
    return;
  }

  const limit = tableRowLimits.portals || 10;
  const visibleRows = filtered.slice(0, limit);
  const showLbl = document.getElementById("portals-showing-label");
  if (showLbl) {
    showLbl.textContent = `Showing ${visibleRows.length} of ${filtered.length} rows`;
  }

  visibleRows.forEach((u, idx) => {
    const tr = document.createElement("tr");
    const endpointsHtml = (u.department_endpoints || []).map(ep =>
      `<div style="margin-bottom: 2px;">
        <span class="badge version">${ep.name}</span>
        <a href="${ep.url}" target="_blank" style="font-family: var(--font-mono); font-size: 0.74rem; color: var(--primary); text-decoration: underline;">${ep.url} ↗</a>
      </div>`
    ).join("");

    tr.innerHTML = `
      <td class="col-num">${idx + 1}</td>
      <td><strong>${u.name}</strong></td>
      <td class="col-native"><span style="color: var(--text-secondary);">${u.chinese_name || "-"}</span></td>
      <td class="col-region"><span class="badge ${getRegionBadgeClass(u.region)}">${u.region || "National"}</span></td>
      <td class="col-tier"><span class="badge ${getTierBadgeClass(u.tier)}">${u.tier || "Tier 3 (Safety)"}</span></td>
      <td class="col-status">${getPipelineStatusBadge(u.pipeline_status)}</td>
      <td>${endpointsHtml}</td>
      <td class="col-action">
        <button class="btn btn-secondary btn-sm btn-interactive" onclick="resolveSingleUniversityDept('${u.domain}', this)" title="Live-probe homepage (院系设置) & WAF fallback to find real CS/AI department & supervisor page">🧭 Verify & Find Dept</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

async function resolveSingleUniversityDept(domain, btnEl) {
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.classList.add("btn-loading");
    btnEl.textContent = "⏳ Probing...";
  }
  const discipline = document.getElementById("filter-discipline")?.value || "Computer Science";
  pushInlineLog("INFO", "HomepageCrawler", `[${domain}] Live-probing homepage & locating '院系设置' (Schools & Departments) for ${discipline}...`);

  try {
    const res = await fetchWithAuth("/api/v1/discovery/resolve-departments", {
      method: "POST",
      body: JSON.stringify({ domains: [domain], discipline: discipline })
    });
    const updatedList = await res.json();
    if (updatedList && updatedList.length > 0) {
      const updated = updatedList[0];
      const idx = lastDiscoveredUniversities.findIndex(u => u.domain === domain);
      if (idx !== -1) lastDiscoveredUniversities[idx] = updated;
      const eps = (updated.department_endpoints || []).map(e => `${e.name}: ${e.url}`).join(" | ");
      pushInlineLog("SUCCESS", "HomepageCrawler", `[${updated.name}] ✓ Live Status: ${updated.pipeline_status} -> ${eps}`);
      applyPortalsTableFilter();
      loadUniversities();
    }
  } catch (err) {
    pushInlineLog("ERROR", "HomepageCrawler", `[${domain}] ✗ Error resolving department: ${err}`);
  } finally {
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.classList.remove("btn-loading");
      btnEl.textContent = "🧭 Verify & Find Dept";
    }
  }
}

async function resolveRealDepartmentsForVisible(triggerBtn = null) {
  const targets = (filteredPortalUniversities && filteredPortalUniversities.length > 0)
    ? filteredPortalUniversities.slice(0, 15)
    : (lastDiscoveredUniversities || []).slice(0, 15);

  if (targets.length === 0) {
    alert("Run discovery first so there are universities to resolve.");
    return;
  }

  const btn = triggerBtn || document.getElementById("btn-resolve-depts");
  if (btn) {
    btn.disabled = true;
    btn.classList.add("btn-loading");
    btn.textContent = `⏳ Live-Probing ${targets.length} Homepages...`;
  }

  startProgressAnimation("HOMEPAGE-FIRST DISCOVERY", `Live-probing ${targets.length} university homepages ('院系设置' -> CS/AI -> '导师队伍')...`);
  pushInlineLog("INFO", "BatchResolver", `Starting Live Homepage & WAF-Fallback Department Discovery for ${targets.length} universities...`);

  const discipline = document.getElementById("filter-discipline")?.value || "Computer Science";
  let done = 0;

  for (const u of targets) {
    done++;
    const pct = Math.round((done / targets.length) * 100);
    updateProgressStage(pct, `LIVE PROBING (${done}/${targets.length})`, `Inspecting ${u.name} (${u.website || u.domain})...`, `Checking 200 OK / Playwright WAF -> 院系设置 -> ${discipline}`);
    try {
      const res = await fetchWithAuth("/api/v1/discovery/resolve-departments", {
        method: "POST",
        body: JSON.stringify({ domains: [u.domain], discipline: discipline })
      });
      const updatedList = await res.json();
      if (updatedList && updatedList.length > 0) {
        const updated = updatedList[0];
        const idx = lastDiscoveredUniversities.findIndex(item => item.domain === u.domain);
        if (idx !== -1) lastDiscoveredUniversities[idx] = updated;
        const epText = (updated.department_endpoints || []).map(e => `${e.name} (${e.url})`).join(", ");
        pushInlineLog(
          updated.pipeline_status.includes("Found") || updated.pipeline_status.includes("Verified") ? "SUCCESS" : "WARNING",
          "HomepageCrawler",
          `[${done}/${targets.length}] [${updated.name}] -> ${updated.pipeline_status} | ${epText}`
        );
      }
    } catch (e) {
      pushInlineLog("ERROR", "HomepageCrawler", `[${done}/${targets.length}] [${u.name}] Failed: ${e}`);
    }
    applyPortalsTableFilter();
  }

  stopProgressAnimation(true, `Completed Homepage-First Department Resolution for ${targets.length} universities.`);
  loadUniversities();
  if (btn) {
    btn.disabled = false;
    btn.classList.remove("btn-loading");
    btn.textContent = "🧭 Resolve Real Dept Links";
  }
}

// Section 1: Execute Live Discovery with Active Button Feedback & Long-Running Progress
let progressTimer = null;
let progressSeconds = 0;

function startProgressAnimation(stageName, initialMessage) {
  const card = document.getElementById("operation-progress-card");
  if (!card) return;
  card.classList.remove("hidden");

  document.getElementById("tracker-stage-badge").textContent = stageName;
  document.getElementById("tracker-message").textContent = initialMessage;
  document.getElementById("tracker-bar-fill").style.width = "20%";
  document.getElementById("tracker-percentage").textContent = "20% In Progress";
  document.getElementById("tracker-details").textContent = "Querying live institutional databases...";

  progressSeconds = 0;
  clearInterval(progressTimer);
  progressTimer = setInterval(() => {
    progressSeconds++;
    const mins = String(Math.floor(progressSeconds / 60)).padStart(2, "0");
    const secs = String(progressSeconds % 60).padStart(2, "0");
    const timerEl = document.getElementById("tracker-elapsed");
    if (timerEl) timerEl.textContent = `${mins}:${secs}`;
  }, 1000);
}

function updateProgressStage(percent, stageName, message, details) {
  const fill = document.getElementById("tracker-bar-fill");
  const pct = document.getElementById("tracker-percentage");
  const msg = document.getElementById("tracker-message");
  const badge = document.getElementById("tracker-stage-badge");
  const det = document.getElementById("tracker-details");

  if (fill) fill.style.width = `${percent}%`;
  if (pct) pct.textContent = `${percent}% Completed`;
  if (badge) badge.textContent = stageName;
  if (msg) msg.textContent = message;
  if (det) det.textContent = details;
}

function stopProgressAnimation(isSuccess = true, summary = "Completed") {
  clearInterval(progressTimer);
  const fill = document.getElementById("tracker-bar-fill");
  const pct = document.getElementById("tracker-percentage");
  const msg = document.getElementById("tracker-message");

  if (fill) fill.style.width = isSuccess ? "100%" : "0%";
  if (pct) pct.textContent = isSuccess ? "100% Completed" : "Interrupted";
  if (msg) msg.textContent = summary;
}

async function refreshActiveProgress(btnEl = null) {
  const btn = btnEl || (typeof event !== "undefined" && event ? event.target : null);
  if (btn) {
    btn.classList.add("btn-loading");
    btn.textContent = "↻ Refreshing...";
  }
  loadAllData();
  const kwInput = document.getElementById("filter-keyword");
  if (kwInput && kwInput.value.trim()) {
    await runRegionalFilter();
  }
  setTimeout(() => {
    if (btn) {
      btn.classList.remove("btn-loading");
      btn.textContent = "↻ Refresh Feed";
    }
  }, 600);
}

async function runRegionalFilter(triggerBtn = null) {
  const btn = document.getElementById("btn-run-discovery");
  const spinner = document.getElementById("btn-discovery-spinner");
  const textEl = document.getElementById("btn-discovery-text");

  // Visual active button feedback & immediate skeleton shimmer
  if (btn) {
    btn.disabled = true;
    btn.classList.add("btn-loading");
  }
  if (triggerBtn && triggerBtn !== btn) {
    triggerBtn.disabled = true;
    triggerBtn.classList.add("btn-loading");
  }
  if (spinner) spinner.classList.remove("hidden");
  if (textEl) textEl.textContent = "Querying Live Registries & Resolving...";

  const container = document.getElementById("discovered-endpoints-container");
  if (container) container.classList.remove("hidden");
  renderTableSkeleton("matched-endpoints-tbody", 8, 8);

  const sourceNames = {
    combined: "Combined Triple-Check (MOE Master's Registry + Wikidata + 985/211)",
    wikidata: "Wikidata Live SPARQL Registry",
    moe: "China MOE Official Master's-Granting Registry (硕士点高校)"
  };
  const activeSourceLabel = sourceNames[activeDiscoverySource] || activeDiscoverySource.toUpperCase();

  startProgressAnimation("STAGE 1: LIVE QUERY", `Querying ${activeSourceLabel}...`);

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
    keyword: keyword || null,
    source: activeDiscoverySource
  };

  pushInlineLog("INFO", "Discovery", `Executing ${activeSourceLabel} query (Regions: ${selectedRegions.join(", ")}, Tier: ${tier}, Keyword: ${keyword || "None"})...`);

  try {
    updateProgressStage(45, "STAGE 2: FILTER & DEDUP", "Filtering Master's-granting .edu.cn domains & excluding 3-year vocational colleges...", "Cross-checking MOE Project 985, 211 & Master's registries");

    const res = await fetchWithAuth("/api/v1/discovery/filter", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    
    updateProgressStage(85, "STAGE 3: PERSISTING PORTALS", "Attaching candidate homepages (Pending Live Check) & syncing MongoDB...", "Syncing Feasibility Matrix");

    const universities = await res.json();
    lastDiscoveredUniversities = universities;

    const t1 = universities.filter(u => u.tier && u.tier.includes("Tier 1")).length;
    const t2 = universities.filter(u => u.tier && u.tier.includes("Tier 2")).length;
    const t3 = universities.length - t1 - t2;

    pushInlineLog("SUCCESS", "Discovery", `✓ Discovered ${universities.length} Master's-granting .edu.cn universities via ${activeSourceLabel} (Tier 1 Dream: ${t1}, Tier 2 Target: ${t2}, Tier 3 Safety: ${t3}). Status set to Pending Live Check.`);

    stopProgressAnimation(true, `Successfully discovered ${universities.length} Master's-granting Chinese universities (Tier 1: ${t1}, Tier 2: ${t2}, Tier 3: ${t3}).`);
    renderMatchedEndpoints(universities);
    // Automatically sync Section 02 Feasibility & Scholarship Matrix!
    await loadUniversities();
  } catch (err) {
    pushInlineLog("ERROR", "Discovery", `✗ Discovery encountered an error: ${err}`);
    stopProgressAnimation(false, "Discovery encountered an error: " + err);
    alert("Error discovering universities: " + err);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.classList.remove("btn-loading");
    }
    if (triggerBtn && triggerBtn !== btn) {
      triggerBtn.disabled = false;
      triggerBtn.classList.remove("btn-loading");
    }
    if (spinner) spinner.classList.add("hidden");
    if (textEl) textEl.textContent = "🔍 Execute Live Discovery & Resolve Endpoints";
  }
}

function clearDiscoveredUniversities() {
  lastDiscoveredUniversities = [];
  filteredPortalUniversities = [];
  renderMatchedEndpoints([]);
  const card = document.getElementById("operation-progress-card");
  if (card) card.classList.add("hidden");
}

// Section 1: Pre-Run Cost Gate
async function prepareEstimateForMatched() {
  if (!lastDiscoveredUniversities || lastDiscoveredUniversities.length === 0) {
    alert("No universities matched. Run search first.");
    return;
  }

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

async function calculateCostEstimate() {
  const text = document.getElementById("intake-urls").value.trim();
  const urls = text.split("\n").map(u => u.trim()).filter(u => u.length > 0);
  
  if (urls.length === 0) {
    alert("Please provide at least one target department URL (.edu.cn).");
    return;
  }

  const endpoints = urls.map(u => ({
    name: "Target Department",
    url: u
  }));

  try {
    const res = await fetchWithAuth("/api/v1/discovery/estimate", {
      method: "POST",
      body: JSON.stringify(endpoints)
    });
    const est = await res.json();

    const univEl = document.getElementById("est-univs");
    if (univEl) univEl.textContent = "Custom Intake";
    document.getElementById("est-depts").textContent = est.total_target_departments;
    document.getElementById("est-faculty").textContent = est.estimated_faculty_count;
    document.getElementById("est-tokens").textContent = est.estimated_gemini_tokens.toLocaleString();
    document.getElementById("est-runtime").textContent = est.estimated_runtime_seconds + "s";
    
    const card = document.getElementById("cost-estimate-card");
    if (card) card.classList.remove("hidden");
    document.getElementById("gate-status-text").textContent = "LOCKED (Approval Required)";
  } catch (err) {
    alert("Error calculating estimate: " + err);
  }
}

// Approve Gate & Start Parallel Extraction with active visual feedback
async function approveCostGate() {
  const btn = document.getElementById("btn-approve-gate");
  const spinner = document.getElementById("btn-approve-spinner");
  const textEl = document.getElementById("btn-approve-text");

  if (btn) {
    btn.disabled = true;
    btn.classList.add("btn-loading");
  }
  if (spinner) spinner.classList.remove("hidden");
  if (textEl) textEl.textContent = "Crawling Official Department Portals...";

  startProgressAnimation("STAGE 4: CRAWLING ROSTER", "Launching asynchronous scraping workers for Master's supervisors (硕导)...");

  try {
    const res = await fetchWithAuth("/api/v1/discovery/approve", { method: "POST" });
    const est = await res.json();
    if (est.is_approved) {
      document.getElementById("gate-status-text").textContent = "UNLOCKED & APPROVED";
      
      if (lastDiscoveredUniversities && lastDiscoveredUniversities.length > 0) {
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

      stopProgressAnimation(true, "Supervisor harvesting completed. Verified profiles saved to database.");
      loadFaculty();
    }
  } catch (err) {
    stopProgressAnimation(false, "Scraping failed: " + err);
    alert("Error approving cost gate: " + err);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.classList.remove("btn-loading");
    }
    if (spinner) spinner.classList.add("hidden");
    if (textEl) textEl.textContent = "✓ Approve Gate & Launch Parallel Harvesters";
  }
}

// Section 4: Dynamic Prompts & AI Directives (MongoDB Persisted)
let loadedPrompts = [];
let selectedPrompt = null;

async function loadPrompts() {
  try {
    const res = await fetchWithAuth("/api/v1/prompts");
    loadedPrompts = await res.json();
    const select = document.getElementById("select-prompt-record");
    if (!select) return;
    select.innerHTML = "";

    loadedPrompts.forEach(p => {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = `[v${p.version}] ${p.is_active ? '★ ACTIVE: ' : ''}${p.title} (${p.stage})`;
      select.appendChild(opt);
    });

    if (loadedPrompts.length > 0) {
      const activeOne = loadedPrompts.find(p => p.is_active) || loadedPrompts[0];
      select.value = activeOne.id;
      onPromptSelected();
    }
  } catch (err) {
    console.error("Error loading prompts:", err);
  }
}

function onPromptSelected() {
  const select = document.getElementById("select-prompt-record");
  if (!select) return;
  const promptId = select.value;
  selectedPrompt = loadedPrompts.find(p => p.id === promptId);

  if (selectedPrompt) {
    document.getElementById("prompt-id-display").textContent = selectedPrompt.id;
    document.getElementById("prompt-stage-display").textContent = selectedPrompt.stage;
    
    const activeBadge = document.getElementById("prompt-active-display");
    if (activeBadge) {
      if (selectedPrompt.is_active) {
        activeBadge.className = "badge window-open";
        activeBadge.textContent = "ACTIVE";
      } else {
        activeBadge.className = "badge window-closed";
        activeBadge.textContent = "INACTIVE";
      }
    }

    document.getElementById("prompt-version-display").textContent = `v${selectedPrompt.version}`;
    document.getElementById("prompt-title-input").value = selectedPrompt.title;
    document.getElementById("prompt-system-text").value = selectedPrompt.system_prompt;
    document.getElementById("prompt-template-text").value = selectedPrompt.template_text;

    // Render Variable Chips
    const chipsContainer = document.getElementById("prompt-variable-chips");
    if (chipsContainer) {
      chipsContainer.innerHTML = "";
      (selectedPrompt.variables || []).forEach(v => {
        const chip = document.createElement("span");
        chip.className = "prompt-chip";
        chip.textContent = `{{${v}}}`;
        chip.title = "Click to insert into template";
        chip.onclick = () => insertPromptVar(v);
        chipsContainer.appendChild(chip);
      });
    }
  }
}

function insertPromptVar(varName) {
  const textarea = document.getElementById("prompt-template-text");
  if (!textarea) return;
  const token = `{{${varName}}}`;
  const start = textarea.selectionStart;
  const end = textarea.selectionEnd;
  const text = textarea.value;
  textarea.value = text.substring(0, start) + token + text.substring(end);
  textarea.focus();
  textarea.selectionStart = textarea.selectionEnd = start + token.length;
}

async function savePromptChanges() {
  if (!selectedPrompt) return alert("Select a prompt first.");
  const title = document.getElementById("prompt-title-input").value.trim();
  const systemPrompt = document.getElementById("prompt-system-text").value.trim();
  const templateText = document.getElementById("prompt-template-text").value.trim();

  try {
    const res = await fetchWithAuth(`/api/v1/prompts/${selectedPrompt.id}`, {
      method: "PUT",
      body: JSON.stringify({
        title: title,
        system_prompt: systemPrompt,
        template_text: templateText
      })
    });
    if (!res.ok) {
      alert("Failed to update prompt.");
      return;
    }
    const updated = await res.json();
    alert(`Success! Saved prompt '${updated.title}' to MongoDB (Version v${updated.version}).`);
    loadPrompts();
  } catch (err) {
    alert("Error saving prompt: " + err);
  }
}

async function activateCurrentPrompt() {
  if (!selectedPrompt) return alert("Select a prompt first.");
  try {
    const res = await fetchWithAuth(`/api/v1/prompts/${selectedPrompt.id}/activate`, {
      method: "POST"
    });
    const updated = await res.json();
    alert(`Prompt '${updated.title}' is now ACTIVE for stage '${updated.stage}'.`);
    loadPrompts();
  } catch (err) {
    alert("Activation error: " + err);
  }
}

async function createNewPromptModal() {
  const promptId = prompt("Enter unique slug ID for new prompt (e.g. cs-outreach-2026):");
  if (!promptId) return;
  const title = prompt("Enter Title for this prompt:", "Custom Cold Outreach Prompt");
  if (!title) return;

  const newPrompt = {
    id: promptId.toLowerCase().replace(/[^a-z0-9_-]/g, "-"),
    title: title,
    stage: selectedPrompt ? selectedPrompt.stage : "outreach_synthesis",
    system_prompt: selectedPrompt ? selectedPrompt.system_prompt : "You are an expert academic advisor.",
    template_text: selectedPrompt ? selectedPrompt.template_text : "Target: {{professor_name}}\nUniversity: {{university}}",
    variables: selectedPrompt ? selectedPrompt.variables : ["professor_name", "university"],
    is_active: false,
    version: 1
  };

  try {
    const res = await fetchWithAuth("/api/v1/prompts", {
      method: "POST",
      body: JSON.stringify(newPrompt)
    });
    if (res.ok) {
      alert(`Created prompt '${newPrompt.id}' in MongoDB!`);
      loadPrompts();
    }
  } catch (err) {
    alert("Error creating prompt: " + err);
  }
}

// Section 2: Universities Directory (With Live Search, Region/Tier Filter, Live Sort & Color Badges)
function setMatrixSort(mode) {
  const sel = document.getElementById("matrix-sort-select");
  if (!sel) return;
  if (sel.value === "region-asc" && mode === "region-asc") {
    sel.value = "region-desc";
  } else {
    sel.value = mode;
  }
  applyMatrixTableFilter();
}

async function loadUniversities(triggerBtn = null) {
  let prevText = "";
  if (triggerBtn) {
    prevText = triggerBtn.textContent;
    triggerBtn.disabled = true;
    triggerBtn.classList.add("btn-loading");
    triggerBtn.textContent = "⏳ Loading...";
  }
  renderTableSkeleton("universities-tbody", 10, 8);
  try {
    const res = await fetchWithAuth("/api/v1/discovery/universities");
    allDirectoryUniversities = await res.json();
    populateRegionFilterDropdown("matrix-region-filter", allDirectoryUniversities);
    populateSupervisorPoolControls();
    applyMatrixTableFilter();
  } catch (err) {
    console.error("Error loading universities:", err);
  } finally {
    if (triggerBtn) {
      triggerBtn.disabled = false;
      triggerBtn.classList.remove("btn-loading");
      triggerBtn.textContent = prevText || "↻ Refresh Directory";
    }
  }
}

function scrollToSupervisorPool() {
  const portalRegion = document.getElementById("portal-region-filter")?.value;
  const matrixRegion = document.getElementById("matrix-region-filter")?.value;
  const supRegSelect = document.getElementById("sup-region-select");
  if (supRegSelect) {
    if (portalRegion && portalRegion !== "All") supRegSelect.value = portalRegion;
    else if (matrixRegion && matrixRegion !== "All") supRegSelect.value = matrixRegion;
    onSupervisorRegionChange();
  }
  const sec = document.getElementById("tab-faculty");
  if (sec) sec.scrollIntoView({ behavior: "smooth" });
}

function populateSupervisorPoolControls() {
  const regSelect = document.getElementById("sup-region-select");
  if (!regSelect) return;

  const sourceList = (allDirectoryUniversities && allDirectoryUniversities.length > 0)
    ? allDirectoryUniversities
    : (lastDiscoveredUniversities || []);

  const prevReg = regSelect.value || "All";
  const counts = {};
  sourceList.forEach(u => {
    const r = u.region || "National";
    counts[r] = (counts[r] || 0) + 1;
  });

  const sortedRegions = Object.keys(counts).sort();
  regSelect.innerHTML = `<option value="All">All Regions (${sourceList.length} Universities)</option>`;
  sortedRegions.forEach(r => {
    const opt = document.createElement("option");
    opt.value = r;
    opt.textContent = `${r} (${counts[r]} Universities)`;
    regSelect.appendChild(opt);
  });

  if (sortedRegions.includes(prevReg)) {
    regSelect.value = prevReg;
  }
  onSupervisorRegionChange();
}

function onSupervisorRegionChange() {
  const regSelect = document.getElementById("sup-region-select");
  const tierSelect = document.getElementById("sup-tier-select");
  const univSelect = document.getElementById("sup-univ-select");
  const countBadge = document.getElementById("sup-region-univ-count-badge");
  if (!regSelect || !univSelect) return;

  const selectedReg = regSelect.value || "All";
  const selectedTier = tierSelect ? tierSelect.value : "All";

  const sourceList = (allDirectoryUniversities && allDirectoryUniversities.length > 0)
    ? allDirectoryUniversities
    : (lastDiscoveredUniversities || []);

  let regionUnivs = sourceList.filter(u => {
    if (selectedReg !== "All" && u.region !== selectedReg) return false;
    if (selectedTier !== "All" && u.tier !== selectedTier) return false;
    return true;
  });

  regionUnivs = sortUniversityList(regionUnivs, "tier-asc");

  if (countBadge) {
    countBadge.textContent = `${regionUnivs.length} Universities in ${selectedReg === "All" ? "All Regions" : selectedReg}`;
  }

  univSelect.innerHTML = `<option value="ALL_IN_REGION" selected>★ All Universities in ${selectedReg === "All" ? "Selected Filter" : selectedReg} (${regionUnivs.length} Universities)</option>`;
  regionUnivs.forEach(u => {
    const opt = document.createElement("option");
    opt.value = u.domain;
    const shortTier = u.tier && u.tier.includes("Tier 1") ? "[985 Dream]" : (u.tier && u.tier.includes("Tier 2") ? "[211 Target]" : "[Safety]");
    opt.textContent = `${shortTier} ${u.name} ${u.chinese_name ? "(" + u.chinese_name + ")" : ""} — ${u.domain}`;
    univSelect.appendChild(opt);
  });

  updateSupervisorSelectionSummary();
}

function updateSupervisorSelectionSummary() {
  const univSelect = document.getElementById("sup-univ-select");
  const selBadge = document.getElementById("sup-selected-univ-badge");
  if (!univSelect || !selBadge) return;

  const selectedOpts = Array.from(univSelect.selectedOptions).map(o => o.value);
  if (selectedOpts.includes("ALL_IN_REGION") || selectedOpts.length === 0) {
    const totalInList = Math.max(0, univSelect.options.length - 1);
    selBadge.textContent = `All (${totalInList}) Selected`;
  } else {
    selBadge.textContent = `${selectedOpts.length} Specific Selected`;
  }
}

async function launchSupervisorWorkerPool() {
  const regSelect = document.getElementById("sup-region-select");
  const tierSelect = document.getElementById("sup-tier-select");
  const univSelect = document.getElementById("sup-univ-select");
  const workerSelect = document.getElementById("sup-worker-count");
  const discSelect = document.getElementById("sup-discipline-select");

  const selectedReg = regSelect ? regSelect.value : "All";
  const selectedTier = tierSelect ? tierSelect.value : "All";
  const workerCount = parseInt(workerSelect ? workerSelect.value : "5", 10) || 5;
  const discipline = discSelect ? discSelect.value : "Computer Science";

  const sourceList = (allDirectoryUniversities && allDirectoryUniversities.length > 0)
    ? allDirectoryUniversities
    : (lastDiscoveredUniversities || []);

  let candidateUnivs = sourceList.filter(u => {
    if (selectedReg !== "All" && u.region !== selectedReg) return false;
    if (selectedTier !== "All" && u.tier !== selectedTier) return false;
    return true;
  });

  const selectedDomains = univSelect ? Array.from(univSelect.selectedOptions).map(o => o.value) : ["ALL_IN_REGION"];
  if (!selectedDomains.includes("ALL_IN_REGION") && selectedDomains.length > 0) {
    candidateUnivs = candidateUnivs.filter(u => selectedDomains.includes(u.domain));
  }

  if (candidateUnivs.length === 0) {
    alert("No universities match the current Region/University selection. Run discovery or select a valid region first.");
    return;
  }

  const btn = document.getElementById("btn-launch-sup-workers");
  const spinner = document.getElementById("btn-sup-spinner");
  const textEl = document.getElementById("btn-sup-text");
  const progCard = document.getElementById("sup-worker-progress-card");
  const progBadge = document.getElementById("sup-tracker-badge");
  const progTitle = document.getElementById("sup-tracker-title");
  const progStats = document.getElementById("sup-tracker-stats");
  const progBar = document.getElementById("sup-tracker-bar");
  const progPct = document.getElementById("sup-tracker-pct");
  const progDetail = document.getElementById("sup-tracker-detail");

  if (btn) {
    btn.disabled = true;
    btn.classList.add("btn-loading");
  }
  if (spinner) spinner.classList.remove("hidden");
  if (textEl) textEl.textContent = `Running ${workerCount} Parallel Worker(s)...`;
  if (progCard) progCard.classList.remove("hidden");

  const totalUnivs = candidateUnivs.length;
  let completedUnivs = 0;
  let totalHarvestedCount = 0;

  pushInlineLog("INFO", "WorkerPool", `🚀 Launching ${workerCount} parallel crawler worker(s) across ${totalUnivs} university(ies) in ${selectedReg} for ${discipline}...`);

  // Process in batches of workerCount so the UI progress bar updates smoothly in real time
  for (let i = 0; i < totalUnivs; i += workerCount) {
    const chunk = candidateUnivs.slice(i, i + workerCount);
    const chunkNames = chunk.map(u => u.name).join(", ");
    const pct = Math.max(5, Math.round((completedUnivs / totalUnivs) * 100));

    if (progBadge) progBadge.textContent = `${workerCount} PARALLEL WORKERS ACTIVE`;
    if (progTitle) progTitle.textContent = `Crawling batch (${completedUnivs + 1}–${Math.min(completedUnivs + chunk.length, totalUnivs)} of ${totalUnivs} in ${selectedReg}): ${chunkNames}`;
    if (progBar) progBar.style.width = `${pct}%`;
    if (progPct) progPct.textContent = `${pct}% (${completedUnivs} / ${totalUnivs} Universities)`;
    if (progDetail) progDetail.textContent = `Resolving 院系设置 -> ${discipline} -> 师资队伍 / 导师队伍 & verifying 硕导 profiles...`;

    const batchTargets = chunk.map(u => ({
      university_name: u.name,
      domain: u.domain,
      department_name: `School of ${discipline}`,
      department_urls: (u.department_endpoints && u.department_endpoints.length > 0)
        ? u.department_endpoints.map(ep => ep.url)
        : [u.website || `https://www.${u.domain}/`]
    }));

    try {
      const res = await fetchWithAuth("/api/v1/professors/harvest-batch", {
        method: "POST",
        body: JSON.stringify({
          targets: batchTargets,
          max_workers: workerCount,
          auto_resolve_homepage: true,
          discipline: discipline
        })
      });
      if (res.ok) {
        const harvestedBatch = await res.json();
        totalHarvestedCount += harvestedBatch.length;
        if (progStats) progStats.textContent = `${totalHarvestedCount} New Supervisors Found`;
      }
    } catch (err) {
      pushInlineLog("ERROR", "WorkerPool", `Batch worker error on (${chunkNames}): ${err}`);
    }

    completedUnivs += chunk.length;
    await loadFaculty();
  }

  if (progBadge) progBadge.textContent = `EXTRACTION COMPLETED`;
  if (progTitle) progTitle.textContent = `Finished crawling ${totalUnivs} university(ies) in ${selectedReg} using ${workerCount} parallel workers.`;
  if (progBar) progBar.style.width = `100%`;
  if (progPct) progPct.textContent = `100% (${totalUnivs} / ${totalUnivs} Universities Completed)`;
  if (progDetail) progDetail.textContent = `All verified Master's/PhD supervisors persisted to MongoDB.`;

  pushInlineLog("SUCCESS", "WorkerPool", `✓ Completed parallel supervisor extraction across ${totalUnivs} university(ies).`);
  await loadUniversities();
  await loadFaculty();

  if (btn) {
    btn.disabled = false;
    btn.classList.remove("btn-loading");
  }
  if (spinner) spinner.classList.add("hidden");
  if (textEl) textEl.textContent = "🚀 Launch Parallel Supervisor Workers";
}

function applyMatrixTableFilter() {
  const tbody = document.getElementById("universities-tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  const searchVal = (document.getElementById("matrix-search-input")?.value || "").toLowerCase().trim();
  const regionVal = document.getElementById("matrix-region-filter")?.value || "All";
  const tierVal = document.getElementById("matrix-tier-filter")?.value || "All";
  const sortVal = document.getElementById("matrix-sort-select")?.value || "region-asc";

  if (!allDirectoryUniversities || allDirectoryUniversities.length === 0) {
    const countEl = document.getElementById("matrix-univ-count");
    if (countEl) countEl.textContent = "0";
    tbody.innerHTML = `
      <tr>
        <td colspan="10" class="empty-state-cell">
          <div class="empty-state">
            <span class="empty-icon">🏛️</span>
            <h4>Database Directory Empty</h4>
            <p>No universities saved in MongoDB yet. Run discovery above to index institutions.</p>
          </div>
        </td>
      </tr>
    `;
    return;
  }

  let filtered = allDirectoryUniversities.filter(u => {
    if (regionVal !== "All" && u.region !== regionVal) return false;
    if (tierVal !== "All" && u.tier !== tierVal) return false;
    if (searchVal) {
      const m = (u.name || "").toLowerCase().includes(searchVal) ||
                (u.chinese_name || "").toLowerCase().includes(searchVal) ||
                (u.domain || "").toLowerCase().includes(searchVal) ||
                (u.region || "").toLowerCase().includes(searchVal) ||
                (u.feasibility_notes || "").toLowerCase().includes(searchVal);
      if (!m) return false;
    }
    return true;
  });

  filtered = sortUniversityList(filtered, sortVal);

  const countEl = document.getElementById("matrix-univ-count");
  if (countEl) countEl.textContent = `${filtered.length} / ${allDirectoryUniversities.length}`;

  if (filtered.length === 0) {
    const showLbl = document.getElementById("matrix-showing-label");
    if (showLbl) showLbl.textContent = "Showing 0 rows";
    tbody.innerHTML = `
      <tr>
        <td colspan="10" class="empty-state-cell">
          <div class="empty-state">
            <span class="empty-icon">🔎</span>
            <h4>No Matching Records</h4>
            <p>Try clearing or changing your search keyword, region, or tier filter.</p>
          </div>
        </td>
      </tr>
    `;
    return;
  }

  const limit = tableRowLimits.matrix || 10;
  const visibleRows = filtered.slice(0, limit);
  const showLbl = document.getElementById("matrix-showing-label");
  if (showLbl) {
    showLbl.textContent = `Showing ${visibleRows.length} of ${filtered.length} rows`;
  }

  visibleRows.forEach((u, idx) => {
    const tr = document.createElement("tr");

    // Accurate National Classification (Never fake 'Top 50'!)
    let natClassHtml = `<span class="badge badge-region-default">Provincial Accredited</span>`;
    if (u.cs_ranking) {
      natClassHtml = `<span class="badge badge-tier-1">CS Rank #${u.cs_ranking}</span>`;
    } else if (u.is_project_985) {
      natClassHtml = `<span class="badge badge-tier-1">Project 985 / C9 Elite</span>`;
    } else if (u.is_project_211) {
      natClassHtml = `<span class="badge badge-tier-2">Project 211 / Key Nat.</span>`;
    }

    // Accurate Application Fee (0 RMB Waived only if verified; otherwise 400-800 RMB Standard Est.)
    let feeHtml = `<span class="badge badge-fee-standard" title="Most Chinese universities charge 400–800 RMB processing fee unless waived via CSC or university policy">${u.fee_note || "400–800 RMB (Standard Est.)"}</span>`;
    if (u.application_fee_rmb === 0) {
      feeHtml = `<span class="badge badge-fee-waived">0 RMB (Fee Waived)</span>`;
    } else if (typeof u.application_fee_rmb === "number" && u.application_fee_rmb > 0) {
      feeHtml = `<span class="badge badge-fee-standard">${u.application_fee_rmb} RMB</span>`;
    }

    const officialSite = u.website || `https://www.${u.domain}/`;

    tr.innerHTML = `
      <td class="col-num">${idx + 1}</td>
      <td><strong>${u.name}</strong></td>
      <td class="col-native">${u.chinese_name || "-"}</td>
      <td class="col-region"><span class="badge ${getRegionBadgeClass(u.region)}">${u.region || "National"}</span></td>
      <td><a href="${officialSite}" target="_blank" style="font-family: var(--font-mono); font-size: 0.75rem; color: var(--primary);">${u.domain} ↗</a></td>
      <td>${natClassHtml}</td>
      <td class="col-tier"><span class="badge ${getTierBadgeClass(u.tier)}">${u.tier}</span></td>
      <td style="font-size: 0.75rem;">${(u.scholarships_available || []).join(", ") || "Provincial / Presidential"}</td>
      <td>${feeHtml}</td>
      <td style="max-width: 260px; font-size: 0.76rem;">
        <div style="margin-bottom: 2px;">${getPipelineStatusBadge(u.pipeline_status)}</div>
        <span style="color: var(--text-secondary);">${u.feasibility_notes || "Accredited institution"}</span>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

// Section 3: Faculty Roster
let allFacultyRecords = [];

async function loadFaculty(triggerBtn = null) {
  let prevText = "";
  if (triggerBtn) {
    prevText = triggerBtn.textContent;
    triggerBtn.disabled = true;
    triggerBtn.classList.add("btn-loading");
    triggerBtn.textContent = "⏳ Loading...";
  }
  renderTableSkeleton("faculty-tbody", 9, 6);
  try {
    const res = await fetchWithAuth("/api/v1/professors");
    const faculty = await res.json();
    allFacultyRecords = Array.isArray(faculty) ? faculty : [];

    const totalEl = document.getElementById("faculty-total-count");
    if (totalEl) totalEl.textContent = allFacultyRecords.length;

    // Populate unique universities dropdown in faculty filter toolbar
    const univFilterEl = document.getElementById("faculty-univ-filter");
    if (univFilterEl) {
      const currentVal = univFilterEl.value;
      const univCounts = {};
      allFacultyRecords.forEach(f => {
        const u = f.university || "Unknown";
        univCounts[u] = (univCounts[u] || 0) + 1;
      });
      const sortedUnivs = Object.keys(univCounts).sort((a, b) => a.localeCompare(b));
      univFilterEl.innerHTML = `<option value="All">All Harvested Universities (${sortedUnivs.length})</option>`;
      sortedUnivs.forEach(u => {
        const opt = document.createElement("option");
        opt.value = u;
        opt.textContent = `${u} (${univCounts[u]})`;
        univFilterEl.appendChild(opt);
      });
      if (sortedUnivs.includes(currentVal)) {
        univFilterEl.value = currentVal;
      }
    }

    applyFacultyTableFilter();
  } catch (err) {
    console.error("Error loading faculty:", err);
  } finally {
    if (triggerBtn) {
      triggerBtn.disabled = false;
      triggerBtn.classList.remove("btn-loading");
      triggerBtn.textContent = prevText || "↻ Refresh Roster";
    }
  }
}

function resetFacultyTableFilter() {
  const searchEl = document.getElementById("faculty-search-input");
  const univEl = document.getElementById("faculty-univ-filter");
  const qualEl = document.getElementById("faculty-qual-filter");
  if (searchEl) searchEl.value = "";
  if (univEl) univEl.value = "All";
  if (qualEl) qualEl.value = "All";
  applyFacultyTableFilter();
}

function applyFacultyTableFilter() {
  const tbody = document.getElementById("faculty-tbody");
  if (!tbody) return;

  const query = (document.getElementById("faculty-search-input")?.value || "").trim().toLowerCase();
  const univFilter = document.getElementById("faculty-univ-filter")?.value || "All";
  const qualFilter = document.getElementById("faculty-qual-filter")?.value || "All";

  const filtered = allFacultyRecords.filter(f => {
    if (univFilter !== "All" && univFilter !== "ALL" && f.university !== univFilter) return false;
    if (qualFilter !== "All" && qualFilter !== "ALL" && !(f.qualification || "").toLowerCase().includes(qualFilter.toLowerCase())) return false;
    if (query) {
      const hay = `${f.name || ""} ${f.native_name || ""} ${f.university || ""} ${f.department || ""} ${f.email || ""} ${(f.research_areas || []).join(" ")}`.toLowerCase();
      if (!hay.includes(query)) return false;
    }
    return true;
  });

  const countBadge = document.getElementById("faculty-filter-count");
  if (countBadge) {
    countBadge.textContent = `${filtered.length} / ${allFacultyRecords.length} Records`;
  }

  tbody.innerHTML = "";

  if (!filtered || filtered.length === 0) {
    const showLbl = document.getElementById("faculty-showing-label");
    if (showLbl) showLbl.textContent = "Showing 0 rows";
    tbody.innerHTML = `
      <tr>
        <td colspan="9" class="empty-state-cell">
          <div class="empty-state">
            <span class="empty-icon">👨‍🏫</span>
            <h4>${allFacultyRecords.length === 0 ? "No Faculty Records Harvested Yet" : "No Matching Supervisors Found"}</h4>
            <p>${allFacultyRecords.length === 0
              ? "Select a Target Region, Universities, and Worker Pool Concurrency above, then click '🚀 Launch Parallel Supervisor Workers' to extract verified graduate supervisors."
              : "Adjust your search filter, university filter, or qualification filter above."}</p>
          </div>
        </td>
      </tr>
    `;
    return;
  }

  const limit = tableRowLimits.faculty || 10;
  const visibleRows = filtered.slice(0, limit);
  const showLbl = document.getElementById("faculty-showing-label");
  if (showLbl) {
    showLbl.textContent = `Showing ${visibleRows.length} of ${filtered.length} rows`;
  }

  visibleRows.forEach((f, idx) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="col-num">${idx + 1}</td>
      <td><strong>${f.name}</strong> ${f.native_name ? '(' + f.native_name + ')' : ''}</td>
      <td>${f.university}</td>
      <td>${f.department}</td>
      <td><span class="badge window-open">${f.qualification}</span></td>
      <td><code>${f.email}</code></td>
      <td>${(f.research_areas || []).join(", ")}</td>
      <td><code title="${f.content_hash}">${f.content_hash ? f.content_hash.substring(0, 8) + '...' : '-'}</code></td>
      <td><a href="${f.source_url}" target="_blank" style="color: var(--primary); font-weight: 600;">Profile ↗</a></td>
    `;
    tbody.appendChild(tr);
  });
}

// Section 4: Email Review Workspace
async function loadDrafts() {
  try {
    const res = await fetchWithAuth("/api/v1/drafts");
    currentDrafts = await res.json();
    const select = document.getElementById("select-draft");
    if (!select) return;
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
  if (countEl) {
    countEl.textContent = words;
    if (words > 200) {
      countEl.style.color = "var(--accent-red)";
    } else {
      countEl.style.color = "var(--accent-green)";
    }
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
    loadDispatchQueue();
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

// Section 5: Dispatch Queue
async function loadDispatchQueue() {
  try {
    const res = await fetchWithAuth("/api/v1/dispatch/queue");
    const queue = await res.json();
    const countEl = document.getElementById("approved-count");
    if (countEl) countEl.textContent = queue.length;
    
    const tbody = document.getElementById("dispatch-tbody");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (!queue || queue.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="7" class="empty-state-cell">
            <div class="empty-state">
              <span class="empty-icon">🚀</span>
              <h4>Dispatch Queue Empty</h4>
              <p>No outreach drafts currently in APPROVED state. Review and approve drafts in Section 04.</p>
            </div>
          </td>
        </tr>
      `;
      return;
    }

    queue.forEach((d, idx) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="col-num">${idx + 1}</td>
        <td><code>${d.id.substring(0, 8)}...</code></td>
        <td>${d.recipient_name} &lt;${d.recipient_email}&gt;</td>
        <td>${d.university}</td>
        <td>${d.subject_line}</td>
        <td><span class="badge window-open">${d.status}</span></td>
        <td><button class="btn btn-primary btn-sm" onclick="sendSingleDraft('${d.id}')">Send Now</button></td>
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
    alert(`Success! Dispatched draft to ${data.recipient_email} (Message-ID: ${data.message_id})`);
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

// Section 6: Analytics & IMAP Inbound Replies
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

async function loadInboundReplies() {
  try {
    const res = await fetchWithAuth("/api/v1/track/replies");
    const replies = await res.json();
    const tbody = document.getElementById("replies-tbody");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (!replies || replies.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="7" class="empty-state-cell">
            <div class="empty-state">
              <span class="empty-icon">📥</span>
              <h4>No Inbound Responses Detected</h4>
              <p>Incoming professor replies polled via IMAP will appear here.</p>
            </div>
          </td>
        </tr>
      `;
      return;
    }

    replies.forEach((r, idx) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="col-num">${idx + 1}</td>
        <td><strong>${r.sender_name || "Supervisor"}</strong></td>
        <td><code>${r.sender_email}</code></td>
        <td>${r.subject}</td>
        <td style="max-width: 300px; overflow: hidden; text-overflow: ellipsis;">${r.snippet || "-"}</td>
        <td>${r.received_at ? r.received_at.split("T")[0] : "-"}</td>
        <td>${r.reply_latency_hours ? r.reply_latency_hours + 'h' : "-"}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error("Error loading replies:", err);
  }
}

async function pollIMAPReplies() {
  try {
    const res = await fetchWithAuth("/api/v1/track/poll-replies", { method: "POST" });
    const replies = await res.json();
    alert(`Polled IMAP inbox. Detected ${replies.length} replies.`);
    loadAnalytics();
    loadInboundReplies();
  } catch (err) {
    alert("IMAP poll error: " + err);
  }
}

// Section 7: Terminal & WebSocket Logs
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
  pushInlineLog(log.level || "INFO", log.module || "System", log.message || "");
  const win = document.getElementById("terminal-window");
  if (!win) return;
  const line = document.createElement("div");
  line.className = `terminal-line ${log.level ? log.level.toLowerCase() : 'info'}`;
  line.textContent = `[${log.timestamp || ''}] [${log.module || 'System'}] [${log.level || 'INFO'}]: ${log.message || ''}`;
  win.appendChild(line);
  win.scrollTop = win.scrollHeight;
}

function appendRaw(text) {
  const win = document.getElementById("terminal-window");
  if (!win) return;
  const line = document.createElement("div");
  line.className = "terminal-line system";
  line.textContent = text;
  win.appendChild(line);
  win.scrollTop = win.scrollHeight;
}

function clearTerminal() {
  const win = document.getElementById("terminal-window");
  if (win) {
    win.innerHTML = `<div class="terminal-line system">[SYSTEM] Console cleared. Streaming active...</div>`;
  }
}

function filterLogs() {
  // Can filter log streams dynamically
}

// Floating Jump-to-Top Button Visibility
window.addEventListener("scroll", () => {
  const btn = document.getElementById("btn-to-top");
  if (!btn) return;
  if (window.pageYOffset > 300) {
    btn.style.display = "flex";
  } else {
    btn.style.display = "none";
  }
});

// App Initialization
document.addEventListener("DOMContentLoaded", () => {
  startLocalCSTClock();
  initTableDragResizers();
  if (!authHeader) {
    showAuthOverlay();
  } else {
    syncCSTClock();
    loadAllData();
    initScrollSpy();
    initWebSocket();
  }
});
