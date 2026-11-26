/* AutoAdmit P12 Tabbed SaaS Workspace Controller */

const state = {
  universities: [],
  reviewItems: [],
  activeTab: "tab-trees",
  activeJobId: null,
  pollTimer: null,
  logOffset: 0,
  logTotal: 0,
  logEntries: [],
  drawerOpen: false
};

function esc(v) {
  return String(v ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function showToast(msg) {
  const el = document.getElementById("p12-toast");
  if (!el) return;
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.add("hidden"), 3500);
}

function switchTab(tabId, btnEl) {
  state.activeTab = tabId;
  document.querySelectorAll(".saas-tab-btn").forEach(b => b.classList.remove("active"));
  document.querySelectorAll(".saas-tab-pane").forEach(p => p.classList.remove("active"));
  if (btnEl) btnEl.classList.add("active");
  else {
    const match = document.querySelector(`.saas-tab-btn[data-tab="${tabId}"]`);
    if (match) match.classList.add("active");
  }
  const pane = document.getElementById(tabId);
  if (pane) pane.classList.add("active");
  if (tabId === "tab-analytics") loadAnalytics();
  if (tabId === "tab-professors") loadProfessors();
  if (tabId === "tab-review") loadNeedsReview();
}

function openAdminLogsDrawer(forceOpen = false) {
  const el = document.getElementById("admin-logs-drawer");
  const chev = document.getElementById("drawer-chevron");
  if (!el) return;
  state.drawerOpen = forceOpen ? true : !state.drawerOpen;
  el.classList.toggle("hidden", !state.drawerOpen);
  if (chev) chev.innerHTML = state.drawerOpen ? "&#9650; Collapse" : "&#9660; Expand";
  if (state.drawerOpen) el.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function toggleAdminLogsDrawer() {
  openAdminLogsDrawer(false);
}

function syncTogglePill(cb) {
  const row = cb.closest(".toggle-pill-row");
  if (!row) return;
  const badge = row.querySelector(".toggle-check-badge");
  row.classList.toggle("enabled", cb.checked);
  if (badge) badge.innerHTML = cb.checked ? "&#10003; Active" : "Off";
}

function copyText(text) {
  if (!text) return;
  navigator.clipboard?.writeText(text).then(() => showToast(`Copied: ${text}`)).catch(() => showToast(text));
}

// =========================================================================
// Data Export Helpers (Universities & Per-University Professors)
// =========================================================================
function downloadUniversities(fmt = "csv") {
  const region = (document.getElementById("f-regions")?.value || "").trim();
  const params = new URLSearchParams({ format: fmt, worked_only: "true" });
  if (region) params.set("region", region);
  window.location.href = `/api/v1/export/universities?${params.toString()}`;
  showToast(`Downloading worked universities${region ? ` (${region})` : ""} (${fmt.toUpperCase()})...`);
}

function downloadProfessors(domain = "", fmt = "csv") {
  const params = new URLSearchParams({ format: fmt });
  if (domain) {
    params.set("domain", domain);
  } else {
    const region = (document.getElementById("f-regions")?.value || "").trim();
    if (region) params.set("region", region);
  }
  window.location.href = `/api/v1/export/professors?${params.toString()}`;
  showToast(`Downloading professors${domain ? ` for ${domain}` : ""} (${fmt.toUpperCase()})...`);
}

function downloadFilteredProfessors(fmt = "csv") {
  const dom = document.getElementById("prof-domain-filter")?.value || "";
  downloadProfessors(dom, fmt);
}

function downloadRunLogsZip() {
  const jid = (document.getElementById("analytics-job-id")?.value || document.getElementById("log-job-id")?.value || state.activeJobId || "").trim();
  const q = jid ? `?job_id=${encodeURIComponent(jid)}` : "";
  window.location.href = `/api/v1/export/run-logs-zip${q}`;
  showToast(`Downloading complete Run Logs ZIP${jid ? ` (${jid})` : ""}...`);
}

function downloadDebugBundle() {
  const jid = (document.getElementById("analytics-job-id")?.value || state.activeJobId || "").trim();
  const q = jid ? `?job_id=${encodeURIComponent(jid)}` : "";
  window.location.href = `/api/v1/export/debug-bundle${q}`;
  showToast("Downloading full Debug Bundle JSON...");
}

function updateQueueModeBadge(qs) {
  const el = document.getElementById("hdr-queue-badge");
  if (!el || !qs) return;
  const mode = qs.queue_mode || "PARALLEL_4X";
  const conc = qs.active_concurrency ?? 4;
  el.textContent = `${mode} (${conc}x)`;
  el.className = `p12-badge ${mode.includes("THROTTLED") ? "p12-badge-warn" : "p12-badge-ok"}`;
}

// =========================================================================
// System Summary & Universities Overview (Tab 1)
// =========================================================================
async function loadSystemSummary() {
  try {
    const res = await fetch("/api/v1/system/summary");
    if (!res.ok) return;
    const d = await res.json();
    document.getElementById("kpi-universities").textContent = d.universities ?? 0;
    document.getElementById("kpi-depts").textContent = d.site_trees ?? d.university_departments ?? 0;
    document.getElementById("kpi-snapshots").textContent = d.page_snapshots ?? 0;
    document.getElementById("kpi-professors").textContent = d.professors ?? 0;
    document.getElementById("kpi-review").textContent = d.needs_review ?? 0;
    document.getElementById("tab-count-profs").textContent = d.professors ?? 0;
    document.getElementById("tab-count-review").textContent = d.needs_review ?? 0;
    document.getElementById("tab-count-analytics").textContent = d.api_call_traces ?? 0;
    document.getElementById("hdr-summary-text").textContent =
      `${d.universities ?? 0} Unis · ${d.professors ?? 0} Profs · ${d.needs_review ?? 0} Review`;
    if (d.queue_state) updateQueueModeBadge(d.queue_state);
  } catch (e) {
    console.error("Summary load error:", e);
  }
}

function populateDomainSelects(universities) {
  const domains = universities.map(u => u.domain).filter(Boolean);
  for (const id of ["prof-domain-filter", "review-domain-filter"]) {
    const sel = document.getElementById(id);
    if (!sel) continue;
    const current = sel.value;
    const firstLabel = id === "prof-domain-filter" ? "All Universities" : "All Domains";
    sel.innerHTML = `<option value="">${firstLabel}</option>` +
      domains.map(d => `<option value="${esc(d)}">${esc(d)}</option>`).join("");
    if (domains.includes(current)) sel.value = current;
  }

  // Populate Region dropdown dynamically with university counts
  const regSel = document.getElementById("f-regions");
  if (regSel && regSel.tagName === "SELECT") {
    const currentReg = regSel.value;
    const counts = {};
    universities.forEach(u => {
      const r = (u.region || "").trim();
      if (r) counts[r] = (counts[r] || 0) + 1;
    });
    const regions = Object.keys(counts).sort((a, b) => a.localeCompare(b));
    regSel.innerHTML = `<option value="">All Regions (${universities.length} unis)</option>` +
      regions.map(r => `<option value="${esc(r)}">${esc(r)} (${counts[r]})</option>`).join("");
    if (regions.includes(currentReg)) regSel.value = currentReg;
  }
}

async function loadUniversitiesOverview() {
  try {
    const res = await fetch("/api/v1/universities");
    if (!res.ok) return;
    state.universities = await res.json();
    populateDomainSelects(state.universities);
    renderUniversitiesTable();
  } catch (e) {
    console.error("Universities load error:", e);
  }
}

function getSelectedRegion() {
  return (document.getElementById("f-regions")?.value || "").trim().toLowerCase();
}

function getSelectedRegionDomains() {
  const reg = getSelectedRegion();
  if (!reg) return null;
  const set = new Set();
  for (const u of state.universities || []) {
    if ((u.region || "").trim().toLowerCase() === reg) {
      set.add((u.domain || "").toLowerCase());
    }
  }
  return set;
}

function onRegionFilterChange() {
  renderUniversitiesTable();
  loadProfessors();
  loadNeedsReview();
}

function renderUniversitiesTable() {
  const q = (document.getElementById("uni-search")?.value || "").trim().toLowerCase();
  const selectedRegion = getSelectedRegion();
  const rows = state.universities.filter(u => {
    if (selectedRegion && (u.region || "").trim().toLowerCase() !== selectedRegion) return false;
    if (!q) return true;
    return `${u.name || ""} ${u.chinese_name || ""} ${u.domain || ""} ${u.region || ""}`.toLowerCase().includes(q);
  });

  document.getElementById("tab-count-trees").textContent = rows.length;
  const tbody = document.getElementById("uni-table-body");
  if (!tbody) return;
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; color:var(--text-muted); padding:24px;">No universities match filter.</td></tr>`;
    return;
  }

  tbody.innerHTML = rows.map(u => {
    const st = u.status || "PENDING";
    const stCls = st === "COMPLETE" ? "p12-badge-ok" : st === "RUNNING" ? "p12-badge-info" : st === "NEEDS_REVIEW" ? "p12-badge-warn" : "p12-badge-muted";
    const navType = u.nav_type || "UNKNOWN";
    const navCls = navType === "SEMANTIC_NAV" ? "p12-badge-info" : navType === "DIV_BASED_NAV" ? "p12-badge-purple" : "p12-badge-muted";
    const rosterHtml = u.faculty_roster_url
      ? `<a href="${esc(u.faculty_roster_url)}" target="_blank" rel="noopener" style="color:var(--primary); word-break:break-all; font-size:11.5px;">${esc(u.faculty_roster_url)}</a>`
      : `<span style="color:var(--text-muted);">—</span>`;
    const errHtml = u.error_code ? `<div style="margin-top:3px;"><span class="p12-badge p12-badge-err">${esc(u.error_code)}</span></div>` : "";
    const profCount = u.professors_verified ?? 0;
    return `
      <tr>
        <td><strong>#${esc(u.rank ?? "-")}</strong></td>
        <td>
          <strong>${esc(u.name || u.domain)}</strong> ${u.chinese_name ? `<span style="color:var(--text-secondary);">(${esc(u.chinese_name)})</span>` : ""}
          <div style="font-size:11px; color:var(--text-muted);">${esc(u.region || "China")} &middot; <code>${esc(u.domain)}</code></div>
        </td>
        <td><span class="p12-badge ${navCls}">${esc(navType)}</span></td>
        <td>
          <span class="p12-badge ${stCls}">${esc(st)}</span>
          ${errHtml}
        </td>
        <td style="max-width:260px;">${rosterHtml}</td>
        <td>
          <strong>${esc(u.departments_mapped_count ?? 0)}</strong> depts
          <div style="font-size:11px; color:var(--text-muted); font-family:var(--font-mono);">${esc((u.token_stats && u.token_stats.total_tokens) ? `${u.token_stats.total_tokens} tok · ${u.token_stats.elapsed_sec ?? 0}s` : "—")}</div>
        </td>
        <td><strong style="color:${profCount > 0 ? "var(--accent-green)" : "var(--text-muted)"};">${esc(profCount)}</strong></td>
        <td style="text-align:center;">
          <div class="action-menu-wrap">
            <button class="action-dots-btn" onclick="toggleRowActionMenu(event, this)" title="Actions">&#8942;</button>
            <div class="action-dropdown">
              <button onclick="closeAllActionMenus(); viewSiteTree('${esc(u.domain)}')">&#127795; View Tree</button>
              <button onclick="closeAllActionMenus(); downloadProfessors('${esc(u.domain)}', 'csv')">&#8681; Download CSV</button>
              <button onclick="closeAllActionMenus(); downloadProfessors('${esc(u.domain)}', 'json')">&#8681; Download JSON</button>
            </div>
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

function closeAllActionMenus() {
  document.querySelectorAll(".action-dropdown.open").forEach(el => el.classList.remove("open"));
}

function toggleRowActionMenu(ev, btn) {
  ev.stopPropagation();
  const menu = btn.nextElementSibling;
  const wasOpen = menu && menu.classList.contains("open");
  closeAllActionMenus();
  if (menu && !wasOpen) menu.classList.add("open");
}

document.addEventListener("click", () => closeAllActionMenus());

function readFilters() {
  const country = (document.getElementById("f-country")?.value || "China").trim();
  const regionsRaw = (document.getElementById("f-regions")?.value || "").trim();
  const regions = regionsRaw ? regionsRaw.split(",").map(s => s.trim()).filter(Boolean) : [];
  const deptsRaw = (document.getElementById("f-departments")?.value || "Computer Science").trim();
  const departments = deptsRaw.split(",").map(s => s.trim()).filter(Boolean);
  const department = departments[0] || "Computer Science";
  const degree = document.getElementById("f-degree")?.value || "masters";
  const tier = document.getElementById("f-tier")?.value || "top_10";
  return { country, regions, departments, department, degree, tier };
}

function _attachJobStart(body, msg) {
  if (body.university_details && Object.keys(body.university_details).length) {
    state.universities = Object.values(body.university_details).sort((a, b) => (a.rank || 999) - (b.rank || 999));
    renderUniversitiesTable();
  }
  state.activeJobId = body.job_id;
  document.getElementById("log-job-id").value = body.job_id;
  document.getElementById("analytics-job-id").value = body.job_id;
  document.getElementById("log-file-label").textContent = `logs/jobs/${body.job_id}.jsonl`;
  state.logOffset = 0;
  state.logEntries = [];
  document.getElementById("log-viewer-box").innerHTML = "";
  document.getElementById("active-job-banner").classList.remove("hidden");
  document.getElementById("job-status-msg").textContent = msg;
  showToast(msg);
  startJobPolling(body.job_id);
}

// Step 1: Build & Verify Trees
async function buildTreesOnly(btn) {
  const { country, regions, department, degree, tier } = readFilters();
  const statusMsg = document.getElementById("job-status-msg");
  btn.disabled = true;
  if (statusMsg) statusMsg.textContent = "Starting Step 1: Build & Verify Trees...";
  try {
    const res = await fetch("/api/v1/trees/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ country, regions, department, degree, tier })
    });
    const body = await res.json();
    if (!res.ok) {
      if (statusMsg) statusMsg.textContent = `Error: ${body.detail || JSON.stringify(body)}`;
      showToast(`Error: ${body.detail || "Failed"}`);
      return;
    }
    _attachJobStart(body, `Step 1 Tree job ${body.job_id} queued (${body.target_domains.length} universities).`);
  } catch (e) {
    if (statusMsg) statusMsg.textContent = `Error: ${e.message}`;
  } finally {
    btn.disabled = false;
  }
}

// Step 2: Extract Professors from Verified Trees
async function extractFromVerifiedTrees(btn) {
  const { country, regions, department, degree, tier } = readFilters();
  const force_reextract = Boolean(document.getElementById("f-force-reextract")?.checked);
  const statusMsg = document.getElementById("job-status-msg");
  btn.disabled = true;
  if (statusMsg) statusMsg.textContent = "Starting Step 2: Extract Professors from Verified Trees...";
  try {
    const res = await fetch("/api/v1/trees/extract", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ country, regions, department, degree, tier, force_reextract })
    });
    const body = await res.json();
    if (!res.ok) {
      if (statusMsg) statusMsg.textContent = `Error: ${body.detail || JSON.stringify(body)}`;
      showToast(body.detail || "No verified trees found. Run Step 1 first.");
      return;
    }
    _attachJobStart(body, `Step 2 Extraction job ${body.job_id} queued (${body.target_domains.length} verified universities).`);
  } catch (e) {
    if (statusMsg) statusMsg.textContent = `Error: ${e.message}`;
  } finally {
    btn.disabled = false;
  }
}

// Full Pipeline (Step 1 + Step 2)
async function startDiscoveryJob(btn) {
  const { country, regions, departments, degree, tier } = readFilters();
  const statusMsg = document.getElementById("job-status-msg");
  btn.disabled = true;
  if (statusMsg) statusMsg.textContent = "Starting full pipeline job...";
  try {
    const res = await fetch("/api/v1/jobs/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ country, regions, departments, degree, tier })
    });
    const body = await res.json();
    if (!res.ok) {
      const detail = body.detail || JSON.stringify(body);
      if (statusMsg) statusMsg.textContent = `Blocked: ${detail}`;
      showToast(`Validation error: ${detail}`);
      return;
    }
    if (body.source === "database") {
      if (body.university_details && Object.keys(body.university_details).length) {
        state.universities = Object.values(body.university_details).sort((a, b) => (a.rank || 999) - (b.rank || 999));
        renderUniversitiesTable();
      }
      if (statusMsg) statusMsg.textContent = `Instant DB hit ($0): ${body.count} professors returned from MongoDB.`;
      showToast(`Served ${body.count} professors directly from MongoDB ($0)`);
      await Promise.all([loadProfessors(), loadSystemSummary()]);
      return;
    }
    _attachJobStart(body, `Full pipeline job ${body.job_id} queued (${body.target_domains.length} universities).`);
  } catch (e) {
    if (statusMsg) statusMsg.textContent = `Error: ${e.message}`;
  } finally {
    btn.disabled = false;
  }
}

function startJobPolling(jobId) {
  if (state.pollTimer) clearInterval(state.pollTimer);
  const poll = async () => {
    try {
      const res = await fetch(`/api/v1/jobs/${encodeURIComponent(jobId)}`);
      if (!res.ok) return;
      const job = await res.json();

      const completed = (job.completed_domains || []).length;
      const total = (job.target_domains || []).length || 1;
      const sc = job.scorecard || {};

      const hdrBadge = document.getElementById("hdr-job-badge");
      if (hdrBadge) {
        hdrBadge.textContent = `${job.job_id}: ${completed}/${total} (${job.status})`;
        hdrBadge.className = `p12-badge ${job.status === "COMPLETED" ? "p12-badge-ok" : "p12-badge-info"}`;
      }
      if (job.queue_mode) {
        updateQueueModeBadge({ queue_mode: job.queue_mode, active_concurrency: job.active_concurrency });
      }
      document.getElementById("banner-job-title").textContent =
        `Job ${job.job_id} — ${job.status} (${completed}/${total} universities completed)`;
      document.getElementById("banner-job-scorecard").textContent =
        `Verified Profs: ${sc.total_verified_professors ?? 0} · Rosters Verified: ${sc.rosters_verified ?? "-"} · Grounding: ${sc.grounding_pass_pct ?? 100}% · Failures: ${sc.failures ?? 0}`;

      if (job.university_details && Object.keys(job.university_details).length) {
        state.universities = Object.values(job.university_details).sort((a, b) => (a.rank || 999) - (b.rank || 999));
        renderUniversitiesTable();
      }

      await fetchIncrementalJobLogs(jobId);

      if (job.status === "COMPLETED" || job.status === "FAILED") {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
        await Promise.all([loadSystemSummary(), loadUniversitiesOverview(), loadProfessors(), loadNeedsReview(), loadAnalytics()]);
        showToast(`Job ${job.job_id} ${job.status}`);
      }
    } catch (e) {
      console.error("Poll error:", e);
    }
  };
  poll();
  state.pollTimer = setInterval(poll, 2000);
}

// =========================================================================
// Tree Modal Drawer
// =========================================================================
async function viewSiteTree(domain) {
  const modal = document.getElementById("tree-modal-backdrop");
  const title = document.getElementById("site-tree-title");
  const badge = document.getElementById("site-tree-nav-badge");
  const mdEl = document.getElementById("site-tree-md");
  const deptEl = document.getElementById("site-tree-depts");
  if (!modal) return;
  modal.classList.remove("hidden");
  title.textContent = `Site Tree — ${domain}`;
  badge.textContent = "...";
  mdEl.textContent = "Loading...";
  deptEl.textContent = "Loading...";
  try {
    const res = await fetch(`/api/v1/trees/${encodeURIComponent(domain)}`);
    if (!res.ok) {
      badge.textContent = "NOT BUILT";
      mdEl.textContent = `No saved site tree yet for ${domain}. Click "1. Build & Verify Trees" first.`;
      deptEl.textContent = "{}";
      return;
    }
    const d = await res.json();
    badge.textContent = d.nav_type || "UNKNOWN";
    badge.className = `p12-badge ${d.nav_type === "SEMANTIC_NAV" ? "p12-badge-info" : d.nav_type === "DIV_BASED_NAV" ? "p12-badge-purple" : "p12-badge-muted"}`;
    const ts = d.token_stats || {};
    const tokEl = document.getElementById("site-tree-tokens");
    if (tokEl) {
      tokEl.textContent = `Tokens: ${ts.total_tokens ?? 0} total (Qwen: ${ts.qwen_tokens ?? 0}, DeepSeek: ${ts.deepseek_tokens ?? 0}, Gemini: ${ts.gemini_tokens ?? 0}) · Elapsed: ${ts.elapsed_sec ?? 0}s`;
    }
    mdEl.textContent = d.markdown_tree || "(empty tree)";
    deptEl.textContent = JSON.stringify({
      verified_rosters: d.verified_rosters || {},
      departments_map: d.departments_map || {}
    }, null, 2);
    const trailEl = document.getElementById("site-tree-trail");
    if (trailEl) {
      trailEl.textContent = JSON.stringify(d.navigation_trail || [], null, 2);
    }
  } catch (e) {
    mdEl.textContent = `Error: ${e.message}`;
  }
}

function closeTreeModal() {
  document.getElementById("tree-modal-backdrop")?.classList.add("hidden");
}

// =========================================================================
// Tab 2: Bilingual Verified Professors Table
// =========================================================================
function _initials(nameEn, nameZh) {
  const src = (nameEn || nameZh || "?").trim();
  const parts = src.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return src.slice(0, 2).toUpperCase();
}

async function loadProfessors() {
  const search = (document.getElementById("prof-search")?.value || "").trim();
  const domain = document.getElementById("prof-domain-filter")?.value || "";
  const emailSt = document.getElementById("prof-email-filter")?.value || "";
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (domain) params.set("domain", domain);
  if (emailSt) params.set("email_status", emailSt);

  try {
    const res = await fetch(`/api/v1/professors?${params.toString()}`);
    if (!res.ok) return;
    let profs = await res.json();
    const regionDomains = getSelectedRegionDomains();
    if (regionDomains) {
      profs = profs.filter(p => regionDomains.has((p.university_domain || "").toLowerCase()));
    }
    document.getElementById("tab-count-profs").textContent = profs.length;
    const container = document.getElementById("prof-grouped-container");
    if (!container) return;
    if (!profs.length) {
      container.innerHTML = `<div style="text-align:center; color:var(--text-muted); padding:24px;">No verified professors match filters.</div>`;
      return;
    }

    // Group professors by university_domain (showing uni name, Chinese name, region, count; click to expand)
    const uniMeta = {};
    for (const u of state.universities || []) {
      uniMeta[(u.domain || "").toLowerCase()] = u;
    }
    const groups = new Map();
    for (const p of profs) {
      const dom = (p.university_domain || "unknown").toLowerCase();
      if (!groups.has(dom)) groups.set(dom, []);
      groups.get(dom).push(p);
    }

    const autoOpen = Boolean(search || domain || groups.size === 1);
    const orderedGroups = [...groups.entries()].sort((a, b) => {
      const ra = uniMeta[a[0]]?.rank ?? 9999;
      const rb = uniMeta[b[0]]?.rank ?? 9999;
      return ra - rb || b[1].length - a[1].length;
    });

    container.innerHTML = orderedGroups.map(([dom, list]) => {
      const meta = uniMeta[dom] || {};
      const uniTitle = meta.name || dom;
      const uniZh = meta.chinese_name ? ` (${meta.chinese_name})` : "";
      const uniRegion = meta.region || "China";
      const rowsHtml = list.map(p => {
        const nameEn = p.name_en || p.name || "";
        const nameZh = p.name && p.name !== nameEn ? p.name : "";
        const titleEn = p.title_en || p.title || "—";
        const inits = esc(_initials(nameEn, p.name));
        const avatarHtml = p.photo_url
          ? `<img class="prof-avatar" src="${esc(p.photo_url)}" alt="${inits}" onerror="this.outerHTML='<span class=\\'prof-avatar-fallback\\'>${inits}</span>'" />`
          : `<span class="prof-avatar-fallback">${inits}</span>`;
        const emailCls = p.email_status === "FOUND" ? "p12-badge-ok" : "p12-badge-warn";
        const degs = (p.degree_eligibility || []).map(d => `<span class="p12-badge p12-badge-info">${esc(d)}</span>`).join(" ");
        const areas = (p.research_areas_en && p.research_areas_en.length ? p.research_areas_en : (p.research_interests || [])).slice(0, 4);
        const topics = areas.map(t => `<span class="p12-badge p12-badge-muted" style="margin:1px;">${esc(t)}</span>`).join(" ");
        const copyBtn = p.email ? `<button class="copy-btn" onclick="copyText('${esc(p.email)}')" title="Copy email">&#128203;</button>` : "";
        return `
          <tr>
            <td>
              <div class="prof-cell">
                ${avatarHtml}
                <div>
                  <div style="font-weight:700; color:var(--text-primary);">${esc(nameEn)}</div>
                  ${nameZh ? `<div style="font-size:11.5px; color:var(--text-secondary);">${esc(nameZh)}</div>` : ""}
                  <a href="${esc(p.canonical_profile_url)}" target="_blank" rel="noopener" style="font-size:11px; color:var(--primary);">Profile &nearr;</a>
                </div>
              </div>
            </td>
            <td><div class="line-clamp-2" title="${esc(titleEn)}">${esc(titleEn)}</div></td>
            <td><div style="font-size:11.5px; color:var(--text-secondary);">${esc(p.department)}</div></td>
            <td>${degs || "—"}</td>
            <td style="max-width:220px;">${topics || "—"}</td>
            <td>
              <div style="display:flex; align-items:center;"><code>${esc(p.email || "—")}</code>${copyBtn}</div>
              <span class="p12-badge ${emailCls}" style="margin-top:3px;">${esc(p.email_status)}</span>
            </td>
          </tr>
        `;
      }).join("");

      return `
        <div class="prof-uni-group ${autoOpen ? "open" : ""}">
          <div class="prof-uni-hdr" onclick="this.parentElement.classList.toggle('open')">
            <div>
              <span class="prof-uni-chev">&#9654;</span>
              <strong>${esc(uniTitle)}</strong><span style="color:var(--text-secondary);">${esc(uniZh)}</span>
              <span class="p12-badge p12-badge-muted" style="margin-left:6px;">${esc(uniRegion)}</span>
              <code style="margin-left:6px; font-size:11px; color:var(--text-muted);">${esc(dom)}</code>
            </div>
            <div style="display:flex; align-items:center; gap:6px;" onclick="event.stopPropagation()">
              <span class="p12-badge p12-badge-ok">${list.length} prof${list.length > 1 ? "s" : ""}</span>
              <button class="btn btn-secondary btn-sm" onclick="downloadProfessors('${esc(dom)}', 'csv')">&#8681; CSV</button>
              <button class="btn btn-secondary btn-sm" onclick="downloadProfessors('${esc(dom)}', 'json')">JSON</button>
            </div>
          </div>
          <div class="prof-uni-body">
            <table class="saas-table">
              <thead>
                <tr>
                  <th>Professor (EN / ZH)</th>
                  <th>Title</th>
                  <th>Department</th>
                  <th>Degree</th>
                  <th>Research Areas (EN)</th>
                  <th>Email &amp; Status</th>
                </tr>
              </thead>
              <tbody>${rowsHtml}</tbody>
            </table>
          </div>
        </div>
      `;
    }).join("");
  } catch (e) {
    console.error("Professors load error:", e);
  }
}

