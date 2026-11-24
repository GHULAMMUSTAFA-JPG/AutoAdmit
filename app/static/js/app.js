/* AutoAdmit P12 Frontend Controller — Wired to app/main.py */

const state = {
  universities: [],
  activeJobId: null,
  pollTimer: null,
  logOffset: 0,
  logTotal: 0,
  logEntries: []
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

// =========================================================================
// System Summary & Universities Overview
// =========================================================================
async function loadSystemSummary() {
  try {
    const res = await fetch("/api/v1/system/summary");
    if (!res.ok) return;
    const d = await res.json();
    document.getElementById("kpi-universities").textContent = d.universities ?? 0;
    document.getElementById("kpi-depts").textContent = d.university_departments ?? 0;
    document.getElementById("kpi-snapshots").textContent = d.page_snapshots ?? 0;
    document.getElementById("kpi-professors").textContent = d.professors ?? 0;
    document.getElementById("kpi-review").textContent = d.needs_review ?? 0;
    document.getElementById("hdr-summary-text").textContent =
      `${d.universities ?? 0} Unis · ${d.professors ?? 0} Profs · ${d.needs_review ?? 0} Review`;
  } catch (e) {
    console.error("Summary load error:", e);
  }
}

async function loadUniversitiesOverview() {
  try {
    const res = await fetch("/api/v1/universities");
    if (!res.ok) return;
    state.universities = await res.json();
    renderUniversitiesTable();
  } catch (e) {
    console.error("Universities load error:", e);
  }
}

function renderUniversitiesTable() {
  const q = (document.getElementById("uni-search")?.value || "").trim().toLowerCase();
  const rows = state.universities.filter(u => {
    if (!q) return true;
    return `${u.name || ""} ${u.chinese_name || ""} ${u.domain || ""} ${u.region || ""}`.toLowerCase().includes(q);
  });

  document.getElementById("uni-row-count").textContent = rows.length;
  const tbody = document.getElementById("uni-table-body");
  if (!tbody) return;
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:var(--text-muted); padding:20px;">No universities match filter.</td></tr>`;
    return;
  }

  tbody.innerHTML = rows.map(u => {
    const st = u.status || "PENDING";
    const stCls = st === "COMPLETE" ? "p12-badge-ok" : st === "RUNNING" ? "p12-badge-info" : st === "NEEDS_REVIEW" ? "p12-badge-warn" : "p12-badge-muted";
    const rosterHtml = u.faculty_roster_url
      ? `<a href="${esc(u.faculty_roster_url)}" target="_blank" rel="noopener" style="color:var(--primary); word-break:break-all;">${esc(u.faculty_roster_url)}</a>`
      : `<span style="color:var(--text-muted);">—</span>`;
    const errHtml = u.error_code ? `<div style="margin-top:4px;"><span class="p12-badge p12-badge-err">${esc(u.error_code)}</span></div>` : "";
    return `
      <tr>
        <td><strong>#${esc(u.rank ?? "-")}</strong></td>
        <td>
          <strong>${esc(u.name || u.domain)}</strong> ${u.chinese_name ? `<span style="color:var(--text-secondary);">(${esc(u.chinese_name)})</span>` : ""}
          <div style="font-size:11.5px; color:var(--text-muted);">${esc(u.region || "China")} &middot; <code>${esc(u.domain)}</code></div>
        </td>
        <td><span class="p12-badge p12-badge-info">${esc(u.winning_strategy || "PENDING")}</span></td>
        <td>${rosterHtml}</td>
        <td><strong>${esc(u.professors_found ?? 0)}</strong> found / <strong style="color:var(--accent-green);">${esc(u.professors_verified ?? 0)}</strong> verified</td>
        <td>
          <span class="p12-badge ${stCls}">${esc(st)}</span>
          ${errHtml}
        </td>
        <td>
          <button class="btn btn-secondary btn-sm" onclick="viewSiteTree('${esc(u.domain)}')">🌳 View Tree</button>
        </td>
      </tr>
    `;
  }).join("");
}

async function buildTreesOnly(btn) {
  const country = (document.getElementById("f-country")?.value || "China").trim();
  const regionsRaw = (document.getElementById("f-regions")?.value || "").trim();
  const regions = regionsRaw ? regionsRaw.split(",").map(s => s.trim()).filter(Boolean) : [];
  const deptsRaw = (document.getElementById("f-departments")?.value || "Computer Science").trim();
  const department = deptsRaw.split(",")[0].trim() || "Computer Science";
  const degree = document.getElementById("f-degree")?.value || "masters";
  const tier = document.getElementById("f-tier")?.value || "top_10";

  const statusMsg = document.getElementById("job-status-msg");
  btn.disabled = true;
  if (statusMsg) statusMsg.textContent = "Starting Tree-Only build & verification job...";
  try {
    const res = await fetch("/api/v1/trees/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ country, regions, department, degree, tier })
    });
    const body = await res.json();
    if (!res.ok) {
      if (statusMsg) statusMsg.textContent = `Error: ${body.detail || JSON.stringify(body)}`;
      return;
    }
    if (body.university_details && Object.keys(body.university_details).length) {
      state.universities = Object.values(body.university_details).sort((a, b) => (a.rank || 999) - (b.rank || 999));
      renderUniversitiesTable();
    }
    state.activeJobId = body.job_id;
    document.getElementById("log-job-id").value = body.job_id;
    document.getElementById("log-file-label").textContent = `logs/jobs/${body.job_id}.jsonl`;
    state.logOffset = 0;
    state.logEntries = [];
    document.getElementById("log-viewer-box").innerHTML = "";
    document.getElementById("active-job-banner").classList.remove("hidden");
    if (statusMsg) statusMsg.textContent = `Tree-only job ${body.job_id} queued (${body.target_domains.length} universities).`;
    showToast(`Started tree-only job ${body.job_id}`);
    startJobPolling(body.job_id);
  } catch (e) {
    if (statusMsg) statusMsg.textContent = `Error: ${e.message}`;
  } finally {
    btn.disabled = false;
  }
}

