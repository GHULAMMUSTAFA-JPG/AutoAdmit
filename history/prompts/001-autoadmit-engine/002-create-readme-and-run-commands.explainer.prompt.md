---
id: "002"
title: "Create README and System Run Commands"
stage: "explainer"
date: "2026-10-30"
surface: "agent"
model: "gemini-3.8-flash"
feature: "001-autoadmit-engine"
branch: "001-autoadmit-engine"
user: "parep"
command: "create readme and run commands"
labels: ["documentation", "readme", "quickstart", "run-commands"]
links:
  spec: "specs/001-autoadmit-engine/spec.md"
  ticket: null
  adr: null
  pr: null
files:
  - "README.md"
tests:
  - "tests/integration/test_p1_discovery.py"
  - "tests/integration/test_p2_scraper.py"
  - "tests/integration/test_p3_storage.py"
  - "tests/integration/test_p4_llm_agent.py"
  - "tests/integration/test_p5_safety.py"
  - "tests/integration/test_p6_tracking.py"
---

## Prompt

give me commands to run this system and also i want you to make the readme.md file and fill it with info on how to run this system and what to do to run this system

## Response snapshot

Created comprehensive README.md covering system architecture, installation, configuration, testing, running with Uvicorn, and 7-tab UI workflow. Provided copy-paste ready commands to launch and test the application.

## Outcome

- ✅ Impact: Complete run guide, command reference, and documentation artifact established in README.md.
- 🧪 Tests: 14/14 automated tests passing.
- 📁 Files: README.md created and updated in project root.
- 🔁 Next prompts: Execution and live campaign management.
- 🧠 Reflection: Clear separation between dry-run/sandbox modes and live dispatch ensures user confidence and safety compliance.

## Evaluation notes (flywheel)

- Failure modes observed: None
- Graders run and results (PASS/FAIL): PASS
- Prompt variant (if applicable): default
- Next experiment (smallest change to try): Launch server and verify UI dashboard locally.