// =========================================================================
// Tab 3: Needs Review
// =========================================================================
async function loadNeedsReview() {
  const domain = document.getElementById("review-domain-filter")?.value || "";
  const errorCode = document.getElementById("review-error-filter")?.value || "";
  const params = new URLSearchParams();
  if (domain) params.set("domain", domain);
  if (errorCode) params.set("error_code", errorCode);
  try {
    const res = await fetch(`/api/v1/needs-review?${params.toString()}`);
    if (!res.ok) return;
    let items = await res.json();
    const regionDomains = getSelectedRegionDomains();
    if (regionDomains) {
      items = items.filter(it => regionDomains.has((it.domain || "").toLowerCase()));
    }
    state.reviewItems = items;
    document.getElementById("tab-count-review").textContent = items.length;
    const tbody = document.getElementById("review-table-body");
    if (!items.length) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:var(--text-muted); padding:24px;">No items in needs_review.</td></tr>`;
      return;
    }
    tbody.innerHTML = items.map((it, idx) => `
      <tr>
        <td><code>${esc(it.domain)}</code></td>
        <td><span class="p12-badge p12-badge-muted">${esc(it.stage)}</span></td>
        <td><span class="p12-badge p12-badge-err">${esc(it.error_code)}</span></td>
        <td style="font-size:12px; max-width:340px;">${esc(it.detail)}</td>
        <td style="max-width:240px; word-break:break-all;">${it.url ? `<a href="${esc(it.url)}" target="_blank" rel="noopener" style="color:var(--primary); font-size:11.5px;">${esc(it.url)}</a>` : "—"}</td>
        <td><button class="btn btn-secondary btn-sm" onclick="inspectReviewAudit(${idx})">Inspect</button></td>
      </tr>
    `).join("");
  } catch (e) {
    console.error("Needs review load error:", e);
  }
}