async function viewSiteTree(domain) {
  const panel = document.getElementById("site-tree-panel");
  const title = document.getElementById("site-tree-title");
  const mdEl = document.getElementById("site-tree-md");
  const deptEl = document.getElementById("site-tree-depts");
  if (!panel) return;
  panel.classList.remove("hidden");
  title.textContent = `Site Tree — ${domain}`;
  mdEl.textContent = "Loading...";
  deptEl.textContent = "Loading...";
  try {
    const res = await fetch(`/api/v1/trees/${encodeURIComponent(domain)}`);
    if (!res.ok) {
      mdEl.textContent = `No saved site tree yet for ${domain}. Click "Build & Verify Trees Only" first.`;
      deptEl.textContent = "{}";
      return;
    }
    const d = await res.json();
    mdEl.textContent = d.markdown_tree || "(empty tree)";
    deptEl.textContent = JSON.stringify({
      verified_rosters: d.verified_rosters || {},
      departments_map: d.departments_map || {}
    }, null, 2);
  } catch (e) {
    mdEl.textContent = `Error: ${e.message}`;
  }
}

// =========================================================================
// Section 01: Start Discovery Job & Live Polling
// =========================================================================
async function startDiscoveryJob(btn) {
  const country = (document.getElementById("f-country")?.value || "China").trim();
  const regionsRaw = (document.getElementById("f-regions")?.value || "").trim();
  const regions = regionsRaw ? regionsRaw.split(",").map(s => s.trim()).filter(Boolean) : [];
  const deptsRaw = (document.getElementById("f-departments")?.value || "Computer Science").trim();
  const departments = deptsRaw.split(",").map(s => s.trim()).filter(Boolean);
  const degree = document.getElementById("f-degree")?.value || "masters";
  const tier = document.getElementById("f-tier")?.value || "top_10";

  const statusMsg = document.getElementById("job-status-msg");
  btn.disabled = true;
  if (statusMsg) statusMsg.textContent = "Starting discovery job...";

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

    if (body.university_details && Object.keys(body.university_details).length) {
      state.universities = Object.values(body.university_details).sort((a, b) => (a.rank || 999) - (b.rank || 999));
      renderUniversitiesTable();
    }

    if (body.source === "database") {
      if (statusMsg) statusMsg.textContent = `Instant DB hit ($0): ${body.count} professors returned from MongoDB.`;
      showToast(`Served ${body.count} professors directly from MongoDB ($0)`);
      await loadProfessors();
      await loadSystemSummary();
      return;
    }

    state.activeJobId = body.job_id;
    document.getElementById("log-job-id").value = body.job_id;
    document.getElementById("log-file-label").textContent = `logs/jobs/${body.job_id}.jsonl`;
    state.logOffset = 0;
    state.logEntries = [];
    document.getElementById("log-viewer-box").innerHTML = "";
    document.getElementById("active-job-banner").classList.remove("hidden");
    if (statusMsg) statusMsg.textContent = `Job ${body.job_id} queued (${body.target_domains.length} universities).`;
    showToast(`Started job ${body.job_id}`);
    startJobPolling(body.job_id);
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
      document.getElementById("banner-job-title").textContent =
        `Job ${job.job_id} — ${job.status} (${completed}/${total} universities completed)`;
      document.getElementById("banner-job-scorecard").textContent =
        `Verified Profs: ${sc.total_verified_professors ?? 0} · Grounding Pass: ${sc.grounding_pass_pct ?? 100}% · Failures: ${sc.failures ?? 0} · Strategies: ${JSON.stringify(sc.winning_strategies || {})}`;

      if (job.university_details && Object.keys(job.university_details).length) {
        state.universities = Object.values(job.university_details).sort((a, b) => (a.rank || 999) - (b.rank || 999));
        renderUniversitiesTable();
      }

      await fetchIncrementalJobLogs(jobId);

      if (job.status === "COMPLETED" || job.status === "FAILED") {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
        await Promise.all([loadSystemSummary(), loadProfessors(), loadNeedsReview()]);
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
// Section 03 & 04: Professors & Needs Review
// =========================================================================
async function loadProfessors() {
  const search = (document.getElementById("prof-search")?.value || "").trim();
  const emailSt = document.getElementById("prof-email-filter")?.value || "";
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (emailSt) params.set("email_status", emailSt);

  try {
    const res = await fetch(`/api/v1/professors?${params.toString()}`);
    if (!res.ok) return;
    const profs = await res.json();
    document.getElementById("prof-row-count").textContent = profs.length;
    const tbody = document.getElementById("prof-table-body");
    if (!profs.length) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:var(--text-muted); padding:20px;">No verified professors match filters.</td></tr>`;
      return;
    }
    tbody.innerHTML = profs.map(p => {
      const emailCls = p.email_status === "FOUND" ? "p12-badge-ok" : "p12-badge-warn";
      const degs = (p.degree_eligibility || []).map(d => `<span class="p12-badge p12-badge-info">${esc(d)}</span>`).join(" ");
      const topics = (p.research_interests || []).slice(0, 5).map(t => `<span class="p12-badge p12-badge-muted" style="margin:1px;">${esc(t)}</span>`).join(" ");
      return `
        <tr>
          <td>
            <strong>${esc(p.name)}</strong>
            <div style="font-size:11.5px; color:var(--text-muted);">${esc(p.title || "")}</div>
            <a href="${esc(p.canonical_profile_url)}" target="_blank" rel="noopener" style="font-size:11px; color:var(--primary);">Profile &nearr;</a>
          </td>
          <td><code>${esc(p.university_domain)}</code><div style="font-size:11.5px; color:var(--text-secondary);">${esc(p.department)}</div></td>
          <td>${degs || "—"}</td>
          <td>${topics || "—"}</td>
          <td>
            <div><code>${esc(p.email || "—")}</code></div>
            <span class="p12-badge ${emailCls}" style="margin-top:3px;">${esc(p.email_status)}</span>
            ${p.status === "POSSIBLY_INACTIVE" ? `<span class="p12-badge p12-badge-err">POSSIBLY_INACTIVE</span>` : ""}
          </td>
          <td style="font-size:12px; color:var(--text-secondary); max-width:260px;">${esc(p.supervisor_evidence_quote || p.name_evidence_quote || "—")}</td>
        </tr>
      `;
    }).join("");
  } catch (e) {
    console.error("Professors load error:", e);
  }
}

async function loadNeedsReview() {
  try {
    const res = await fetch("/api/v1/needs-review");
    if (!res.ok) return;
    const items = await res.json();
    document.getElementById("review-row-count").textContent = items.length;
    const tbody = document.getElementById("review-table-body");
    if (!items.length) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--text-muted); padding:18px;">No items in needs_review.</td></tr>`;
      return;
    }
    tbody.innerHTML = items.map(it => `
      <tr>
        <td><code>${esc(it.domain)}</code></td>
        <td><span class="p12-badge p12-badge-muted">${esc(it.stage)}</span></td>
        <td><span class="p12-badge p12-badge-err">${esc(it.error_code)}</span></td>
        <td style="font-size:12px;">${esc(it.detail)}</td>
        <td>${it.url ? `<a href="${esc(it.url)}" target="_blank" rel="noopener" style="color:var(--primary); font-size:12px;">${esc(it.url)}</a>` : "—"}</td>
      </tr>
    `).join("");
  } catch (e) {
    console.error("Needs review load error:", e);
  }
}

