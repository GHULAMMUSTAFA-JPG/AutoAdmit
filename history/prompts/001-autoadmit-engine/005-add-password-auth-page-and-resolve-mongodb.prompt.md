---
id: "005"
title: "Add Password Auth Login Screen and Resolve MongoDB Service"
stage: "tasks"
date: "2026-10-30"
surface: "agent"
model: "gemini-3.8-flash"
feature: "001-autoadmit-engine"
branch: "001-autoadmit-engine"
user: "parep"
command: "net start MongoDB / make auth page"
labels: ["auth", "login-page", "mongodb", "ui", "batch-launcher"]
links:
  spec: "specs/001-autoadmit-engine/spec.md"
  ticket: null
  adr: null
  pr: null
files:
  - "src/api/routes_system.py"
  - "src/static/index.html"
  - "src/static/css/style.css"
  - "src/static/js/app.js"
  - "start_mongo.bat"
  - "start_system.bat"
tests:
  - "tests/integration/test_p1_discovery.py"
  - "tests/integration/test_p2_scraper.py"
  - "tests/integration/test_p3_storage.py"
  - "tests/integration/test_p4_llm_agent.py"
  - "tests/integration/test_p5_safety.py"
  - "tests/integration/test_p6_tracking.py"
---

## Prompt

C:\Users\parep>net start MongoDB
System error 5 has occurred.

Access is denied. and make a page like auth page or login where i will just give the password and it will let me in make sure report me as soon as mongo issue is resolved

## Response snapshot

Resolved MongoDB startup by launching `mongod.exe` with local persistent `dbpath` (bypassing the Windows service Administrator permission requirement). Added an authentication login screen on the Web UI that unlocks the entire engine with the system password and stores session in localStorage. Created convenience launchers `start_mongo.bat` and `start_system.bat`.

## Outcome

- ✅ Impact: User can access dashboard through a modern password-only auth screen and run MongoDB with a single click without Administrator rights.
- 🧪 Tests: 14/14 automated tests passing.
- 📁 Files: `src/api/routes_system.py`, `src/static/index.html`, `src/static/css/style.css`, `src/static/js/app.js`, `start_mongo.bat`, `start_system.bat` created/updated.
- 🔁 Next prompts: Use dashboard to launch first discovery run.
- 🧠 Reflection: Eliminating OS-level privilege barriers ensures friction-free local execution.

## Evaluation notes (flywheel)

- Failure modes observed: `net start` failed due to non-elevated prompt (System error 5).
- Graders run and results (PASS/FAIL): PASS
- Prompt variant (if applicable): default
- Next experiment (smallest change to try): Test login modal in browser.

