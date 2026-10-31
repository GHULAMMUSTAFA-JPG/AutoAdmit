---
id: 033
title: "Git Commit, Red Error Tooltips, Unlimited Batch Dept Resolution, Vertical Scroller & Persistent Raw vs. Normalized DB Pipeline"
stage: refactor
date: "2026-10-31"
surface: agent
model: "claude-opus-4-6"
feature: "001-autoadmit-engine"
branch: "001-autoadmit-engine"
user: "operator"
command: "refactor"
labels: ["phase-1", "git-commit", "error-tooltips", "vertical-scroller", "raw-vs-normalized", "mongodb-persistence"]
links:
  spec: "specs/001-autoadmit-engine/spec.md"
  ticket: null
  adr: null
  pr: null
files:
  - src/models/university.py
  - src/services/discovery.py
  - src/api/routes_discovery.py
  - src/static/index.html
  - src/static/css/style.css
  - src/static/js/app.js
tests: []
---

## Prompt

so now its some what working and also when i clicked 🧭 Resolve Real Dept Links it started doing but did for the first 15 and 1 was skipped and i saw something ok so what is not found turn it to red or any other error and also give a tip on that with reason when hover ovr and also those found still shows action to be 🧭 Verify & Find Dept and all remaining are left why it stopped at 15 and also its drag and drop for view but no vertical scroller so add it, so why it stopped there and also we will save in db everything like uni home page link with other so ,  there is a issue when i search it shows me progress but it dont show me which search is happening and then it dont show me separate results 1 raw with all data from all sources and then after we normalizes it and the search goes the moment we refresh so do it like persistant and we can open and close the thing like to see and on every search we are doing live work save in db and then picking from db and then showing back to UI from DB and so give me report and if there are task to work on make a list and start with small and easy and before all that do the commit 

## Response

1. **Git Commit Executed (`9ebde46`):**
   - Committed the working Phase 1 enhancements (`feat(phase1): add Playwright WAF fallback, authentic live status, 10-row resizable tables, and Section 03 worker pool`) before starting the new set of tasks.
2. **Red Error Status Badges + Hover Reason Tooltip (`status_reason`):**
   - Added `status_reason` to `University` (`src/models/university.py`) and updated `resolve_department_from_homepage()` (`src/services/discovery.py`) so that when a homepage is reachable (`200 OK`) but no CS/AI department link is found, it marks `pipeline_status = "Department URL Not Found"` (Red badge) instead of leaving it green, and saves the exact diagnostic reason (`status_reason`) to MongoDB.
   - Styled `.badge-status-missing` and `.badge-status-manual` in Red (`#fee2e2` / `#b91c1c`) with hover tooltip `title="❌ NOT FOUND REASON: ..."`.
3. **Removed 15-University Cap, Smart Action Button & Stop Toggle:**
   - Removed `.slice(0, 15)` in `resolveRealDepartmentsForVisible()` (`src/static/js/app.js`), added automatic skipping of already-verified rows (`Faculty Page Found` / `Department URL Found`), added a `⏹ Stop (X/Y Probed)` toggle button, and updated row Action buttons to show `✓ Verified (↻)` (green) when found or `↻ Retry Probe` (red) when not found.
4. **Explicit Vertical Scrollbar Inside 10-Row Drag-Resizable Tables:**
   - Kept the default viewport height at 10 visible rows (`420px`) with `overflow-y: scroll !important` while rendering all matching rows inside the scroll box so the user can both scroll vertically through all records and drag the bottom resize handle (`⇕`) to adjust viewport height.
5. **Active Source Progress + Collapsible Raw Multi-Source vs. Normalized Inspector + Full MongoDB Persistence Across Refresh (`F5`):**
   - Added `discovery_runs` persistence in `POST /api/v1/discovery/filter` and `GET /api/v1/discovery/last-audit` (`src/api/routes_discovery.py`), added the collapsible `📂 Raw Multi-Source vs. Normalized DB Inspector` (`#discovery-audit-box`) in `src/static/index.html`, and updated `loadUniversities()` so refreshing (`F5`) automatically restores Section 01 (`Discovered University Portals`) and the Raw/Normalized Audit directly from MongoDB.