function inspectReviewAudit(idx) {
  const it = state.reviewItems[idx];
  if (!it) return;
  const modal = document.getElementById("audit-modal-backdrop");
  if (!modal) return;
  modal.classList.remove("hidden");
  document.getElementById("audit-modal-title").textContent = `${it.domain} · ${it.error_code}`;
  document.getElementById("audit-modal-meta").textContent = `Stage: ${it.stage} · URL: ${it.url || "-"} · ${it.detail}`;
  const ga = it.grounding_audit || {};
  document.getElementById("audit-modal-llm").textContent = JSON.stringify({
    extracted_quotes: ga.extracted_quotes || {},
    raw_llm_output: ga.raw_llm_output || "(not recorded)",
    payload: it.payload || {}
  }, null, 2);
  document.getElementById("audit-modal-md").textContent = ga.markdown_excerpt || "(no markdown excerpt saved)";
}

function closeAuditModal() {
  document.getElementById("audit-modal-backdrop")?.classList.add("hidden");
}

// =========================================================================
// Tab 4: LLM & API Analytics + Trace Modal
// =========================================================================
const PROVIDER_LABELS = {
  colab_qwen: "Qwen(C)",
  deepseek: "DeepSeek (Tier 2)",
  gemini: "Gemini (Tier 3)",
  serper: "Serper Search"
};

