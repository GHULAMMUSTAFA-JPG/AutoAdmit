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

// Section 1: Render Matched Endpoints with custom scroll & row numbers
function renderMatchedEndpoints(universities) {
  const countEl = document.getElementById("matched-univ-count");
  if (countEl) countEl.textContent = universities.length;

  const tbody = document.getElementById("matched-endpoints-tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  if (!universities || universities.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" class="empty-state-cell">
          <div class="empty-state">
            <span class="empty-icon">🌐</span>
            <h4>No Universities Discovered Yet</h4>
            <p>Select your region filters and click 'Execute Live Discovery' to query institutions.</p>
          </div>
        </td>
      </tr>
    `;
    const container = document.getElementById("discovered-endpoints-container");
    if (container) container.classList.add("hidden");
    return;
  }

  universities.forEach((u, idx) => {
    const tr = document.createElement("tr");
    const endpointsHtml = (u.department_endpoints || []).map(ep => 
      `<div style="margin-bottom: 3px;"><span class="badge version">${ep.name}</span> <code style="font-size: 0.75rem; color: var(--primary);">${ep.url}</code></div>`
    ).join("");

    tr.innerHTML = `
      <td class="col-num">${idx + 1}</td>
      <td><strong>${u.name}</strong></td>
      <td><span style="color: var(--text-secondary);">${u.chinese_name || "-"}</span></td>
      <td><span class="badge ${u.region === 'Beijing' || u.region === 'Shanghai' ? 'status-staged' : 'status-sent'}">${u.region}</span></td>
      <td><span class="badge ${u.tier && u.tier.includes('Dream') ? 'warning' : 'version'}">${u.tier || "Target"}</span></td>
      <td>${endpointsHtml}</td>
    `;
    tbody.appendChild(tr);
  });

  const container = document.getElementById("discovered-endpoints-container");
  if (container) container.classList.remove("hidden");
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

async function runRegionalFilter() {
  const btn = document.getElementById("btn-run-discovery");
  const spinner = document.getElementById("btn-discovery-spinner");
  const textEl = document.getElementById("btn-discovery-text");

  // Visual active button feedback
  if (btn) {
    btn.disabled = true;
    btn.classList.add("btn-loading");
  }
  if (spinner) spinner.classList.remove("hidden");
  if (textEl) textEl.textContent = "Querying Live Registries & Resolving...";

  startProgressAnimation("STAGE 1: LIVE QUERY", `Connecting to ${activeDiscoverySource.toUpperCase()} endpoint...`);

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

  try {
    updateProgressStage(45, "STAGE 2: FILTER & DEDUP", "Filtering accredited .edu.cn domains and deduplicating...", "Processing regional institutions");

    const res = await fetchWithAuth("/api/v1/discovery/filter", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    
    updateProgressStage(80, "STAGE 3: RESOLVING PORTALS", "Synthesizing CS/AI faculty directory endpoints...", "Validating department URLs");

    const universities = await res.json();
    lastDiscoveredUniversities = universities;

    stopProgressAnimation(true, `Successfully resolved ${universities.length} accredited Chinese university portals.`);
    renderMatchedEndpoints(universities);
  } catch (err) {
    stopProgressAnimation(false, "Discovery encountered an error: " + err);
    alert("Error discovering universities: " + err);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.classList.remove("btn-loading");
    }
    if (spinner) spinner.classList.add("hidden");
    if (textEl) textEl.textContent = "🔍 Execute Live Discovery & Resolve Endpoints";
  }
}

function clearDiscoveredUniversities() {
  lastDiscoveredUniversities = [];
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

// Section 2: Universities Directory
async function loadUniversities() {
  try {
    const res = await fetchWithAuth("/api/v1/discovery/universities");
    const universities = await res.json();
    const tbody = document.getElementById("universities-tbody");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (!universities || universities.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="9" class="empty-state-cell">
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

    universities.forEach((u, idx) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="col-num">${idx + 1}</td>
        <td><strong>${u.name}</strong></td>
        <td>${u.chinese_name || "-"}</td>
        <td><code>${u.domain}</code></td>
        <td>${u.cs_ranking ? "#" + u.cs_ranking : "Top 50"}</td>
        <td><span class="badge ${u.tier && u.tier.includes('Dream') ? 'warning' : 'version'}">${u.tier}</span></td>
        <td>${(u.scholarships_available || []).join(", ") || "CSC Type B"}</td>
        <td>${u.application_fee_rmb === 0 ? '<span class="badge window-open">0 RMB (Free)</span>' : u.application_fee_rmb + ' RMB'}</td>
        <td style="max-width: 250px; font-size: 0.8rem;">${u.feasibility_notes || "Accredited institution"}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error("Error loading universities:", err);
  }
}

// Section 3: Faculty Roster
async function loadFaculty() {
  try {
    const res = await fetchWithAuth("/api/v1/professors");
    const faculty = await res.json();
    const tbody = document.getElementById("faculty-tbody");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (!faculty || faculty.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="9" class="empty-state-cell">
            <div class="empty-state">
              <span class="empty-icon">👨‍🏫</span>
              <h4>No Faculty Records Harvested</h4>
              <p>Approve the Pre-Run Cost Gate to launch parallel supervisor crawlers.</p>
            </div>
          </td>
        </tr>
      `;
      return;
    }

    faculty.forEach((f, idx) => {
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
  } catch (err) {
    console.error("Error loading faculty:", err);
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
  if (!authHeader) {
    showAuthOverlay();
  } else {
    syncCSTClock();
    loadAllData();
    initScrollSpy();
    initWebSocket();
  }
});
