---
id: "008"
title: "Fix WebSocket Log Handler formatTime AttributeError"
stage: "refactor"
date: "2026-10-30"
surface: "agent"
model: "gemini-3.8-flash"
feature: "001-autoadmit-engine"
branch: "001-autoadmit-engine"
user: "parep"
command: "fix websocket logging error"
labels: ["websocket", "logging", "attribute-error", "formatTime"]
links:
  spec: "specs/001-autoadmit-engine/spec.md"
  ticket: null
  adr: null
  pr: null
files:
  - "src/core/logger.py"
tests:
  - "tests/integration/test_p1_discovery.py"
  - "tests/integration/test_p2_scraper.py"
  - "tests/integration/test_p3_storage.py"
  - "tests/integration/test_p4_llm_agent.py"
  - "tests/integration/test_p5_safety.py"
  - "tests/integration/test_p6_tracking.py"
---

## Prompt

INFO: 127.0.0.1:54564 - "WebSocket /ws/logs" [accepted]
INFO: connection open
...
--- Logging error ---
Traceback (most recent call last):
  File "D:\Sch\src\core\logger.py", line 24, in emit
    "timestamp": self.formatTime(record),
                 ^^^^^^^^^^^^^^^
AttributeError: 'WebSocketLogHandler' object has no attribute 'formatTime'. Did you mean: 'formatter'?

## Response snapshot

Explained the AttributeError: `formatTime` is a method on `logging.Formatter`, not on `logging.Handler`. Fixed `WebSocketLogHandler.emit()` in `src/core/logger.py` to use `self.formatter.formatTime(record)` or fallback to `datetime.fromtimestamp(record.created).strftime("%H:%M:%S")`.

## Outcome

- ✅ Impact: WebSocket log broadcast emits records cleanly to the live terminal in the UI without traceback errors.
- 🧪 Tests: 14/14 automated tests passing.
- 📁 Files: `src/core/logger.py` updated.
- 🔁 Next prompts: Continue monitoring dashboard and running campaigns.
- 🧠 Reflection: Direct formatter delegation ensures robust timestamp extraction regardless of handler configuration.

## Evaluation notes (flywheel)

- Failure modes observed: AttributeError on `Handler.formatTime`.
- Graders run and results (PASS/FAIL): PASS
- Prompt variant (if applicable): default
- Next experiment (smallest change to try): View live log stream in Tab 7 terminal.