async function refreshAnalyticsJobsDropdown() {
  const sel = document.getElementById("analytics-job-id");
  if (!sel || sel.tagName !== "SELECT") return;
  const prev = sel.value;
  try {
    const res = await fetch("/api/v1/analytics/jobs");
    if (!res.ok) return;
    const jobs = await res.json();
    sel.innerHTML = `<option value="">All Time (All Jobs)</option>` +
      jobs.map(j => `<option value="${esc(j.job_id)}">${esc(j.job_id)} (${j.calls} calls)</option>`).join("");
    if (prev && [...sel.options].some(o => o.value === prev)) {
      sel.value = prev;
    }
  } catch (_) {}
}

async function refreshConnections(btn) {
  const orig = btn ? btn.textContent : "";
  if (btn) { btn.disabled = true; btn.textContent = "Checking..."; }
  try {
    const res = await fetch("/api/v1/analytics/refresh-connections", { method: "POST" });
    if (res.ok) {
      const data = await res.json();
      if (data.queue_state) updateQueueModeBadge(data.queue_state);
      const pill = document.getElementById("colab-gpu-pill");
      const g = data.gpu || {};
      if (pill) {
        if (g.loaded) {
          pill.className = "p12-badge p12-badge-ok";
          pill.textContent = `Live GPU (${g.engine || "vllm"}): ${g.vram_used_mb ?? g.vram_allocated_mb ?? 0}/${g.vram_total_mb ?? 0} MB · Active: ${g.active_requests ?? 0}`;
        } else {
          pill.className = "p12-badge p12-badge-err";
          pill.textContent = `Qwen(C) GPU: ${g.status || "offline"}`;
        }
      }
      await loadAnalytics();
    }
  } catch (e) {
    console.error("Refresh connections error:", e);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = orig; }
  }
}

