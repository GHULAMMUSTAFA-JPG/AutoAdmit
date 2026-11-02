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
  loadApplicantProfile();
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

function escapeAttr(str) {
  return String(str || "").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function getPipelineStatusBadge(status, reason) {
  const s = status || "Pending Live Check";
  const tip = escapeAttr(reason || s);
  if (s === "Professor Extraction Completed") {
    return `<div style="display:flex; flex-direction:column; gap:2px;">
      <span class="badge badge-status-verified" title="Step 1 Succeeded: Official homepage verified live.">✓ Step 1: Homepage OK</span>
      <span class="badge badge-status-extracted" title="${tip || 'Master/PhD supervisors extracted and verified in MongoDB.'}">✓ Step 2 & 3: Supervisors Extracted ⓘ</span>
    </div>`;
  }
  if (s === "Faculty Page Found") {
    return `<div style="display:flex; flex-direction:column; gap:2px;">
      <span class="badge badge-status-verified" title="Step 1 Succeeded: Official homepage verified live.">✓ Step 1: Homepage OK</span>
      <span class="badge badge-status-faculty" title="${tip || 'Step 2 & 3 Succeeded: Live-verified CS/AI department and confirmed Supervisor Roster URL.'}">✓ Step 2: Dept + Roster Found ⓘ</span>
    </div>`;
  }
  if (s === "Department URL Found") {
    return `<div style="display:flex; flex-direction:column; gap:2px;">
      <span class="badge badge-status-verified" title="Step 1 Succeeded: Official homepage verified live.">✓ Step 1: Homepage OK</span>
      <span class="badge badge-status-dept" title="${tip || 'Step 2 Succeeded: Resolved official CS/AI school URL.'}">✓ Step 2: CS/AI Dept Found ⓘ</span>
    </div>`;
  }
  if (s === "Homepage OK · Dept Not Found" || s === "Department URL Not Found") {
    const errTip = escapeAttr(reason || "Step 1 Succeeded (Homepage reachable), but Step 2 did not find a static CS/AI department link in '院系设置' or common subdomains.");
    return `<div style="display:flex; flex-direction:column; gap:2px;">
      <span class="badge badge-status-verified" title="✓ Step 1 Succeeded: University homepage is live and saved in MongoDB!">✓ Step 1: Homepage OK</span>
      <span class="badge badge-status-missing" title="❌ STEP 2 REASON: ${errTip}">✗ Step 2: Dept Not Found ⓘ</span>
    </div>`;
  }
  if (s === "Step 1 Failed: Homepage Unreachable" || s === "Requires Manual Review") {
    const errTip = escapeAttr(reason || "Step 1 Failed: Homepage and CS/AI subdomains timed out, failed DNS, or were blocked by WAF.");
    return `<span class="badge badge-status-manual" title="❌ STEP 1 FAILED REASON: ${errTip}">✗ Step 1 Failed: Unreachable / WAF ⓘ</span>`;
  }
  if (s === "Homepage Verified" || s === "University Homepage Verified") {
    return `<span class="badge badge-status-verified" title="${tip || 'Step 1 Succeeded: Homepage verified live (HTTP 200 OK).'}">✓ Step 1: Homepage Verified ⓘ</span>`;
  }
  return `<span class="badge badge-status-pending" title="⏳ Not live-probed yet. Click '🧭 Verify & Find Dept' on this row or '🧭 Resolve Real Dept Links' above to verify live.">⏳ Pending Live Check</span>`;
}

// Table Viewport Size (10 visible rows by default = 415px) & Scrollable Row Buffer
const tableRowLimits = {
  portals: 9999,
  matrix: 9999,
  faculty: 9999
};

const tableVisibleRowsConfig = {
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
  const rowsVisible = val === "ALL" ? 150 : (parseInt(val, 10) || 10);
  tableVisibleRowsConfig[tableKey] = rowsVisible;
  const viewMap = {
    portals: "portals-table-view",
    matrix: "matrix-table-view",
    faculty: "faculty-table-view"
  };
  const viewEl = document.getElementById(viewMap[tableKey]);
  if (viewEl) {
    // ~38px per row + 40px sticky header => 10 rows = 420px viewport with active vertical scrollbar
    const targetHeight = val === "ALL" ? 1600 : Math.max(260, (rowsVisible * 38) + 42);
    viewEl.style.maxHeight = `${targetHeight}px`;
  }
  if (tableKey === "portals") applyPortalsTableFilter();
  if (tableKey === "matrix") applyMatrixTableFilter();
  if (tableKey === "faculty") applyFacultyTableFilter();
}

function initTableDragResizers() {
  const handles = document.querySelectorAll(".table-resize-handle");
  handles.forEach(handle => {
    let startY = 0;
    let startHeight = 420;
    const targetId = handle.getAttribute("data-target");
    const tableKey = handle.getAttribute("data-table");

    const onMouseMove = (e) => {
      const container = document.getElementById(targetId);
      if (!container) return;
      const deltaY = e.clientY - startY;
      const newHeight = Math.max(240, Math.min(1800, startHeight + deltaY));
      container.style.maxHeight = `${newHeight}px`;

      const approxVisibleRows = Math.max(5, Math.round((newHeight - 42) / 38));
      if (tableKey) {
        tableVisibleRowsConfig[tableKey] = approxVisibleRows;
        const lblMap = {
          portals: "portals-showing-label",
          matrix: "matrix-showing-label",
          faculty: "faculty-showing-label"
        };
        const lblEl = document.getElementById(lblMap[tableKey]);
        if (lblEl) {
          lblEl.textContent = `Viewport: ~${approxVisibleRows} visible rows (Scroll vertically for all records)`;
        }
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
      startHeight = container.getBoundingClientRect().height || 420;
      handle.classList.add("dragging");
      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    });
  });
}

function toggleDiscoveryAuditPanel() {
  const body = document.getElementById("discovery-audit-body");
  const chev = document.getElementById("audit-chevron");
  if (!body) return;
  const isHidden = body.classList.contains("hidden");
  if (isHidden) {
    body.classList.remove("hidden");
    if (chev) chev.textContent = "▼";
  } else {
    body.classList.add("hidden");
    if (chev) chev.textContent = "▶";
  }
}

async function loadLastDiscoveryAudit() {
  try {
    const res = await fetchWithAuth("/api/v1/discovery/last-audit");
    if (!res.ok) return;
    const audit = await res.json();
    if (!audit || !audit.total_raw_count) return;

    const box = document.getElementById("discovery-audit-box");
    if (box) box.classList.remove("hidden");

    const srcLabels = {
      combined: "Combined Triple-Check (China MOE Master's + Wikidata SPARQL + 985/211)",
      wikidata: "Wikidata Live SPARQL Registry",
      moe: "China MOE Official Master's-Granting Registry (硕士点高校)"
    };
    const titleEl = document.getElementById("audit-summary-title");
    if (titleEl) {
      titleEl.textContent = `Active Search: ${srcLabels[audit.source_mode] || audit.source_mode} | Regions: ${(audit.regions_filter || ["All"]).join(", ")}`;
    }

    const excludedTotal = (audit.excluded_non_edu_count || 0) + (audit.excluded_vocational_count || 0) + (audit.duplicate_merged_count || 0);
    const rawBadge = document.getElementById("audit-badge-raw");
    const filtBadge = document.getElementById("audit-badge-filtered");
    const normBadge = document.getElementById("audit-badge-norm");
    if (rawBadge) rawBadge.textContent = `${audit.total_raw_count} Raw Source Records`;
    if (filtBadge) filtBadge.textContent = `${excludedTotal} Filtered / Deduplicated`;
    if (normBadge) normBadge.textContent = `${audit.normalized_count} Normalized in MongoDB`;

    const setTxt = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    setTxt("audit-moe-count", audit.moe_raw_count || 0);
    setTxt("audit-wd-count", audit.wikidata_raw_count || 0);
    setTxt("audit-non-edu-count", audit.excluded_non_edu_count || 0);
    setTxt("audit-voc-count", audit.excluded_vocational_count || 0);
    setTxt("audit-dup-count", audit.duplicate_merged_count || 0);
    setTxt("audit-final-count", audit.normalized_count || 0);

    const rawTbody = document.getElementById("audit-raw-tbody");
    if (rawTbody && Array.isArray(audit.raw_preview_rows)) {
      rawTbody.innerHTML = audit.raw_preview_rows.map((r, i) => {
        let outBadge = `<span class="badge badge-status-faculty">${r.outcome}</span>`;
        if ((r.outcome || "").startsWith("REJECTED")) outBadge = `<span class="badge badge-status-manual">${r.outcome}</span>`;
        else if ((r.outcome || "").startsWith("EXCLUDED")) outBadge = `<span class="badge badge-status-missing">${r.outcome}</span>`;
        else if ((r.outcome || "").startsWith("MERGED")) outBadge = `<span class="badge badge-status-dept">${r.outcome}</span>`;
        return `
          <tr>
            <td class="col-num">${i + 1}</td>
            <td><span class="badge version">${r.source_origin}</span></td>
            <td style="font-family: var(--font-mono); font-size: 0.72rem;">${r.raw_id || "-"}</td>
            <td><strong>${r.raw_en_name}</strong></td>
            <td>${r.raw_zh_name}</td>
            <td style="font-family: var(--font-mono); font-size: 0.72rem;">${r.raw_url}</td>
            <td>${outBadge}</td>
          </tr>
        `;
      }).join("");
    }
  } catch (e) {
    console.error("Failed loading discovery audit:", e);
  }
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
      const statusRank = s => {
        if (!s) return 4;
        if (s.includes("Faculty") || s.includes("Department") || s.includes("Completed")) return 1;
        if (s.includes("Homepage OK") || s.includes("Homepage Verified")) return 2;
        if (s.includes("Pending")) return 3;
        return 5;
      };
      const diff = statusRank(a.pipeline_status) - statusRank(b.pipeline_status);
      if (diff !== 0) return diff;
      return (a.name || "").localeCompare(b.name || "");
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

function populatePortalUnivDropdown() {
  const univSelect = document.getElementById("portal-univ-filter");
  if (!univSelect) return;
  const regionVal = document.getElementById("portal-region-filter")?.value || "All";
  const tierVal = document.getElementById("portal-tier-filter")?.value || "All";
  const currentVal = univSelect.value || "All";

  let list = (lastDiscoveredUniversities || []).filter(u => {
    if (regionVal !== "All" && u.region !== regionVal) return false;
    if (tierVal !== "All" && u.tier !== tierVal) return false;
    return true;
  });

  list = sortUniversityList(list, "name-asc");
  univSelect.innerHTML = `<option value="All">All Universities in Filter (${list.length})</option>`;
  list.forEach(u => {
    const opt = document.createElement("option");
    opt.value = u.domain;
    opt.textContent = `${u.name} (${u.domain})`;
    univSelect.appendChild(opt);
  });

  if (list.some(u => u.domain === currentVal)) {
    univSelect.value = currentVal;
  } else {
    univSelect.value = "All";
  }
}

function onPortalRegionOrTierChange() {
  populatePortalUnivDropdown();
  applyPortalsTableFilter();
}

function renderMatchedEndpoints(universities) {
  lastDiscoveredUniversities = universities || [];
  populateRegionFilterDropdown("portal-region-filter", lastDiscoveredUniversities);
  populatePortalUnivDropdown();
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
  const univVal = document.getElementById("portal-univ-filter")?.value || "All";
  const sortVal = document.getElementById("portal-sort-select")?.value || "region-asc";

  let filtered = (lastDiscoveredUniversities || []).filter(u => {
    if (regionVal !== "All" && u.region !== regionVal) return false;
    if (tierVal !== "All" && u.tier !== tierVal) return false;
    if (univVal !== "All" && u.domain !== univVal) return false;
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

  // Dynamically update Live Count Badges for Step 1 Failed and Step 2 Missing Retry Buttons
  const s1FailedCount = filtered.filter(u => {
    const st = u.pipeline_status || "";
    return st.startsWith("Step 1 Failed") || st === "Requires Manual Review";
  }).length;
  const s2MissingCount = filtered.filter(u => {
    const st = u.pipeline_status || "";
    return st === "Homepage OK · Dept Not Found" ||
           st === "Department URL Not Found" ||
           (st === "Homepage Verified" && (!u.department_endpoints || u.department_endpoints.length <= 1));
  }).length;
  const s1El = document.getElementById("retry-s1-count");
  if (s1El) s1El.textContent = s1FailedCount;
  const s2El = document.getElementById("retry-s2-count");
  if (s2El) s2El.textContent = s2MissingCount;

  const tbody = document.getElementById("matched-endpoints-tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  if (filtered.length === 0) {
    const showLbl = document.getElementById("portals-showing-label");
    if (showLbl) showLbl.textContent = "Showing 0 rows";
    tbody.innerHTML = `
      <tr>
        <td colspan="7" class="empty-state-cell">
          <div class="empty-state">
            <span class="empty-icon">🔎</span>
            <h4>No Matching Universities</h4>
            <p>Adjust your search text, region filter, tier filter, or university dropdown above.</p>
          </div>
        </td>
      </tr>
    `;
    return;
  }

  const limit = tableRowLimits.portals || 9999;
  const visibleRows = filtered.slice(0, limit);
  const showLbl = document.getElementById("portals-showing-label");
  if (showLbl) {
    const vpRows = tableVisibleRowsConfig.portals || 10;
    showLbl.textContent = `Viewport: ~${vpRows} visible rows | Scrollable: ${visibleRows.length} rows`;
  }

  visibleRows.forEach((u, idx) => {
    const tr = document.createElement("tr");
    const endpointsHtml = (u.department_endpoints || []).map(ep => {
      let icon = "🌐";
      if (ep.name.includes("🏛️") || ep.name.includes("Homepage")) icon = "🏛️";
      else if (ep.name.includes("👨‍🏫") || ep.name.includes("Supervisor") || ep.name.includes("导师")) icon = "👨‍🏫";
      else if (ep.name.includes("🎓") || ep.name.includes("Department") || ep.name.includes("学院")) icon = "🎓";
      return `
        <div class="endpoint-chip-item">
          <span class="badge version">${icon} ${ep.name}</span>
          <a href="${ep.url}" target="_blank" title="${ep.url}">${ep.url} ↗</a>
        </div>
      `;
    }).join("") || `<span style="color:var(--text-muted); font-size:0.74rem;">Pending discovery</span>`;

    // Smart Action Button based on live Step 1 (Homepage) & Step 2 (Department) status
    const st = u.pipeline_status || "Pending Live Check";
    const reasonTip = escapeAttr(u.status_reason || "");
    let actionBtnHtml = `<button class="btn btn-secondary btn-sm btn-interactive" onclick="resolveSingleUniversityDept('${u.domain}', this)" title="Live-probe Step 1 Homepage & Step 2 CS/AI Department">🧭 Verify & Find Dept</button>`;
    if (st === "Faculty Page Found" || st === "Department URL Found" || st === "Professor Extraction Completed") {
      actionBtnHtml = `<button class="btn btn-success btn-sm btn-interactive" onclick="resolveSingleUniversityDept('${u.domain}', this)" title="Step 1 & Step 2 Verified! (${reasonTip}) Click to re-verify.">✓ Verified (↻)</button>`;
    } else if (st === "Homepage OK · Dept Not Found" || st === "Department URL Not Found") {
      actionBtnHtml = `<button class="btn btn-secondary btn-sm btn-interactive" style="border-color:#f59e0b; color:#b45309;" onclick="resolveSingleUniversityDept('${u.domain}', this)" title="Step 1 Homepage OK, Step 2 Dept Missing: ${reasonTip} — Click to retry Step 2.">🧭 Retry Step 2 (Dept)</button>`;
    } else if (st === "Step 1 Failed: Homepage Unreachable" || st === "Requires Manual Review") {
      actionBtnHtml = `<button class="btn btn-danger btn-sm btn-interactive" onclick="resolveSingleUniversityDept('${u.domain}', this)" title="Step 1 Failed: ${reasonTip} — Click to retry.">↻ Retry Step 1 & 2</button>`;
    }

    tr.innerHTML = `
      <td class="col-num">${idx + 1}</td>
      <td>
        <div><strong>${u.name}</strong></div>
        <div style="color: var(--text-secondary); font-size: 0.74rem;">${u.chinese_name || "-"}</div>
      </td>
      <td class="col-region"><span class="badge ${getRegionBadgeClass(u.region)}">${u.region || "National"}</span></td>
      <td class="col-tier"><span class="badge ${getTierBadgeClass(u.tier)}">${u.tier || "Tier 3 (Safety)"}</span></td>
      <td class="col-status">${getPipelineStatusBadge(u.pipeline_status, u.status_reason)}</td>
      <td><div class="endpoint-chips-list">${endpointsHtml}</div></td>
      <td class="col-action">${actionBtnHtml}</td>
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
      pushInlineLog(
        updated.pipeline_status.includes("Found") ? "SUCCESS" : "WARNING",
        "HomepageCrawler",
        `[${updated.name}] -> ${updated.pipeline_status} (${updated.status_reason || ""}) | ${eps}`
      );
      applyPortalsTableFilter();
      loadUniversities();
    }
  } catch (err) {
    pushInlineLog("ERROR", "HomepageCrawler", `[${domain}] ✗ Error resolving department: ${err}`);
  } finally {
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.classList.remove("btn-loading");
    }
  }
}

let isBatchResolving = false;
let stopBatchResolveRequested = false;
let currentActiveBatchBtn = null;
let currentBatchDefaultHtml = "";

function stopBatchProbeExecution(btn = null) {
  if (!isBatchResolving) {
    pushInlineLog("INFO", "BatchResolver", "No batch probe is currently running.");
    return;
  }
  stopBatchResolveRequested = true;
  if (btn) btn.textContent = "⏳ Stopping after current...";
  const stopBtn = document.getElementById("btn-stop-batch-probe");
  if (stopBtn) stopBtn.textContent = "⏳ Stopping after current...";
  if (currentActiveBatchBtn) currentActiveBatchBtn.textContent = "⏳ Stopping after current...";
  pushInlineLog("WARNING", "BatchResolver", "⏸ Batch probe halt requested. Safe stop after current in-flight batch without data loss.");
}

async function executeBatchProbe(targets, modeLabel, triggerBtn, defaultHtml, stageTitle) {
  const btn = triggerBtn || document.getElementById("btn-resolve-depts");

  if (isBatchResolving) {
    stopBatchResolveRequested = true;
    if (btn) btn.textContent = "⏳ Stopping after current...";
    if (currentActiveBatchBtn && currentActiveBatchBtn !== btn) {
      currentActiveBatchBtn.textContent = "⏳ Stopping after current...";
    }
    pushInlineLog("WARNING", "BatchResolver", `⏸ Stop requested by operator for ${modeLabel || "Batch Probe"}. Halting after current in-flight batch...`);
    return;
  }

  if (!targets || targets.length === 0) {
    alert(`No universities match the criteria for ${modeLabel || "this action"}.`);
    return;
  }

  isBatchResolving = true;
  stopBatchResolveRequested = false;
  currentActiveBatchBtn = btn;
  currentBatchDefaultHtml = defaultHtml;

  const workerSelect = document.getElementById("portal-probe-workers");
  const workerCount = Math.min(3, Math.max(1, parseInt(workerSelect ? workerSelect.value : "3", 10) || 3));

  if (btn) {
    btn.classList.add("btn-loading");
    btn.textContent = `⏹ Stop (0/${targets.length} Probed | ${workerCount}W)`;
  }

  startProgressAnimation(stageTitle || "HOMEPAGE-FIRST DISCOVERY", `Live-probing ${targets.length} target university homepages using ${workerCount} parallel worker(s)...`);
  pushInlineLog("INFO", "BatchResolver", `🚀 Starting ${modeLabel} across ${targets.length} universities with ${workerCount} parallel worker(s)...`);

  const discipline = document.getElementById("filter-discipline")?.value || "Computer Science";
  let done = 0;

  try {
    for (let i = 0; i < targets.length; i += workerCount) {
      if (stopBatchResolveRequested) {
        pushInlineLog("WARNING", "BatchResolver", `⏸ Batch resolution paused by operator at ${done}/${targets.length} universities.`);
        break;
      }

      const chunk = targets.slice(i, i + workerCount);
      const chunkDomains = chunk.map(u => u.domain);
      const chunkNames = chunk.map(u => u.name).join(", ");
      const pct = Math.max(3, Math.round((done / targets.length) * 100));

      if (btn) btn.textContent = `⏹ Stop (${done}/${targets.length} Probed | ${workerCount}W)`;
      updateProgressStage(
        pct,
        `LIVE PROBING (${done}/${targets.length} | ${workerCount} WORKERS)`,
        `Parallel batch (${done + 1}–${Math.min(done + chunk.length, targets.length)} of ${targets.length}): ${chunkNames}`,
        `Checking 200 OK / Playwright WAF -> 院系设置 -> ${discipline} -> Saving to MongoDB`
      );

      try {
        const res = await fetchWithAuth("/api/v1/discovery/resolve-departments", {
          method: "POST",
          body: JSON.stringify({
            domains: chunkDomains,
            discipline: discipline,
            max_workers: workerCount
          })
        });
        const updatedList = await res.json();
        if (Array.isArray(updatedList)) {
          updatedList.forEach(updated => {
            done++;
            const idx = lastDiscoveredUniversities.findIndex(item => item.domain === updated.domain);
            if (idx !== -1) lastDiscoveredUniversities[idx] = updated;
            const epText = (updated.department_endpoints || []).map(e => `${e.name} (${e.url})`).join(" | ");
            const st = updated.pipeline_status || "";
            const logLevel = st.includes("Found") ? "SUCCESS" : (st.includes("Homepage OK") ? "INFO" : "WARNING");
            const stepSummary = st.includes("Found")
              ? "[Step 1: Homepage OK ✓ | Step 2: CS/AI Dept Found ✓]"
              : (st.includes("Homepage OK")
                  ? "[Step 1: Homepage OK ✓ | Step 2: Dept Link Not Found ⚠]"
                  : "[Step 1: Homepage Unreachable ✗]");
            pushInlineLog(
              logLevel,
              "HomepageCrawler",
              `[${done}/${targets.length}] [${updated.name}] ${stepSummary} -> ${updated.status_reason || st} | ${epText}`
            );
            if (Array.isArray(allDirectoryUniversities)) {
              const dIdx = allDirectoryUniversities.findIndex(item => item.domain === updated.domain);
              if (dIdx !== -1) allDirectoryUniversities[dIdx] = updated;
              else allDirectoryUniversities.push(updated);
            }
          });
          updateMatrixAnalyticsAndRegions();
        }
      } catch (e) {
        const errMsg = String(e || "");
        if (errMsg.includes("Failed to fetch") || errMsg.includes("NetworkError")) {
          pushInlineLog("ERROR", "BatchResolver", `⏸ Backend server connection lost (${errMsg}). Automatically paused batch at ${done}/${targets.length} so remaining universities are not skipped!`);
          stopProgressAnimation(false, `Paused at ${done}/${targets.length}: Backend server offline (Failed to fetch). Restart server and click to resume.`);
          break;
        }
        done += chunk.length;
        pushInlineLog("ERROR", "HomepageCrawler", `[Batch ${done}/${targets.length}] (${chunkNames}) Failed: ${e}`);
      }
      applyPortalsTableFilter();
    }
  } finally {
    isBatchResolving = false;
    stopBatchResolveRequested = false;
    currentActiveBatchBtn = null;
    stopProgressAnimation(true, `Completed ${modeLabel} (${done}/${targets.length} probed with ${workerCount} parallel workers, persisted to MongoDB).`);
    loadUniversities();
    if (btn) {
      btn.disabled = false;
      btn.classList.remove("btn-loading");
      btn.innerHTML = defaultHtml;
    }
    applyPortalsTableFilter();
  }
}

async function resolveRealDepartmentsForVisible(triggerBtn = null) {
  const btn = triggerBtn || document.getElementById("btn-resolve-depts");
  if (isBatchResolving) {
    executeBatchProbe(null, "Live Discovery & Department Resolution", btn, "🧭 Resolve Real Dept Links", "HOMEPAGE-FIRST DISCOVERY");
    return;
  }

  const univVal = document.getElementById("portal-univ-filter")?.value || "All";
  const regionVal = document.getElementById("portal-region-filter")?.value || "All";
  const tierVal = document.getElementById("portal-tier-filter")?.value || "All";

  const baseList = (filteredPortalUniversities && filteredPortalUniversities.length > 0)
    ? filteredPortalUniversities
    : (lastDiscoveredUniversities || []);

  if (baseList.length === 0) {
    alert("No universities match the current filters. Adjust your filters or run discovery first.");
    return;
  }

  // Scoped worker targets based on Region, Tier, and Specific University filters
  let targets = [];
  if (univVal !== "All") {
    targets = baseList.filter(u => u.domain === univVal);
  } else {
    targets = baseList.filter(u =>
      u.pipeline_status !== "Faculty Page Found" &&
      u.pipeline_status !== "Department URL Found" &&
      u.pipeline_status !== "Professor Extraction Completed"
    );
  }

  if (targets.length === 0) {
    const filterDesc = [
      regionVal !== "All" ? `Region: ${regionVal}` : null,
      tierVal !== "All" ? `Tier: ${tierVal}` : null,
      univVal !== "All" ? `University: ${univVal}` : null
    ].filter(Boolean).join(" | ") || "All Universities";
    alert(`All universities in the selected filter (${filterDesc}) already have verified department links!`);
    return;
  }

  await executeBatchProbe(
    targets,
    "Live Discovery & Department Resolution",
    btn,
    "🧭 Resolve Real Dept Links",
    "HOMEPAGE-FIRST DISCOVERY"
  );
}

async function retryFailedStep1Universities(triggerBtn = null) {
  const btn = triggerBtn || document.getElementById("btn-retry-step1-failed");
  if (isBatchResolving) {
    executeBatchProbe(null, "Step 1 Failed Homepage Retry", btn, `🔄 Retry Step 1 Failed (<span id="retry-s1-count">0</span>)`, "STEP 1 HOMEPAGE RETRY");
    return;
  }

  const baseList = (filteredPortalUniversities && filteredPortalUniversities.length > 0)
    ? filteredPortalUniversities
    : (lastDiscoveredUniversities || []);

  const univVal = document.getElementById("portal-univ-filter")?.value || "All";
  const targets = baseList.filter(u => {
    if (univVal !== "All" && u.domain !== univVal) return false;
    const st = u.pipeline_status || "";
    return st.startsWith("Step 1 Failed") || st === "Requires Manual Review";
  });

  if (targets.length === 0) {
    alert("No universities in the current view have Step 1 failures (all homepages are reachable or already verified)!");
    return;
  }

  const defaultHtml = `🔄 Retry Step 1 Failed (<span id="retry-s1-count">${targets.length}</span>)`;
  await executeBatchProbe(
    targets,
    "Step 1 Failed Homepage Retry",
    btn,
    defaultHtml,
    "STEP 1 HOMEPAGE RETRY"
  );
}

async function retryMissingStep2Universities(triggerBtn = null) {
  const btn = triggerBtn || document.getElementById("btn-retry-step2-missing");
  if (isBatchResolving) {
    executeBatchProbe(null, "Step 2 Missing Dept/Roster Retry", btn, `🧭 Retry Missing Dept/Roster (<span id="retry-s2-count">0</span>)`, "STEP 2 DEPARTMENT RETRY");
    return;
  }

  const baseList = (filteredPortalUniversities && filteredPortalUniversities.length > 0)
    ? filteredPortalUniversities
    : (lastDiscoveredUniversities || []);

  const univVal = document.getElementById("portal-univ-filter")?.value || "All";
  const targets = baseList.filter(u => {
    if (univVal !== "All" && u.domain !== univVal) return false;
    const st = u.pipeline_status || "";
    return st === "Homepage OK · Dept Not Found" ||
           st === "Department URL Not Found" ||
           (st === "Homepage Verified" && (!u.department_endpoints || u.department_endpoints.length <= 1));
  });

  if (targets.length === 0) {
    alert("No universities in the current view have missing Step 2 departments!");
    return;
  }

  const defaultHtml = `🧭 Retry Missing Dept/Roster (<span id="retry-s2-count">${targets.length}</span>)`;
  await executeBatchProbe(
    targets,
    "Step 2 Missing Department & Roster Retry",
    btn,
    defaultHtml,
    "STEP 2 DEPARTMENT RETRY"
  );
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
    updateProgressStage(35, "STAGE 1: RAW MULTI-SOURCE QUERY", `Fetching raw datasets from ${activeSourceLabel}...`, `Source: ${activeSourceLabel} | Regions: ${selectedRegions.join(", ")}`);

    const res = await fetchWithAuth("/api/v1/discovery/filter", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    
    updateProgressStage(75, "STAGE 2: NORMALIZING & SAVING TO MONGODB", "Deduplicating raw MOE/Wikidata records, saving raw audit + normalized universities to MongoDB...", "Writing to autoadmit.universities & autoadmit.discovery_runs");

    const universities = await res.json();
    lastDiscoveredUniversities = universities;

    updateProgressStage(92, "STAGE 3: READING FROM MONGODB TO UI", "Loading persisted normalized records and raw multi-source audit from MongoDB...", "Syncing Section 01 Portals & Section 02 Matrix");

    const t1 = universities.filter(u => u.tier && u.tier.includes("Tier 1")).length;
    const t2 = universities.filter(u => u.tier && u.tier.includes("Tier 2")).length;
    const t3 = universities.length - t1 - t2;

    pushInlineLog("SUCCESS", "Discovery", `✓ Discovered & persisted ${universities.length} normalized Master's-granting .edu.cn universities via ${activeSourceLabel} (Tier 1 Dream: ${t1}, Tier 2 Target: ${t2}, Tier 3 Safety: ${t3}). Loaded from MongoDB.`);

    stopProgressAnimation(true, `Successfully discovered & saved ${universities.length} normalized universities via ${activeSourceLabel} (Tier 1: ${t1}, Tier 2: ${t2}, Tier 3: ${t3}).`);
    await loadLastDiscoveryAudit();
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

  // Instant Layer 3 Hydration from localStorage so page never opens blank
  const cached = localStorage.getItem("cached_universities_directory");
  if (cached && (!allDirectoryUniversities || allDirectoryUniversities.length === 0)) {
    try {
      const parsed = JSON.parse(cached);
      if (Array.isArray(parsed) && parsed.length > 0) {
        allDirectoryUniversities = parsed;
        lastDiscoveredUniversities = parsed;
        populateRegionFilterDropdown("matrix-region-filter", allDirectoryUniversities);
        populateSupervisorPoolControls();
        updateMatrixAnalyticsAndRegions();
        applyMatrixTableFilter();
        renderMatchedEndpoints(allDirectoryUniversities);
      }
    } catch (e) {}
  }

  renderTableSkeleton("universities-tbody", 7, 8);
  try {
    const res = await fetchWithAuth("/api/v1/discovery/universities");
    const fetched = await res.json();
    if (Array.isArray(fetched) && fetched.length > 0) {
      allDirectoryUniversities = fetched;
      lastDiscoveredUniversities = fetched;
      try {
        localStorage.setItem("cached_universities_directory", JSON.stringify(fetched));
      } catch (e) {}
    }
    populateRegionFilterDropdown("matrix-region-filter", allDirectoryUniversities);
    populateSupervisorPoolControls();
    updateMatrixAnalyticsAndRegions();
    applyMatrixTableFilter();

    // Automatically restore Section 01 (Discovered University Portals) & Raw/Normalized Audit from MongoDB across page refreshes!
    if (allDirectoryUniversities && allDirectoryUniversities.length > 0) {
      renderMatchedEndpoints(allDirectoryUniversities);
      loadLastDiscoveryAudit();
    }
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

function updateMatrixAnalyticsAndRegions() {
  const list = allDirectoryUniversities || [];
  const total = list.length;
  
  let hpOk = 0;
  let deptOk = 0;
  let pending = 0;
  const regCounts = {};

  list.forEach(u => {
    const reg = u.region || "National";
    regCounts[reg] = (regCounts[reg] || 0) + 1;

    const st = u.pipeline_status || "";
    const isHpVerified = Boolean(u.website_verified || (st && !st.includes("Pending") && !st.startsWith("Step 1 Failed")));
    const isDeptFound = Boolean(st === "Faculty Page Found" || st === "Department URL Found" || st === "Professor Extraction Completed");

    if (isHpVerified) hpOk++;
    if (isDeptFound) deptOk++;
    if (!isHpVerified || st === "Pending Live Check" || st.startsWith("Step 1 Failed")) pending++;
  });

  const setT = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
  setT("matrix-stat-total", total);
  setT("matrix-stat-hp-ok", hpOk);
  setT("matrix-stat-hp-pct", total > 0 ? `${Math.round((hpOk / total) * 100)}% verified 200 OK` : "0%");
  setT("matrix-stat-dept-ok", deptOk);
  setT("matrix-stat-dept-pct", total > 0 ? `${Math.round((deptOk / total) * 100)}% endpoints resolved` : "0%");
  setT("matrix-stat-pending", pending);

  // Render regional distribution pills sorted by university count descending
  const pillsWrap = document.getElementById("matrix-region-pills");
  if (pillsWrap) {
    const sortedRegions = Object.keys(regCounts).sort((a, b) => regCounts[b] - regCounts[a]);
    const currentFilter = document.getElementById("matrix-region-filter")?.value || "All";
    
    pillsWrap.innerHTML = sortedRegions.map(r => {
      const isActive = (r === currentFilter) ? "active" : "";
      return `<button class="region-pill ${isActive}" onclick="filterMatrixByRegion('${escapeAttr(r)}')">${r} <span class="pill-count">${regCounts[r]}</span></button>`;
    }).join("");
  }
}

function filterMatrixByRegion(region) {
  const sel = document.getElementById("matrix-region-filter");
  if (sel) {
    sel.value = region;
  }
  applyMatrixTableFilter();
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

let isSupervisorHarvesting = false;
let stopSupervisorHarvestRequested = false;

function stopSupervisorWorkerPool() {
  if (!isSupervisorHarvesting) return;
  stopSupervisorHarvestRequested = true;
  const stopBtn = document.getElementById("btn-stop-sup-workers");
  if (stopBtn) stopBtn.textContent = "⏳ Stopping after current batch...";
  const launchBtnText = document.getElementById("btn-sup-text");
  if (launchBtnText) launchBtnText.textContent = "⏳ Stopping after batch...";
  pushInlineLog("WARNING", "WorkerPool", "⏸ Supervisor extraction stop requested. Halting cleanly after in-flight batch without data loss...");
}

async function launchSupervisorWorkerPool() {
  if (isSupervisorHarvesting) {
    stopSupervisorWorkerPool();
    return;
  }

  const regSelect = document.getElementById("sup-region-select");
  const tierSelect = document.getElementById("sup-tier-select");
  const univSelect = document.getElementById("sup-univ-select");
  const workerSelect = document.getElementById("sup-worker-count");
  const discSelect = document.getElementById("sup-discipline-select");

  const selectedReg = regSelect ? regSelect.value : "All";
  const selectedTier = tierSelect ? tierSelect.value : "All";
  const workerCount = Math.min(3, Math.max(1, parseInt(workerSelect ? workerSelect.value : "3", 10) || 3));
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

  isSupervisorHarvesting = true;
  stopSupervisorHarvestRequested = false;

  const btn = document.getElementById("btn-launch-sup-workers");
  const stopBtn = document.getElementById("btn-stop-sup-workers");
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
    btn.disabled = false;
    btn.classList.add("btn-loading", "btn-danger");
    btn.classList.remove("btn-primary");
  }
  if (stopBtn) {
    stopBtn.disabled = false;
    stopBtn.textContent = "⏹ Stop Workers";
  }
  if (spinner) spinner.classList.remove("hidden");
  if (textEl) textEl.textContent = `⏹ Stop Supervisor Workers (0/${candidateUnivs.length} | ${workerCount}W)`;
  if (progCard) progCard.classList.remove("hidden");

  const totalUnivs = candidateUnivs.length;
  let completedUnivs = 0;
  let totalHarvestedCount = 0;

  pushInlineLog("INFO", "WorkerPool", `🚀 Launching ${workerCount} parallel crawler worker(s) across ${totalUnivs} university(ies) in ${selectedReg} for ${discipline}...`);

  try {
    // Process in batches of workerCount so the UI progress bar updates smoothly in real time
    for (let i = 0; i < totalUnivs; i += workerCount) {
      if (stopSupervisorHarvestRequested) {
        pushInlineLog("WARNING", "WorkerPool", `⏸ Supervisor worker pool paused by operator at ${completedUnivs}/${totalUnivs} universities.`);
        break;
      }

      const chunk = candidateUnivs.slice(i, i + workerCount);
      const chunkNames = chunk.map(u => u.name).join(", ");
      const pct = Math.max(5, Math.round((completedUnivs / totalUnivs) * 100));

      if (textEl) textEl.textContent = `⏹ Stop Supervisor Workers (${completedUnivs}/${totalUnivs} | ${workerCount}W)`;
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
        const errStr = String(err || "");
        if (errStr.includes("Failed to fetch") || errStr.includes("NetworkError")) {
          pushInlineLog("ERROR", "WorkerPool", `⏸ Backend server connection lost (${errStr}). Paused supervisor extraction at ${completedUnivs}/${totalUnivs}.`);
          break;
        }
        pushInlineLog("ERROR", "WorkerPool", `Batch worker error on (${chunkNames}): ${err}`);
      }

      completedUnivs += chunk.length;
      await loadFaculty();
    }

    if (stopSupervisorHarvestRequested) {
      if (progBadge) progBadge.textContent = `EXTRACTION PAUSED`;
      if (progTitle) progTitle.textContent = `Paused crawling at ${completedUnivs}/${totalUnivs} university(ies) in ${selectedReg}. All harvested supervisors preserved.`;
      if (progDetail) progDetail.textContent = `Safe stop complete. You can resume or switch filters anytime.`;
    } else {
      if (progBadge) progBadge.textContent = `EXTRACTION COMPLETED`;
      if (progTitle) progTitle.textContent = `Finished crawling ${totalUnivs} university(ies) in ${selectedReg} using ${workerCount} parallel workers.`;
      if (progBar) progBar.style.width = `100%`;
      if (progPct) progPct.textContent = `100% (${totalUnivs} / ${totalUnivs} Universities Completed)`;
      if (progDetail) progDetail.textContent = `All verified Master's/PhD supervisors persisted to MongoDB.`;
      pushInlineLog("SUCCESS", "WorkerPool", `✓ Completed parallel supervisor extraction across ${totalUnivs} university(ies).`);
    }
  } finally {
    isSupervisorHarvesting = false;
    stopSupervisorHarvestRequested = false;
    await loadUniversities();
    await loadFaculty();

    if (btn) {
      btn.disabled = false;
      btn.classList.remove("btn-loading", "btn-danger");
      btn.classList.add("btn-primary");
    }
    if (stopBtn) {
      stopBtn.disabled = false;
      stopBtn.textContent = "⏹ Stop Workers";
    }
    if (spinner) spinner.classList.add("hidden");
    if (textEl) textEl.textContent = "🚀 Launch Parallel Supervisor Workers";
  }
}

function applyMatrixTableFilter() {
  const tbody = document.getElementById("universities-tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  const searchVal = (document.getElementById("matrix-search-input")?.value || "").toLowerCase().trim();
  const regionVal = document.getElementById("matrix-region-filter")?.value || "All";
  const tierVal = document.getElementById("matrix-tier-filter")?.value || "All";
  const sortVal = document.getElementById("matrix-sort-select")?.value || "region-asc";

  // Sync active state on regional pills
  const pills = document.querySelectorAll("#matrix-region-pills .region-pill");
  pills.forEach(p => {
    const pillReg = p.textContent.split(" ")[0].trim();
    if (pillReg === regionVal || (regionVal === "All" && pillReg === "All")) {
      p.classList.add("active");
    } else {
      p.classList.remove("active");
    }
  });

  if (!allDirectoryUniversities || allDirectoryUniversities.length === 0) {
    const countEl = document.getElementById("matrix-univ-count");
    if (countEl) countEl.textContent = "0";
    tbody.innerHTML = `
      <tr>
        <td colspan="7" class="empty-state-cell">
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
        <td colspan="7" class="empty-state-cell">
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

  const limit = tableRowLimits.matrix || 9999;
  const visibleRows = filtered.slice(0, limit);
  const showLbl = document.getElementById("matrix-showing-label");
  if (showLbl) {
    const viewportRows = tableVisibleRowsConfig.matrix || 10;
    showLbl.textContent = `Viewport: ~${viewportRows} visible rows | Scrollable: ${visibleRows.length} rows`;
  }

  visibleRows.forEach((u, idx) => {
    const tr = document.createElement("tr");

    // Unified National Classification & Competitiveness Note
    let natClassHtml = `<span class="badge badge-region-default">Provincial Key</span>`;
    let compNote = "Accredited Master's institution";
    if (u.is_project_985) {
      natClassHtml = `<span class="badge badge-tier-1">Project 985 / C9</span>`;
      compNote = "High competition · Elite research labs";
    } else if (u.is_project_211) {
      natClassHtml = `<span class="badge badge-tier-2">Project 211 / Double First-Class</span>`;
      compNote = "Strong quota · Key national engineering";
    } else {
      compNote = "High acceptance flexibility";
    }

    // Accurate Application Fee
    let feeHtml = `<span class="badge badge-fee-standard" title="Most Chinese universities charge 400–800 RMB processing fee unless waived via CSC or university policy">${u.fee_note || "400–800 RMB (Standard Est.)"}</span>`;
    if (u.application_fee_rmb === 0) {
      feeHtml = `<span class="badge badge-fee-waived">0 RMB (Fee Waived)</span>`;
    } else if (typeof u.application_fee_rmb === "number" && u.application_fee_rmb > 0) {
      feeHtml = `<span class="badge badge-fee-standard">${u.application_fee_rmb} RMB</span>`;
    }

    const officialSite = u.website || `https://www.${u.domain}/`;

    // Gathered Specific Department/Supervisor Links Displayed Clearly Alongside Root
    const endpointsListHtml = (u.department_endpoints || []).map(ep => {
      let icon = "🌐";
      if (ep.name.includes("🏛️") || ep.name.includes("Homepage")) icon = "🏛️";
      else if (ep.name.includes("👨‍🏫") || ep.name.includes("Supervisor") || ep.name.includes("导师")) icon = "👨‍🏫";
      else if (ep.name.includes("🎓") || ep.name.includes("Department") || ep.name.includes("学院")) icon = "🎓";
      return `
        <div class="endpoint-chip-item">
          <span class="badge version">${icon} ${ep.name}</span>
          <a href="${ep.url}" target="_blank" title="${ep.url}">${ep.url} ↗</a>
        </div>
      `;
    }).join("") || `
      <div class="endpoint-chip-item">
        <span class="badge version">🏛️ Root</span>
        <a href="${officialSite}" target="_blank" title="${officialSite}">${u.domain} ↗</a>
      </div>
    `;

    tr.innerHTML = `
      <td class="col-num">${idx + 1}</td>
      <td>
        <div><strong>${u.name}</strong></div>
        <div style="color: var(--text-secondary); font-size: 0.74rem;">${u.chinese_name || "-"}</div>
      </td>
      <td class="col-region"><span class="badge ${getRegionBadgeClass(u.region)}">${u.region || "National"}</span></td>
      <td>
        <div class="endpoint-chips-list">
          ${endpointsListHtml}
        </div>
      </td>
      <td>
        <div style="display: flex; gap: 0.35rem; align-items: center; margin-bottom: 2px;">
          <span class="badge ${getTierBadgeClass(u.tier)}">${u.tier || "Tier 3"}</span>
          ${natClassHtml}
        </div>
        <div style="font-size: 0.72rem; color: var(--text-secondary);">${compNote}</div>
      </td>
      <td>
        <div style="margin-bottom: 3px;">${feeHtml}</div>
        <div style="font-size: 0.72rem; color: var(--text-secondary);">${(u.scholarships_available || []).join(", ") || "Provincial / Presidential"}</div>
      </td>
      <td style="max-width: 250px;">
        <div>${getPipelineStatusBadge(u.pipeline_status, u.status_reason)}</div>
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

  filteredFacultyRecords = filtered;
  const draftCandEl = document.getElementById("faculty-draft-candidate-count");
  if (draftCandEl) {
    const validEmails = filtered.filter(f => f.email && f.email.includes("@")).length;
    draftCandEl.textContent = validEmails;
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

let isGeneratingDrafts = false;
let stopDraftsRequested = false;

function stopDraftGeneration() {
  if (!isGeneratingDrafts) return;
  stopDraftsRequested = true;
  const stopBtn = document.getElementById("btn-stop-draft-workers");
  if (stopBtn) stopBtn.textContent = "⏳ Stopping after current batch...";
  const btnDraftText = document.getElementById("btn-drafts-text");
  if (btnDraftText) btnDraftText.textContent = "⏳ Stopping after batch...";
  pushInlineLog("WARNING", "DraftGenerator", "⏸ Stop requested for Gemini draft generator. Halting cleanly after in-flight batch.");
}

async function generateDraftsForFilteredFaculty(triggerBtn = null) {
  if (isGeneratingDrafts) {
    stopDraftGeneration();
    return;
  }

  const btn = triggerBtn || document.getElementById("btn-generate-faculty-drafts");
  const spinner = document.getElementById("btn-drafts-spinner");
  const textEl = document.getElementById("btn-drafts-text");
  const stopBtn = document.getElementById("btn-stop-draft-workers");
  const progCard = document.getElementById("sup-worker-progress-card");
  const progBadge = document.getElementById("sup-tracker-badge");
  const progTitle = document.getElementById("sup-tracker-title");
  const progStats = document.getElementById("sup-tracker-stats");
  const progBar = document.getElementById("sup-tracker-bar");
  const progPct = document.getElementById("sup-tracker-pct");
  const progDetail = document.getElementById("sup-tracker-detail");

  const candidates = (filteredFacultyRecords && filteredFacultyRecords.length > 0 ? filteredFacultyRecords : allFacultyRecords).filter(f => f.email && f.email.includes("@"));

  if (candidates.length === 0) {
    alert("No supervisors with verified emails match the current filter. Crawl universities in Step 03 or adjust your filter first!");
    return;
  }

  isGeneratingDrafts = true;
  stopDraftsRequested = false;

  const workerCount = 3;
  const total = candidates.length;
  let done = 0;
  let generatedTotal = 0;

  if (btn) {
    btn.classList.add("btn-loading", "btn-danger");
    btn.classList.remove("btn-primary");
  }
  if (spinner) spinner.classList.remove("hidden");
  if (textEl) textEl.textContent = `⏹ Stop Draft Generator (0/${total} | ${workerCount}W)`;
  if (stopBtn) {
    stopBtn.classList.remove("hidden");
    stopBtn.textContent = "⏹ Stop Drafts";
  }
  if (progCard) progCard.classList.remove("hidden");

  pushInlineLog("INFO", "DraftGenerator", `🤖 Launching Gemini LLM Draft Generation across ${total} supervisors with ${workerCount} parallel workers...`);

  try {
    for (let i = 0; i < total; i += workerCount) {
      if (stopDraftsRequested) {
        pushInlineLog("WARNING", "DraftGenerator", `⏸ Draft generation paused by operator at ${done}/${total} supervisors.`);
        break;
      }

      const chunk = candidates.slice(i, i + workerCount);
      const chunkIds = chunk.map(c => c.id);
      const chunkNames = chunk.map(c => c.name).join(", ");
      const pct = Math.max(5, Math.round((done / total) * 100));

      if (textEl) textEl.textContent = `⏹ Stop Draft Generator (${done}/${total} | ${workerCount}W)`;
      if (progBadge) progBadge.textContent = `GEMINI SYNTHESIS ACTIVE`;
      if (progTitle) progTitle.textContent = `Synthesizing batch (${done + 1}–${Math.min(done + chunk.length, total)} of ${total}): ${chunkNames}`;
      if (progBar) progBar.style.width = `${pct}%`;
      if (progPct) progPct.textContent = `${pct}% (${done} / ${total} Drafts Generated)`;
      if (progDetail) progDetail.textContent = `Extracting lab digest & synthesizing personalized cold outreach (<200 words)...`;

      try {
        const res = await fetchWithAuth("/api/v1/drafts/generate-batch", {
          method: "POST",
          body: JSON.stringify({
            professor_ids: chunkIds,
            discipline: document.getElementById("sup-discipline-select")?.value || "Computer Science",
            max_workers: workerCount
          })
        });
        if (res.ok) {
          const generatedList = await res.json();
          generatedTotal += generatedList.length;
          if (progStats) progStats.textContent = `${generatedTotal} Outreach Drafts Created`;
          pushInlineLog("SUCCESS", "DraftGenerator", `✓ Generated ${generatedList.length} drafts for: ${chunkNames}`);
        }
      } catch (err) {
        pushInlineLog("ERROR", "DraftGenerator", `Batch error on (${chunkNames}): ${err}`);
      }

      done += chunk.length;
    }

    if (stopDraftsRequested) {
      if (progBadge) progBadge.textContent = `SYNTHESIS PAUSED`;
      if (progTitle) progTitle.textContent = `Paused at ${done}/${total} drafts. Generated drafts are preserved in Review Workspace.`;
    } else {
      if (progBadge) progBadge.textContent = `SYNTHESIS COMPLETE`;
      if (progTitle) progTitle.textContent = `Completed Gemini draft generation for ${total} supervisors!`;
      if (progBar) progBar.style.width = `100%`;
      if (progPct) progPct.textContent = `100% (${total}/${total} Generated)`;
      pushInlineLog("SUCCESS", "DraftGenerator", `✓ Finished generating drafts for ${total} supervisors. Ready for review in Tab 05!`);
    }
  } finally {
    isGeneratingDrafts = false;
    stopDraftsRequested = false;

    if (btn) {
      btn.classList.remove("btn-loading", "btn-danger");
      btn.classList.add("btn-primary");
    }
    if (spinner) spinner.classList.add("hidden");
    if (textEl) textEl.innerHTML = `🤖 Generate Gemini Drafts for Filtered Faculty (<span id="faculty-draft-candidate-count">${candidates.length}</span>)`;
    if (stopBtn) stopBtn.classList.add("hidden");
    loadDrafts();
  }
}

// Applicant CV & Background Context Management
async function loadApplicantProfile() {
  try {
    const res = await fetchWithAuth("/api/v1/prompts/applicant-profile");
    if (res.ok) {
      const p = await res.json();
      const nameEl = document.getElementById("app-full-name");
      const degEl = document.getElementById("app-degree");
      const projEl = document.getElementById("app-projects");
      const pubEl = document.getElementById("app-pubs");
      const cvBadge = document.getElementById("cv-status-badge");
      const fnLabel = document.getElementById("cv-filename-label");

      if (nameEl && p.name) nameEl.value = p.name;
      if (degEl && p.degree) degEl.value = p.degree;
      if (projEl && p.key_projects) projEl.value = (p.key_projects || []).join(", ");
      if (pubEl && p.publications) pubEl.value = (p.publications || []).join("; ");
      if (cvBadge) {
        if (p.cv_filename) {
          cvBadge.className = "badge badge-tier-1";
          cvBadge.textContent = `✓ CV: ${p.cv_filename}`;
        }
      }
      if (fnLabel && p.cv_filename) {
        fnLabel.textContent = `Loaded: ${p.cv_filename} (${(p.cv_raw_text || "").length} characters parsed via PyMuPDF)`;
      }
    }
  } catch (err) {
    console.warn("Could not load applicant profile:", err);
  }
}

async function saveApplicantProfile(btnEl = null) {
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.textContent = "⏳ Saving...";
  }

  const nameVal = document.getElementById("app-full-name")?.value || "Applicant";
  const degVal = document.getElementById("app-degree")?.value || "B.S. in Computer Science";
  const projRaw = document.getElementById("app-projects")?.value || "";
  const pubRaw = document.getElementById("app-pubs")?.value || "";

  const projects = projRaw.split(/[,;\n]/).map(s => s.trim()).filter(Boolean);
  const pubs = pubRaw.split(/[,;\n]/).map(s => s.trim()).filter(Boolean);

  try {
    const res = await fetchWithAuth("/api/v1/prompts/applicant-profile", {
      method: "POST",
      body: JSON.stringify({
        name: nameVal,
        degree: degVal,
        key_projects: projects,
        publications: pubs
      })
    });
    if (res.ok) {
      pushInlineLog("SUCCESS", "ApplicantProfile", "✓ Applicant CV & technical context saved to MongoDB.");
      alert("Applicant Profile Context saved! Gemini will now personalize outreach using your real projects and publications.");
    }
  } catch (err) {
    alert("Error saving profile: " + err);
  } finally {
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.textContent = "💾 Save Profile to DB";
    }
  }
}

async function uploadApplicantCv(inputEl) {
  if (!inputEl || !inputEl.files || inputEl.files.length === 0) return;
  const file = inputEl.files[0];
  const formData = new FormData();
  formData.append("file", file);

  const cvBadge = document.getElementById("cv-status-badge");
  const fnLabel = document.getElementById("cv-filename-label");
  if (cvBadge) cvBadge.textContent = "⏳ Uploading & Parsing...";

  try {
    const token = getAuthToken();
    const res = await fetch("/api/v1/prompts/upload-cv", {
      method: "POST",
      headers: token ? { "Authorization": `Bearer ${token}` } : {},
      body: formData
    });
    if (res.ok) {
      const updated = await res.json();
      if (cvBadge) {
        cvBadge.className = "badge badge-tier-1";
        cvBadge.textContent = `✓ CV: ${updated.cv_filename}`;
      }
      if (fnLabel) {
        fnLabel.textContent = `Uploaded ${updated.cv_filename} (${(updated.cv_raw_text || "").length} characters parsed via PyMuPDF)`;
      }
      pushInlineLog("SUCCESS", "ApplicantProfile", `✓ Uploaded CV '${updated.cv_filename}'. Background parsed for Gemini.`);
      alert(`CV '${updated.cv_filename}' successfully parsed! Its content is now active for all Gemini draft syntheses.`);
    }
  } catch (err) {
    alert("CV upload error: " + err);
    if (cvBadge) cvBadge.textContent = "Upload Failed";
  }
}

async function bulkApproveValidDrafts(btnEl = null) {
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.textContent = "⏳ Approving...";
  }

  try {
    const res = await fetchWithAuth("/api/v1/drafts/bulk-approve", {
      method: "POST",
      body: JSON.stringify({ max_words: 200 })
    });
    if (res.ok) {
      const data = await res.json();
      pushInlineLog("SUCCESS", "ReviewWorkspace", `✓ Bulk approved ${data.approved_count} valid outreach drafts.`);
      alert(`Bulk approval complete! ${data.approved_count} drafts approved and moved to Outbox Dispatcher (Tab 06).`);
      loadDrafts();
      loadDispatchQueue();
    }
  } catch (err) {
    alert("Bulk approval error: " + err);
  } finally {
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.textContent = "✓ Bulk Approve Valid Drafts (<200 Words)";
    }
  }
}

async function testSmtpConnection(btnEl = null) {
  const resultEl = document.getElementById("smtp-test-result");
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.textContent = "⏳ Testing Connection...";
  }
  if (resultEl) {
    resultEl.textContent = "Attempting SMTP handshake & authentication...";
    resultEl.style.color = "var(--text-secondary)";
  }

  try {
    const res = await fetchWithAuth("/api/v1/dispatch/test-smtp", { method: "POST" });
    const data = await res.json();
    if (data.success) {
      if (resultEl) {
        resultEl.textContent = `✓ ${data.message} (Sandbox: ${data.sandbox_mode ? "ON" : "OFF"})`;
        resultEl.style.color = "#10b981";
      }
      pushInlineLog("SUCCESS", "DispatchEngine", `✓ Live SMTP Connection Verified: ${data.message}`);
    } else {
      if (resultEl) {
        resultEl.textContent = `✗ ${data.message}`;
        resultEl.style.color = "#ef4444";
      }
      pushInlineLog("ERROR", "DispatchEngine", `✗ SMTP Test Failed: ${data.message}`);
    }
  } catch (err) {
    if (resultEl) {
      resultEl.textContent = `✗ Connection error: ${err}`;
      resultEl.style.color = "#ef4444";
    }
  } finally {
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.textContent = "🔌 Test Live SMTP Connection";
    }
  }
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

    const pendingCount = (currentDrafts || []).filter(d => d.status === "PENDING_REVIEW").length;
    const pendingBadge = document.getElementById("pending-drafts-badge");
    if (pendingBadge) pendingBadge.textContent = `${pendingCount} Pending Drafts`;

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
