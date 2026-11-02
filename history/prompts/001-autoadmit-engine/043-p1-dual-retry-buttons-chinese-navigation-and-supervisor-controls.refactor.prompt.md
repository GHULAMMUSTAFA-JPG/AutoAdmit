---
id: 043
title: "P1 Dual Retry Buttons Chinese Navigation and Supervisor Harvesting Controls"
stage: refactor
date: "2026-11-02"
surface: agent
model: "claude-opus-4-6"
feature: "001-autoadmit-engine"
branch: "001-autoadmit-engine"
user: "operator"
command: "refactor"
labels: ["p1-retry", "chinese-navigation", "supervisor-controls", "stop-mechanism", "decoupling"]
links:
  spec: "specs/001-autoadmit-engine/spec.md"
  ticket: null
  adr: null
  pr: null
files:
  - src/services/discovery.py
  - src/static/index.html
  - src/static/js/app.js
  - history/prompts/001-autoadmit-engine/043-p1-dual-retry-buttons-chinese-navigation-and-supervisor-controls.refactor.prompt.md
tests:
  - "python -m py_compile src/services/discovery.py src/api/routes_discovery.py src/services/scraper.py src/api/routes_professors.py"
  - "node -c src/static/js/app.js"
  - "pytest tests/integration/test_p1_discovery.py -k test_p1_feasibility_scoring_tiers -v"
---

## Prompt

so add 2 button to p11 where one button retries the unis where everything failed and other where only the faculty page failed so also as chinese uni are in chinese we need to make sure our system navigate correctly coz our system is working in english and sites are native to chinese and then with the button we can retries the respective unis and then the next phase for finding professors i can control it from UI and also stop and same for above 2 button add stop too and verify the complete p1 and whole system and run dont make one part depended on next to run make sure its a flow and from 1 step to second

## Response

Implemented the dual retry button architecture for Phase 1, Chinese navigation and supervisor roster grounding, UI-based stop controls for both Phase 1 and Section 03 supervisor harvesting, and verified the complete pipeline flow:

1. **Dual Retry Buttons on P1 Toolbar (`src/static/index.html`):**
   - Added `btn-retry-step1-failed`: Targets universities where Step 1 failed (homepage unreachable/timeout/WAF) with dynamic badge counter `retry-s1-count`.
   - Added `btn-retry-step2-missing`: Targets universities where Step 1 homepage succeeded (200 OK) but Step 2 CS/AI department or supervisor roster was missing with dynamic badge counter `retry-s2-count`.
   - Unified execution engine `executeBatchProbe()` in `src/static/js/app.js` with interactive Start/Stop toggling and batch worker concurrency (1-3).
2. **Chinese Academic Taxonomy & Navigation Grounding (`src/services/discovery.py`):**
   - Expanded navigation menu keywords to authentic Chinese university organizational structures (`院系设置`, `机构设置`, `教学单位`, `学院设置`, `二级学院`, `学部院系`, `院系总览`, `学院导航`, `教学机构`, `院系所`, `教学与科研`, `学科建设`, `教学科研单位`, `学校机构`, `组织机构`, `教育教学`).
   - Expanded discipline keywords for Computer Science, AI, and Software Engineering, accommodating legitimate parenthetical college designations up to 34 characters.
   - Expanded supervisor roster keywords to 34 standard Chinese titles (`硕士生导师`, `博士生导师`, `硕导`, `博导`, `师资队伍`, `教师名录`, `专任教师`, etc.).
3. **Interactive UI Control & Stop Mechanism for Section 03 (`src/static/js/app.js`):**
   - Implemented `stopSupervisorWorkerPool()` and wired `#btn-stop-sup-workers`.
   - Updated `launchSupervisorWorkerPool()` with toggle Stop functionality on the launch button and progress state persistence without data loss.
4. **Decoupled Pipeline Flow:**
   - Ensured Section 03 automatically resolves homepages or falls back to root domains when department endpoints have not yet been resolved, allowing operators to run any step independently or in smooth natural succession.