async function clearAnalyticsTraces() {
  const jobId = (document.getElementById("analytics-job-id")?.value || "").trim();
  const scope = jobId ? `traces for job '${jobId}'` : "ALL historical API traces";
  if (!confirm(`Clear ${scope}? (Professors and site trees are NOT affected.)`)) return;
  try {
    const url = jobId ? `/api/v1/analytics/traces?job_id=${encodeURIComponent(jobId)}` : "/api/v1/analytics/traces";
    const res = await fetch(url, { method: "DELETE" });
    if (res.ok) {
      const sel = document.getElementById("analytics-job-id");
      if (sel && sel.tagName === "SELECT") sel.value = "";
      await loadAnalytics();
    }
  } catch (e) {
    console.error("Clear traces error:", e);
  }
}

async function loadAnalytics() {
  await refreshAnalyticsJobsDropdown();
  const jobId = (document.getElementById("analytics-job-id")?.value || "").trim();
  const provider = document.getElementById("analytics-provider-filter")?.value || "";
  const statusFilter = document.getElementById("analytics-status-filter")?.value || "";

  const ovParams = new URLSearchParams();
  if (jobId) ovParams.set("job_id", jobId);
  const trParams = new URLSearchParams({ limit: "60" });
  if (jobId) trParams.set("job_id", jobId);
  if (provider) trParams.set("provider", provider);
  if (statusFilter) trParams.set("status", statusFilter);

  try {
    const [ovRes, trRes, gpuRes, benchRes] = await Promise.all([
      fetch(`/api/v1/analytics/overview?${ovParams.toString()}`),
      fetch(`/api/v1/analytics/traces?${trParams.toString()}`),
      fetch("/api/v1/analytics/colab-gpu"),
      fetch("/api/v1/analytics/benchmarks")
    ]);
    if (gpuRes.ok) {
      const g = await gpuRes.json();
      const pill = document.getElementById("colab-gpu-pill");
      if (pill) {
        if (g.loaded) {
          pill.className = "p12-badge p12-badge-ok";
          pill.textContent = `Live GPU (${g.engine || "vllm"}): ${g.vram_used_mb ?? g.vram_allocated_mb ?? 0}/${g.vram_total_mb ?? 0} MB · Active: ${g.active_requests ?? 0}`;
        } else {
          pill.className = "p12-badge p12-badge-err";
          pill.textContent = `Colab GPU: ${g.status || "offline"}`;
        }
      }
    }
    if (benchRes.ok) {
      const benchRuns = await benchRes.json();
      renderBenchmarkHistory(benchRuns);
      renderBenchmarkChart(benchRuns);
    }
    if (ovRes.ok) {
      const ov = await ovRes.json();
      renderAnalyticsCharts(ov);
      if (ov.queue_state) updateQueueModeBadge(ov.queue_state);
      const cardsEl = document.getElementById("analytics-provider-cards");
      const order = ["colab_qwen", "deepseek", "gemini", "serper"];
      let totalCalls = 0;
      const conns = ov.connections || {};
      cardsEl.innerHTML = order.map(key => {
        const p = (ov.providers || {})[key] || { total_calls: 0, ok_count: 0, failed_count: 0, avg_latency_ms: 0, max_latency_ms: 0, total_tokens: 0, last_error: null };
        const conn = conns[key] || { live: false, configured: false, label: "Unknown" };
        totalCalls += p.total_calls;
        const hasErr = p.failed_count > 0;
        const connBadge = conn.live
          ? `<span class="p12-badge p12-badge-ok">&#9679; ${esc(conn.label)}</span>`
          : conn.configured
            ? `<span class="p12-badge p12-badge-err">&#9679; ${esc(conn.label)}</span>`
            : `<span class="p12-badge p12-badge-muted">${esc(conn.label)}</span>`;
        const statusBadge = p.total_calls === 0
          ? connBadge
          : hasErr
            ? `${connBadge} <span class="p12-badge p12-badge-err">Alert (${p.failed_count} fail)</span>`
            : `${connBadge} <span class="p12-badge p12-badge-info">Healthy</span>`;
        const errBox = p.last_error
          ? `<div class="provider-err-box"><strong>${esc(p.last_error.status)}</strong>: ${esc(p.last_error.detail)}</div>`
          : "";
        return `
          <div class="provider-card ${hasErr || (conn.configured && !conn.live) ? "has-error" : ""}">
            <div class="provider-hdr">
              <span class="provider-name">${esc(PROVIDER_LABELS[key] || key)}</span>
              ${statusBadge}
            </div>
            <div class="provider-stats">
              <div>Calls: <strong>${p.total_calls}</strong></div>
              <div>OK / Fail: <strong style="color:var(--accent-green);">${p.ok_count}</strong> / <strong style="color:${hasErr ? "var(--accent-red)" : "var(--text-muted)"};">${p.failed_count}</strong></div>
              <div>Avg: <strong>${p.avg_latency_ms} ms</strong></div>
              <div>Max: <strong>${p.max_latency_ms} ms</strong></div>
              <div style="grid-column:span 2;">Tokens: <strong>${p.total_tokens ?? 0}</strong></div>
            </div>
            ${errBox}
          </div>
        `;
      }).join("");
      document.getElementById("tab-count-analytics").textContent = totalCalls;

      const failBox = document.getElementById("analytics-failure-summary");
      const breaks = ov.failure_breakdown || [];
      if (!breaks.length) {
        failBox.className = "failure-box clean";
        failBox.innerHTML = "&#10003; No API breakages, tunnel drops, or auth errors recorded.";
      } else {
        failBox.className = "failure-box";
        failBox.innerHTML = `<strong>Failure / Breakage Summary (${breaks.length} pattern${breaks.length > 1 ? "s" : ""}):</strong>` +
          breaks.map(b => `<div style="margin-top:4px;"><span class="p12-badge p12-badge-err">${esc(b.provider)}</span> <span class="p12-badge p12-badge-warn">${esc(b.status)} &times; ${b.count}</span> <span style="color:var(--text-secondary);">${esc(b.error_detail)}</span></div>`).join("");
      }
    }

    if (trRes.ok) {
      const traces = await trRes.json();
      const tbody = document.getElementById("analytics-traces-body");
      if (!traces.length) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:var(--text-muted); padding:20px;">No API traces match filter.</td></tr>`;
      } else {
        tbody.innerHTML = traces.map(t => {
          const ok = t.status === "ok";
          const stCls = ok ? "p12-badge-ok" : "p12-badge-err";
          const ts = (t.created_at || "").replace("T", " ").slice(11, 19);
          return `
            <tr class="clickable-row" onclick="openTraceDetail('${esc(t.trace_id)}')" title="Click to inspect full sent prompt & raw response">
              <td style="font-family:var(--font-mono); font-size:11.5px;">${esc(ts)}</td>
              <td><strong>${esc(t.provider)}</strong><div style="font-size:11px; color:var(--text-muted);">${esc(t.model)}</div></td>
              <td><span class="p12-badge p12-badge-muted">${esc(t.stage || "-")}</span><div style="font-size:11px; color:var(--text-secondary);">${esc(t.domain || "-")}</div></td>
              <td><span class="p12-badge ${stCls}">${esc(t.status)}</span></td>
              <td style="font-family:var(--font-mono);"><strong>${esc(t.latency_ms)} ms</strong><div style="font-size:10.5px; color:var(--text-muted);">${esc(t.total_tokens ?? 0)} tok</div></td>
              <td style="font-size:11.5px; color:var(--text-secondary); max-width:280px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${esc(t.error_detail || "OK (click to inspect)")}</td>
            </tr>
          `;
        }).join("");
      }
    }
  } catch (e) {
    console.error("Analytics load error:", e);
  }
}

