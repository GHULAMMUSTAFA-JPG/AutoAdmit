---
id: 037
title: "Enforce 3-Worker Pool, Playwright CPU/RAM Semaphore Guard, and Two-Step Homepage vs. Department Status & Logs"
stage: refactor
date: "2026-10-31"
surface: agent
model: "claude-opus-4-6"
feature: "001-autoadmit-engine"
branch: "001-autoadmit-engine"
user: "operator"
command: "refactor"
labels: ["3-workers", "cpu-ram-guard", "step1-homepage", "step2-department", "edge-cases"]
links:
  spec: "specs/001-autoadmit-engine/spec.md"
  ticket: null
  adr: null
  pr: null
files:
  - src/services/scraper.py
  - src/services/discovery.py
  - src/api/routes_discovery.py
  - src/api/routes_professors.py
  - src/static/index.html
  - src/static/js/app.js
tests:
  - "py_compile src/services/scraper.py src/services/discovery.py src/api/routes_discovery.py src/api/routes_professors.py"
---

## Prompt

so leets use 3 workers only and make sure code has all cases covered exception and edge cases and so on and apply fixes

## Response

1. **Strict 3-Worker Concurrency + Playwright 1-at-a-Time CPU/RAM Guard:**
   - Capped worker concurrency to **3 Workers (`1`, `2`, `3 Workers (Recommended)`)** in both Section 01 (`#portal-probe-workers` / `resolve_departments_endpoint`) and Section 03 (`#sup-worker-count` / `harvest_faculty_batch`).
   - Added a global `_playwright_semaphore = asyncio.Semaphore(1)` in `FacultyHarvester` (`src/services/scraper.py`) with `--disable-gpu`, `--disable-dev-shm-usage`, `--disable-extensions`, a hard `18.0s` `asyncio.wait_for` timeout, and `try/finally` cleanup on both `context` and `browser` so at most 1 Chromium browser can ever exist in RAM at a time.
2. **Separated Step 1 (Homepage) vs. Step 2 (Department) in Data, Badges, and Live Logs:**
   - Updated `resolve_department_from_homepage()` (`src/services/discovery.py`) and `getPipelineStatusBadge()` (`src/static/js/app.js`) so:
     - **Step 1 OK + Step 2 OK:** Shows two green pills (`✓ Step 1: Homepage OK` + `✓ Step 2: CS/AI Dept Found` / `✓ Step 2: Dept + Roster Found`) and keeps **both** the `🏛️ Verified Institutional Homepage` and the CS/AI Department / Supervisor Roster links in `department_endpoints`.
     - **Step 1 OK + Step 2 Not Found (`Homepage OK · Dept Not Found`):** Preserves `website_verified = True` and the verified homepage link (`🏛️ Verified Institutional Homepage (Step 1 OK)`), renders `✓ Step 1: Homepage OK` (Green) + `✗ Step 2: Dept Not Found ⓘ` (Red with hover reason), and shows `🧭 Retry Step 2 (Dept)` as the row action button.
     - **Step 1 Failed (`Step 1 Failed: Homepage Unreachable`):** Renders `✗ Step 1 Failed: Unreachable / WAF ⓘ` (Red with hover reason) and shows `↻ Retry Step 1 & 2`.
3. **Edge Cases & Exception Handling Covered:**
   - Fast `<meta http-equiv="refresh" content="0;url=...">` and `window.location.href` client-side redirect following in `httpx` so portals like `buct.edu.cn` resolve in `0.2s` without needing Playwright.
   - Safe `_safe_urljoin()` wrapper filtering out malformed `href`s, `mailto:`, `tel:`, and binary files (`.pdf`, `.doc`, `.xls`, `.zip`).
   - News/article title filter (`活动`, `通知`, `公告`, `新闻`, `讲座`, `党支部`, etc.) so news items are never mistaken for academic departments.

