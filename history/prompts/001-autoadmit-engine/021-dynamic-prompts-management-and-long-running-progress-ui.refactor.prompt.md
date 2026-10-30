---
id: "021"
title: "Dynamic Prompts Management in MongoDB and Long-Running Progress UI"
stage: "refactor"
date: "2026-10-30"
surface: "agent"
model: "gemini-3.8-flash"
feature: "001-autoadmit-engine"
branch: "001-autoadmit-engine"
user: "parep"
command: "provide prompts from UI, save prompts in DB, redesign discovery and cost gate, button active states, long running progress bar, real time logs and refresh"
labels: ["refactor", "ui", "prompts-management", "mongodb", "progress-bar", "real-time", "button-states"]
links:
  spec: "specs/001-autoadmit-engine/spec.md"
  ticket: null
  adr: "history/adr/0001-multi-source-discovery-verification.md"
  pr: null
files:
  - "src/models/prompt.py"
  - "src/api/routes_prompts.py"
  - "src/main.py"
  - "src/static/index.html"
  - "src/static/css/style.css"
  - "src/static/js/app.js"
tests:
  - "tests/integration/test_p1_discovery.py"
  - "tests/integration/test_p2_scraper.py"
  - "tests/integration/test_p3_storage.py"
  - "tests/integration/test_p4_llm_agent.py"
  - "tests/integration/test_p5_safety.py"
  - "tests/integration/test_p6_tracking.py"
---

## Prompt

also add that we can provide prompts from the UI and we can also hold prompts record and save them in db and change from UI, the UI related to 
DISCOVERY & PRE-RUN COST GATE dont look good and button should like someone clicked and operation started and aslso this is long running process so it should show progress and we can also get real time updates and data and can see on logs and we can also refresh that

## Response snapshot

1. Dynamic Prompt Management Subsystem:
   - Added `src/models/prompt.py` (`PromptRecord`, `PromptUpdateRequest`) with versioning, stage mapping, system prompt, and interpolation variables.
   - Built `src/api/routes_prompts.py` supporting `GET /api/v1/prompts`, `POST /api/v1/prompts`, `PUT /api/v1/prompts/{id}`, and `POST /api/v1/prompts/{id}/activate` targeting MongoDB `prompts` collection.
   - Integrated full visual Prompt Editor in `src/static/index.html` (Section 04) allowing users to create, view, edit, version, and activate system/user prompts with variable chips directly in the database.
2. Discovery & Cost Gate UI Overhaul:
   - Redesigned Section 01 into an elevated enterprise layout with high-contrast filter grouping.
   - Added active button click feedback (`.btn-loading`, animated `.spinner-inline`, dynamic text change) to clearly signal operation start.
3. Long-Running Progress Tracker & Real-Time Telemetry:
   - Added `#operation-progress-card` displaying live stage progression (Stage 1: Live Query -> Stage 2: Filter & Dedup -> Stage 3: Resolving Portals -> Stage 4: Crawling Roster).
   - Real-time animated progress bar with percentage, running elapsed timer, stage badges, and a manual "↻ Refresh Feed" button.
   - Live trace events streamed through WebSocket directly to the Live System Console.
4. All 14 integration tests passing green.

## Outcome

- ✅ Impact: Complete operator autonomy over prompt directives with database persistence, alongside responsive long-running operation progress tracking.
- 🧪 Tests: 14/14 integration tests passing (16.05s).
- 📁 Files: `src/models/prompt.py`, `src/api/routes_prompts.py`, `src/main.py`, `src/static/index.html`, `src/static/css/style.css`, `src/static/js/app.js`.
- 🔁 Next prompts: Ready for end-to-end testing and production deployment.

## Evaluation notes (flywheel)

- Failure modes observed: None
- Graders run and results (PASS/FAIL): PASS
- Prompt variant: default
- Next experiment: N/A