const _analyticsCharts = {};

function _mountChart(canvasId, config) {
  if (typeof Chart === "undefined") return;
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  if (_analyticsCharts[canvasId]) {
    try { _analyticsCharts[canvasId].destroy(); } catch (_) {}
  }
  _analyticsCharts[canvasId] = new Chart(canvas.getContext("2d"), config);
}

function renderAnalyticsCharts(ov) {
  if (typeof Chart === "undefined") return;
  const order = ["colab_qwen", "deepseek", "gemini", "serper"];
  const labels = order.map(k => (PROVIDER_LABELS[k] || k).replace(/\s*\(Tier \d\)/, ""));
  const provs = ov.providers || {};

  // 1. API Calls & Health by Provider (Stacked Bar)
  _mountChart("chart-provider-calls", {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "OK Calls",
          data: order.map(k => (provs[k]?.ok_count) || 0),
          backgroundColor: "rgba(22, 163, 74, 0.82)",
          borderRadius: 4,
        },
        {
          label: "Failed / 429 / Timeout",
          data: order.map(k => (provs[k]?.failed_count) || 0),
          backgroundColor: "rgba(220, 38, 38, 0.80)",
          borderRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: "bottom", labels: { boxWidth: 12, font: { size: 11 } } } },
      scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true } },
    },
  });

  // 2. Token Usage by Provider (Grouped Bar: Prompt vs Completion)
  _mountChart("chart-provider-tokens", {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Prompt Tokens",
          data: order.map(k => (provs[k]?.prompt_tokens) || 0),
          backgroundColor: "rgba(37, 99, 235, 0.82)",
          borderRadius: 4,
        },
        {
          label: "Completion Tokens",
          data: order.map(k => (provs[k]?.completion_tokens) || 0),
          backgroundColor: "rgba(124, 58, 237, 0.82)",
          borderRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: "bottom", labels: { boxWidth: 12, font: { size: 11 } } } },
      scales: { y: { beginAtZero: true } },
    },
  });

  // 3. Calls & Token Usage Over Time (Dual-Axis Bar + Line)
  const timeline = ov.timeline || [];
  _mountChart("chart-usage-timeline", {
    type: "bar",
    data: {
      labels: timeline.map(t => t.bucket),
      datasets: [
        {
          type: "bar",
          label: "OK Calls",
          data: timeline.map(t => t.ok_count || 0),
          backgroundColor: "rgba(16, 185, 129, 0.72)",
          yAxisID: "y",
          stack: "calls",
          borderRadius: 3,
        },
        {
          type: "bar",
          label: "Failed Calls",
          data: timeline.map(t => t.failed_count || 0),
          backgroundColor: "rgba(239, 68, 68, 0.72)",
          yAxisID: "y",
          stack: "calls",
          borderRadius: 3,
        },
        {
          type: "line",
          label: "Total Tokens",
          data: timeline.map(t => t.total_tokens || 0),
          borderColor: "#2563eb",
          backgroundColor: "rgba(37, 99, 235, 0.12)",
          yAxisID: "y1",
          tension: 0.28,
          fill: false,
          pointRadius: 3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: "bottom", labels: { boxWidth: 12, font: { size: 11 } } } },
      scales: {
        x: { stacked: true, ticks: { maxRotation: 35, font: { size: 10 } } },
        y: { stacked: true, beginAtZero: true, position: "left", title: { display: true, text: "Calls", font: { size: 10 } } },
        y1: { beginAtZero: true, position: "right", grid: { drawOnChartArea: false }, title: { display: true, text: "Tokens", font: { size: 10 } } },
      },
    },
  });
}

