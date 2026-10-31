---
id: 038
title: "Audit Live 3-Worker Execution Logs (20:13 to 20:54) and Identify Playwright Timeout Bottleneck"
stage: explainer
date: "2026-10-31"
surface: agent
model: "claude-opus-4-6"
feature: "001-autoadmit-engine"
branch: "001-autoadmit-engine"
user: "operator"
command: "explainer"
labels: ["log-audit", "3-workers", "telemetry", "bottleneck-analysis"]
links:
  spec: "specs/001-autoadmit-engine/spec.md"
  ticket: null
  adr: null
  pr: null
files: []
tests: []
---

## Prompt

i want you to look at my logs and see how the 3 workers are doing and dont take alot of times and also look from the time i started this action ok or put an agent to this task ok

## Response

Audited `data/logs/autoadmit.log` from the moment the 3-worker run started (`20:13:27` to `20:54:53`, 41 minutes elapsed, 596 log lines):
1. **3-Worker Health & Stability:**
   - Process `[13672]` ran continuously for 41 minutes with **0 crashes** and **0 `NotImplementedError` exceptions**.
   - Dispatched clean parallel batches of 3 universities at a time.
2. **Exact Yield Across 126 Universities Probed So Far:**
   - **Total Probed:** `126` universities
   - **Step 1 Homepage Verified (`✓`):** `81` universities (`64.3%` reachable)
   - **Step 2 CS/AI Departments Found (`✓`):** `63` CS/AI school links across `47` universities
   - **Step 2 Direct Supervisor Rosters Verified (`师资队伍` / `硕士生导师`):** `33` direct roster URLs
   - **Step 1 OK (`✓`) + Step 2 Dept Missing (`⚠`):** `34` universities (mostly Medical, Music, Sport, Finance, TCM universities with no CS school, plus JS-menu sites)
   - **Step 1 Failed (`✗` Unreachable/Geo-blocked):** `45` universities
3. **Key Bottleneck & Edge Cases Spotted in the Logs:**
   - **Playwright Triggered 69 Times, Succeeded Only Once (`68` timeouts × 15s = ~17 minutes wasted):** Whenever `http://` timed out in `httpx`, Playwright launched and waited 12–15s before `https://` succeeded immediately in `httpx`.
   - **WebVPN / Login Redirects on Subdomains (3 cases):** `clientvpn.cqwu.edu.cn/.../login`, `ai.gxust.edu.cn/rump_frontend/login`, and `inner.btbu.edu.cn` redirected subdomain probes to campus VPN login pages (`统一身份认证`).

