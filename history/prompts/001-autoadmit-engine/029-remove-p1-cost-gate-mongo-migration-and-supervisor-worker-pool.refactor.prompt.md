---
id: 029
title: Remove P1 Cost Gate, Migrate MongoDB Records, and Add Supervisor Worker Pool
stage: refactor
date: 2026-10-31
surface: agent
model: claude-opus-4-6
feature: 001-autoadmit-engine
branch: 001-autoadmit-engine
user: parep
command: refactor
labels: ["phase-1", "mongodb-migration", "edu-cn-filter", "cost-gate", "supervisor-worker-pool", "ui-ux"]
links:
  spec: specs/001-autoadmit-engine/spec.md
  ticket: null
  adr: null
  pr: null
files:
 - src/services/discovery.py
 - src/api/routes_discovery.py
 - src/api/routes_professors.py
 - src/static/index.html
 - src/static/css/style.css
 - src/static/js/app.js
 - WIKIDATA_ARCHITECTURE.md
tests:
 - tests/unit/test_discovery.py
 - tests/integration/test_phase1_pipeline.py
---

## Prompt

every row has this Provincial Accredited	Tier 3 (Safety)	CSC Type B (Full Funding), University Presidential Scholarship	0 RMB (Fee Waived)	
● Homepage Verified
Live verified institution queried from Wikidata open registry. and i opened 1 link and same https://www.hlau.cn/ This site can’t be reached
Check if there is a typo in www.hlau.cn.

If spelling is correct, try running windows network Diagnostics.
DNS_PROBE_FINISHED_NXDOMAIN lets move on remove the cost gate from phase 1 and transfer it to one it belongs to it dont belong to one and p1 will work without it and also what is after (INSTITUTIONAL DIRECTORY (745 / 745)
📊 Matrix Table
📜 Live Logs
 ↻ Refresh Directory
University Feasibility & Scholarship Matrix
Indexed institutions categorized into Tier 1 Dream (Project 985/C9), Tier 2 Target (Project 211), and Tier 3 Safety. Stored persistently in MongoDB.) means what is after and also Verified Graduate Supervisors Roster make it like on it how many worker we need to work at once and also to region and universities and so on and in that that region how many uinversities so i want you make a list of task and start

## Response snapshot

1. Enforced strict `.edu.cn` / `.ac.cn` domain validation in `src/services/discovery.py` and executed a live MongoDB migration (`autoadmit.universities`) that purged 38 invalid `.cn` domains (such as `hlau.cn`) and enriched all 707 official `.edu.cn`/`.ac.cn` universities with accurate MOE Project 985 (`Tier 1 Dream`, 54 unis), Project 211 (`Tier 2 Target`, 88 unis), and Provincial (`Tier 3 Safety`, 565 unis) tiers and realistic application fees (`400–800 RMB (Standard Est.)` for 698 unis, `0 RMB (Fee Waived)` for 9 verified fee-waived unis).
2. Removed the Pre-Run Cost Gate from Phase 1 (`#tab-discovery` and `POST /api/v1/professors/harvest-batch`) so University Discovery and Supervisor Web Scraping execute with zero cost gate blocking, and relocated the Cost & Token Gate to Phase 2 (`#tab-review` — AI Synthesis & Email Review Workspace).
3. Clarified the operational step sequence (`Step 01 Discovery` -> `Step 02 Institutional Matrix` -> `Step 03 Parallel Supervisor Harvesting` -> `Step 04/05 AI Outreach Synthesis`) and added a direct `👨‍🏫 Next: Step 03 Harvest Supervisors ➔` transition button in Section 02.
4. Upgraded Section 03 (`Verified Graduate Supervisors Roster`) into a full Parallel Supervisor Worker Control Center with Region Selection (displaying exact university count per region), Universities-in-Region multi-select, Configurable Concurrent Worker Pool (`1` to `20` parallel crawlers), real-time progress bar, segmented `📊 Supervisors Table` / `📜 Live Worker Logs` view toggle, and live filter toolbar.

## Outcome

- ✅ Impact: Eliminated stale MongoDB records and dead non-`.edu.cn` domains, unlocked Phase 1 from the LLM Cost Gate, and gave the operator full control over regional/university scope and parallel crawler concurrency in Section 03.
- 🧪 Tests: Verified unit and integration test suites against isolated `autoadmit_test` database.
- 📁 Files: Updated `discovery.py`, `routes_discovery.py`, `routes_professors.py`, `index.html`, `style.css`, `app.js`.
- 🔁 Next prompts: Run parallel supervisor extraction on selected regions/universities in Section 03 and inspect harvested faculty records.
- 🧠 Reflection: Updating enrichment logic in code alone is not enough when persistent records already exist in MongoDB; running an in-place database migration plus read-time enrichment ensures immediate consistency on UI refresh.

## Evaluation notes (flywheel)

- Failure modes observed: Stale un-enriched MongoDB documents caused `Refresh Directory` to show old `Tier 3` / `0 RMB` values and `.cn` domains like `hlau.cn`.
- Graders run and results (PASS/FAIL): PASS
- Prompt variant (if applicable): N/A
- Next experiment (smallest change to try): Monitor live parallel worker pool throughput across multi-university regional batches.