function renderBenchmarkChart(runs) {
  if (typeof Chart === "undefined") return;
  const ordered = [...(runs || [])].reverse().slice(-20);
  _mountChart("chart-benchmark-perf", {
    type: "bar",
    data: {
      labels: ordered.map(r => `${r.concurrency}x ${r.payload_size.replace("_", " ")}`),
      datasets: [
        {
          type: "bar",
          label: "Speed (Req/Min)",
          data: ordered.map(r => r.requests_per_min || 0),
          backgroundColor: "rgba(37, 99, 235, 0.78)",
          yAxisID: "y",
          borderRadius: 4,
        },
        {
          type: "line",
          label: "Avg Latency (ms)",
          data: ordered.map(r => r.avg_latency_ms || 0),
          borderColor: "#f59e0b",
          backgroundColor: "rgba(245, 158, 11, 0.15)",
          yAxisID: "y1",
          tension: 0.25,
          pointRadius: 3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: "bottom", labels: { boxWidth: 12, font: { size: 11 } } } },
      scales: {
        x: { ticks: { maxRotation: 40, font: { size: 10 } } },
        y: { beginAtZero: true, position: "left", title: { display: true, text: "Req/Min", font: { size: 10 } } },
        y1: { beginAtZero: true, position: "right", grid: { drawOnChartArea: false }, title: { display: true, text: "Latency (ms)", font: { size: 10 } } },
      },
    },
  });
}

function renderBenchmarkHistory(runs) {
  const tbody = document.getElementById("benchmark-history-body");
  if (!tbody) return;
  if (!runs || !runs.length) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; color:var(--text-muted); padding:14px;">No benchmark runs yet.</td></tr>`;
    return;
  }
  tbody.innerHTML = runs.map((r, i) => `
    <tr>
      <td><code>#${runs.length - i} (${esc(r.run_id)})</code></td>
      <td><strong>${esc(r.provider)}</strong><div style="font-size:11px; color:var(--text-muted);">${esc(r.model)}</div></td>
      <td><span class="p12-badge p12-badge-info">${esc(r.concurrency)}x</span> <span class="p12-badge p12-badge-muted">${esc(r.payload_size)}</span></td>
      <td style="font-family:var(--font-mono);">${esc(r.avg_input_tokens)} / ${esc(r.avg_output_tokens)}</td>
      <td style="font-family:var(--font-mono);">${esc((r.total_time_ms / 1000).toFixed(2))}s</td>
      <td style="font-family:var(--font-mono);">${esc(r.avg_latency_ms)} / ${esc(r.max_latency_ms)} ms</td>
      <td style="font-family:var(--font-mono);"><strong style="color:var(--accent-green);">${esc(r.requests_per_min)} req/m</strong></td>
      <td style="font-family:var(--font-mono);">${esc(r.ok_count)} / <span style="color:${r.fail_count ? "var(--accent-red)" : "var(--text-muted)"};">${esc(r.fail_count)}</span></td>
    </tr>
  `).join("");
}

async function runStressBenchmark(btn) {
  const provider = document.getElementById("bench-provider")?.value || "colab_qwen";
  const concurrency = parseInt(document.getElementById("bench-concurrency")?.value || "2", 10);
  const payload_size = document.getElementById("bench-payload")?.value || "nav_500";
  const batch_size = parseInt(document.getElementById("bench-batch")?.value || "5", 10);
  const msg = document.getElementById("bench-status-msg");
  btn.disabled = true;
  if (msg) msg.textContent = `Running ${batch_size} requests on ${provider} (conc=${concurrency}, ${payload_size})...`;
  try {
    const res = await fetch("/api/v1/analytics/benchmark", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider, concurrency, payload_size, batch_size })
    });
    const d = await res.json();
    if (!res.ok) {
      if (msg) msg.textContent = `Benchmark failed: ${d.detail || JSON.stringify(d)}`;
      return;
    }
    if (msg) msg.textContent = `Done (${d.run_id}): ${d.ok_count}/${d.batch_size} OK · Avg ${d.avg_latency_ms}ms · ${d.requests_per_min} req/min`;
    showToast(`Benchmark done: ${d.requests_per_min} req/min (${d.ok_count}/${d.batch_size} OK)`);
    await loadAnalytics();
  } catch (e) {
    if (msg) msg.textContent = `Error: ${e.message}`;
  } finally {
    btn.disabled = false;
  }
}

async function openTraceDetail(traceId) {
  const modal = document.getElementById("trace-modal-backdrop");
  if (!modal) return;
  modal.classList.remove("hidden");
  document.getElementById("trace-modal-title").textContent = `Trace ${traceId}`;
  document.getElementById("trace-modal-meta").textContent = "Loading...";
  document.getElementById("trace-modal-req").textContent = "Loading...";
  document.getElementById("trace-modal-res").textContent = "Loading...";
  document.getElementById("trace-modal-error").classList.add("hidden");
  try {
    const res = await fetch(`/api/v1/analytics/traces/${encodeURIComponent(traceId)}`);
    if (!res.ok) return;
    const t = await res.json();
    document.getElementById("trace-modal-title").textContent = `${t.provider} · ${t.model} (${t.status})`;
    document.getElementById("trace-modal-meta").textContent =
      `Trace: ${t.trace_id} · Job: ${t.job_id || "-"} · Domain: ${t.domain || "-"} · Stage: ${t.stage || "-"} · HTTP: ${t.http_status ?? "-"} · Latency: ${t.latency_ms} ms`;
    if (t.error_detail) {
      const errEl = document.getElementById("trace-modal-error");
      errEl.textContent = t.error_detail;
      errEl.classList.remove("hidden");
    }
    document.getElementById("trace-modal-req").textContent = t.request_payload || "(empty)";
    document.getElementById("trace-modal-res").textContent = t.response_payload || "(empty)";
  } catch (e) {
    document.getElementById("trace-modal-req").textContent = `Error: ${e.message}`;
  }
}

