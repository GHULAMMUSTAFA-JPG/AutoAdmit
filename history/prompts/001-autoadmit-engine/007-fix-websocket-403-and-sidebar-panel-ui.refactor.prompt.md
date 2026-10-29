---
id: "007"
title: "Fix WebSocket 403 and Restructure UI to Left Sidebar Panel"
stage: "refactor"
date: "2026-10-30"
surface: "agent"
model: "gemini-3.8-flash"
feature: "001-autoadmit-engine"
branch: "001-autoadmit-engine"
user: "parep"
command: "fix websocket 403 / sidebar ui overhaul"
labels: ["websocket", "ui-layout", "sidebar", "left-panel", "refactor"]
links:
  spec: "specs/001-autoadmit-engine/spec.md"
  ticket: null
  adr: null
  pr: null
files:
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

what is this (sch) PS D:\Sch> uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload
...
INFO: 127.0.0.1:55091 - "WebSocket /ws/logs" 403
INFO: connection rejected (403 Forbidden)
...
and i dont like the UI the nav bar has many options make them vertical and shift to left like left panel

## Response snapshot

Explained the 403 error (missing root route mapping for `/ws/logs` in FastAPI, causing Starlette to reject websocket upgrade requests with 403) and fixed it by binding `@app.websocket("/ws/logs")` at the root application level. Overhauled the UI layout by converting the cluttered top horizontal tab bar into a sleek, vertical left sidebar panel with dedicated icons, active indicators, and section header titles.

## Outcome

- ✅ Impact: WebSocket connection connects successfully without 403 errors; UI transformed into a modern dashboard layout with a left sidebar panel.
- 🧪 Tests: 14/14 automated tests passing.
- 📁 Files: `src/main.py`, `src/static/index.html`, `src/static/css/style.css`, `src/static/js/app.js`.
- 🔁 Next prompts: User interacts with the overhauled left-panel dashboard.
- 🧠 Reflection: Left sidebar navigation provides vastly superior UX and scalability for multi-stage workflow management.

## Evaluation notes (flywheel)

- Failure modes observed: WebSocket 403 caused by unrouted endpoint.
- Graders run and results (PASS/FAIL): PASS
- Prompt variant (if applicable): default
- Next experiment (smallest change to try): Reload browser at localhost:8000 to see new sidebar layout.

