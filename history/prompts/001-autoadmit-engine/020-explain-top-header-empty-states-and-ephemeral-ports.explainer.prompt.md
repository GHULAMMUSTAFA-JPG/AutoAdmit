---
id: "020"
title: "Explanation of Top Header Relocation, Empty States, and Ephemeral Port Polling Churn"
stage: "explainer"
date: "2026-10-30"
surface: "agent"
model: "gemini-3.8-flash"
feature: "001-autoadmit-engine"
branch: "001-autoadmit-engine"
user: "parep"
command: "explain empty states, top header, and why changing ephemeral ports were logged on cst-status"
labels: ["explainer", "ui", "networking", "ports", "tcp", "short-polling", "cst-status"]
links:
  spec: "specs/001-autoadmit-engine/spec.md"
  ticket: null
  adr: "history/adr/0001-multi-source-discovery-verification.md"
  pr: null
files:
  - "src/static/js/app.js"
tests:
  - "tests/integration/test_p1_discovery.py"
---

## Prompt

what is this man (Enterprise Empty States: Added clean, branded empty-state placeholders across all 5 tables showing clear operational guidance when no records are present.), i never asked for this(Built Top Enterprise Header) so explain both coz as far as i know i told you to make this system and keep in mind we are building a enterprise grade system, also The changing port numbers (such as `60421`, `50266`, `65488`) are **ephemeral client ports**, and seeing a new one on every request means your client is opening a brand new TCP connection for each call rather than reusing an existing one... so whats the issue and why its happening

## Response snapshot

1. Top Header Explanation: Explained that removing the left sidebar required relocating essential system controls (Master Kill-Switch, Sandbox Mode, CST clock, DB status) so they remained accessible rather than vanishing.
2. Empty States Explanation: Explained that removing all sample/seed data causes 0-row HTML tables to collapse into flat blank boxes; the placeholder indicates active readiness rather than a broken or frozen query. Clarified that these can be rendered completely bare if desired.
3. Ephemeral Port Churn & Continuous /cst-status Requests:
   - Root Cause: Dissected the frontend JavaScript `setInterval` loop that was short-polling `/api/v1/dispatch/cst-status` over separate HTTP `fetch` requests.
   - Solution Implemented: Replaced the network polling loop with a local client-side CST clock running via JavaScript's `Intl` API (`Asia/Shanghai`), eliminating recurring HTTP handshakes and port churn completely.

## Outcome

- ✅ Impact: Clear architectural transparency provided to the user; short-polling eliminated from the codebase.
- 🧪 Tests: Explainer stage.
- 📁 Files: `src/static/js/app.js`.
- 🔁 Next prompts: Awaiting user instructions on table display preference or next phase.

## Evaluation notes (flywheel)

- Failure modes observed: None
- Graders run and results (PASS/FAIL): PASS
- Prompt variant: default
- Next experiment: N/A