// =========================================================================
// Section 05: Complete Un-Truncated Incremental Run Logs Viewer
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
  // Loop until all pages loaded so zero lines are truncated
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
// Section 06: Admin Config & 3-Step Diff-Sync
// =========================================================================
async function loadAdminConfig() {
  try {
    const res = await fetch("/api/v1/admin/config");
    if (!res.ok) return;
    const c = await res.json();
    document.getElementById("adm-max-depts").value = c.max_departments_per_request;
    document.getElementById("adm-max-unis").value = c.max_universities_per_job;
    document.getElementById("adm-max-profs").value = c.max_professors_per_uni;
    if (document.getElementById("adm-max-concurrent")) {
      document.getElementById("adm-max-concurrent").value = c.max_concurrent_universities ?? 2;
    }
    document.getElementById("adm-countries").value = (c.allowed_countries || []).join(", ");
    document.getElementById("adm-enable-serper").checked = Boolean(c.enable_serper);
    document.getElementById("adm-enable-playwright").checked = Boolean(c.enable_playwright);
    document.getElementById("adm-enable-agent").checked = Boolean(c.enable_agent_fallback);
    document.getElementById("adm-enable-colab").checked = Boolean(c.enable_colab_bridge);
    document.getElementById("adm-enable-llm").checked = Boolean(c.enable_llm_extraction);
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
      max_concurrent_universities: parseInt(document.getElementById("adm-max-concurrent")?.value || "2", 10),
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
    if (res.ok) showToast("Admin config saved!");
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
    loadAdminConfig()
  ]);
}

document.addEventListener("DOMContentLoaded", () => {
  refreshAllData();
});
