---
id: "014"
title: "Senior Frontend Light Theme Redesign and Test Database Isolation"
stage: "refactor"
date: "2026-10-30"
surface: "agent"
model: "gemini-3.8-flash"
feature: "001-autoadmit-engine"
branch: "001-autoadmit-engine"
user: "parep"
command: "redesign UI to one big page light theme and isolate test db"
labels: ["refactor", "ui", "light-theme", "one-big-page", "db-isolation", "pytest"]
links:
  spec: "specs/001-autoadmit-engine/spec.md"
  ticket: null
  adr: null
  pr: null
files:
  - "src/static/css/style.css"
  - "src/static/index.html"
  - "src/static/js/app.js"
  - "tests/conftest.py"
  - "src/api/routes_discovery.py"
  - "src/api/routes_dispatch.py"
  - "src/api/routes_drafts.py"
  - "src/core/database.py"
tests:
  - "tests/integration/test_p1_discovery.py"
  - "tests/integration/test_p2_scraper.py"
  - "tests/integration/test_p3_storage.py"
  - "tests/integration/test_p4_llm_agent.py"
  - "tests/integration/test_p5_safety.py"
  - "tests/integration/test_p6_tracking.py"
---

## Prompt

so excepts logs we are saving everything to db and then reading from db the tests cannot populate db with test or sample or mock content so and second the UI make it one big page and then bg should be light not dark and design should look good and consistent make it like a senior front end engineer

## Response snapshot

1. Test Database Isolation: Configured `tests/conftest.py` with `settings.DB_NAME = "autoadmit_test"` and automatic teardown cleanup, guaranteeing that test runs (`pytest`) execute strictly in an isolated test database and NEVER pollute or touch the production/runtime database (`autoadmit`).
2. MongoDB Persistence and Retrieval: Connected all operational routes (`universities`, `professors`, `outreach_drafts`, `telemetry`, `inbound_replies`) to persist and read from MongoDB. Added `universities` collection index.
3. One Big Page Flow: Redesigned the UI layout from hidden tab switching to a continuous, linear single-page flow where all 7 core workflow sections are displayed sequentially with smooth scroll navigation and dynamic `IntersectionObserver` scrollspy.
4. Senior Frontend Light Theme: Replaced the dark theme with a clean, modern SaaS light design system (Inter/system-ui typography, slate neutral palette, crisp white elevated cards, subtle borders, polished metric boxes, and clean pill badges).
5. All 14 integration tests passing green.

## Outcome

- ✅ Impact: The dashboard is unified into a cohesive, senior-level light theme page with 100% database persistence and complete test database isolation.
- 🧪 Tests: 14/14 integration tests passed (25.74s).
- 📁 Files: `src/static/css/style.css`, `src/static/index.html`, `src/static/js/app.js`, `tests/conftest.py`, `src/api/routes_discovery.py`, `src/api/routes_dispatch.py`, `src/api/routes_drafts.py`, `src/core/database.py`.
- 🔁 Next prompts: User can open dashboard, log in with password `2026`, and run discovery or review drafts.
- 🧠 Reflection: Single-page scroll combined with a sticky table-of-contents dock provides a significantly smoother user experience than fragmented tabs.

## Evaluation notes (flywheel)

- Failure modes observed: None
- Graders run and results (PASS/FAIL): PASS
- Prompt variant: default
- Next experiment: N/A
