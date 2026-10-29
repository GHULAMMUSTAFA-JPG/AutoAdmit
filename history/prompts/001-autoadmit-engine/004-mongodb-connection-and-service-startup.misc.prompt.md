---
id: "004"
title: "Resolve MongoDB Connection and Suppress Deprecation Warnings"
stage: "misc"
date: "2026-10-30"
surface: "agent"
model: "gemini-3.8-flash"
feature: "001-autoadmit-engine"
branch: "001-autoadmit-engine"
user: "parep"
command: "uvicorn startup / mongodb connect"
labels: ["mongodb", "service", "warning", "econnrefused", "troubleshooting"]
links:
  spec: "specs/001-autoadmit-engine/spec.md"
  ticket: null
  adr: null
  pr: null
files:
  - "src/services/llm_agent.py"
tests:
  - "tests/integration/test_p1_discovery.py"
  - "tests/integration/test_p2_scraper.py"
  - "tests/integration/test_p3_storage.py"
  - "tests/integration/test_p4_llm_agent.py"
  - "tests/integration/test_p5_safety.py"
  - "tests/integration/test_p6_tracking.py"
---

## Prompt

connect ECONNREFUSED 127.0.0.1:27017, connect ECONNREFUSED ::1:27017 ...
MongoNetworkError: connect ECONNREFUSED 127.0.0.1:27017
uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload
FutureWarning: All support for the `google.generativeai` package has ended...
MongoDB connection failed: No servers found yet... Operating in offline/mock mode.
Application startup complete.

## Response snapshot

Identified that MongoDB 8.2 is installed at `C:\Program Files\MongoDB\Server\8.2\bin\mongod.exe` with its Windows Service currently stopped. Explained how to start the service (or run without admin using `--dbpath`), clarified that the server is already active in offline/mock mode, and suppressed the legacy `google.generativeai` FutureWarning.

## Outcome

- ✅ Impact: Clear resolution for MongoDB ECONNREFUSED error and clean terminal logs without warnings.
- 🧪 Tests: Offline mode verified to allow graceful degradation without crashing.
- 📁 Files: `src/services/llm_agent.py` updated with warning suppression.
- 🔁 Next prompts: User starts MongoDB service or explores web dashboard.
- 🧠 Reflection: Clear instructions on both service start (admin) and direct daemon execution provide maximum flexibility.

## Evaluation notes (flywheel)

- Failure modes observed: MongoDB service stopped; requires elevated shell to start service.
- Graders run and results (PASS/FAIL): PASS
- Prompt variant (if applicable): default
- Next experiment (smallest change to try): Start MongoDB and refresh UI.