function closeTraceModal() {
  document.getElementById("trace-modal-backdrop")?.classList.add("hidden");
}

// =========================================================================
// Live Un-Truncated Run Logs Viewer
// =========================================================================
async function fetchIncrementalJobLogs(jobId) {
  if (!jobId) return;
  const level = document.getElementById("log-level-filter")?.value || "";
  const domain = (document.getElementById("log-domain-filter")?.value || "").trim();
  const params = new URLSearchParams({ offset: String(state.logOffset), limit: "500" });
  if (level) params.set("level", level);
  if (domain) params.set("domain", domain);

  try {
    const res = await fetch(`/api/v1/jobs/${encodeURIComponent(jobId)}/logs?${params.toString()}`);
    if (!res.ok) return;
    const d = await res.json();
    state.logTotal = d.total;
    const box = document.getElementById("log-viewer-box");
    if (d.entries && d.entries.length) {
      const frag = document.createDocumentFragment();
      d.entries.forEach(entry => {
        state.logEntries.push(entry);
        const div = document.createElement("div");
        const lvl = String(entry.level || "info").toLowerCase();
        div.className = `p12-log-line ${lvl}`;
        div.textContent = `[${entry.timestamp || ""}] [${lvl.toUpperCase()}] [${entry.module || ""}] ${entry.domain ? `[${entry.domain}] ` : ""}${entry.event || ""} ${JSON.stringify(entry)}`;
        frag.appendChild(div);
      });
      box.appendChild(frag);
      state.logOffset = d.next_offset;
      if (document.getElementById("log-autoscroll")?.checked) {
        box.scrollTop = box.scrollHeight;
      }
    }
    document.getElementById("log-loaded-count").textContent = state.logEntries.length;
    document.getElementById("log-total-count").textContent = state.logTotal;
  } catch (e) {
    console.error("Log stream error:", e);
  }
}

async function reloadLogsFromStart() {
  const jid = (document.getElementById("log-job-id")?.value || state.activeJobId || "").trim();
  if (!jid) return;
  state.logOffset = 0;
  state.logEntries = [];
  document.getElementById("log-file-label").textContent = `logs/jobs/${jid}.jsonl`;
  document.getElementById("log-viewer-box").innerHTML = "";
  while (true) {
    const prev = state.logOffset;
    await fetchIncrementalJobLogs(jid);
    if (state.logOffset === prev || state.logOffset >= state.logTotal) break;
  }
}

function downloadCurrentJobLogs() {
  const jid = (document.getElementById("log-job-id")?.value || state.activeJobId || "").trim();
  if (!jid) {
    showToast("Enter or start a job_id first.");
    return;
  }
  window.location.href = `/api/v1/jobs/${encodeURIComponent(jid)}/logs/download`;
}

// =========================================================================
// Admin Config & 3-Step Diff-Sync
// =========================================================================
async function loadAdminConfig() {
  try {
    const res = await fetch("/api/v1/admin/config");
    if (!res.ok) return;
    const c = await res.json();
    document.getElementById("adm-max-depts").value = c.max_departments_per_request;
    document.getElementById("adm-max-unis").value = c.max_universities_per_job;
    document.getElementById("adm-max-profs").value = c.max_professors_per_uni;
    document.getElementById("adm-max-concurrent").value = c.max_concurrent_universities ?? 4;
    document.getElementById("adm-countries").value = (c.allowed_countries || []).join(", ");
    const map = [
      ["adm-enable-serper", c.enable_serper],
      ["adm-enable-playwright", c.enable_playwright],
      ["adm-enable-agent", c.enable_agent_fallback],
      ["adm-enable-colab", c.enable_colab_bridge],
      ["adm-enable-llm", c.enable_llm_extraction]
    ];
    map.forEach(([id, val]) => {
      const cb = document.getElementById(id);
      if (cb) {
        cb.checked = Boolean(val);
        syncTogglePill(cb);
      }
    });
  } catch (e) {
    console.error("Admin config load error:", e);
  }
}

async function saveAdminConfig(btn) {
  btn.disabled = true;
  try {
    const payload = {
      max_departments_per_request: parseInt(document.getElementById("adm-max-depts").value, 10),
      max_universities_per_job: parseInt(document.getElementById("adm-max-unis").value, 10),
      max_professors_per_uni: parseInt(document.getElementById("adm-max-profs").value, 10),
      max_concurrent_universities: parseInt(document.getElementById("adm-max-concurrent")?.value || "4", 10),
      allowed_countries: document.getElementById("adm-countries").value.split(",").map(s => s.trim()).filter(Boolean),
      enable_serper: document.getElementById("adm-enable-serper").checked,
      enable_playwright: document.getElementById("adm-enable-playwright").checked,
      enable_agent_fallback: document.getElementById("adm-enable-agent").checked,
      enable_colab_bridge: document.getElementById("adm-enable-colab").checked,
      enable_llm_extraction: document.getElementById("adm-enable-llm").checked
    };
    const res = await fetch("/api/v1/admin/config", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (res.ok) showToast("✓ Admin config saved!");
    else showToast("Save failed: " + (await res.text()));
  } finally {
    btn.disabled = false;
  }
}

async function triggerAdminDiffSync(btn) {
  const domains = document.getElementById("sync-domains").value.split(",").map(s => s.trim()).filter(Boolean);
  if (!domains.length) {
    showToast("Enter at least one domain to diff-sync.");
    return;
  }
  const out = document.getElementById("sync-result-output");
  btn.disabled = true;
  out.textContent = "Running 3-Step Smart Diff-Sync...";
  try {
    const res = await fetch("/api/v1/admin/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        domains,
        department: document.getElementById("sync-dept").value.trim() || "Computer Science",
        degree: document.getElementById("sync-degree").value || "masters"
      })
    });
    const d = await res.json();
    out.textContent = JSON.stringify(d, null, 2);
    await Promise.all([loadSystemSummary(), loadProfessors()]);
    showToast(`Diff-sync finished for ${domains.length} domain(s)`);
  } catch (e) {
    out.textContent = `Error: ${e.message}`;
  } finally {
    btn.disabled = false;
  }
}

async function refreshAllData() {
  await Promise.all([
    loadSystemSummary(),
    loadUniversitiesOverview(),
    loadProfessors(),
    loadNeedsReview(),
    loadAnalytics(),
    loadAdminConfig()
  ]);
}

document.addEventListener("DOMContentLoaded", () => {
  refreshAllData();
});
