---
id: 044
title: "Implement Batch Drafts Persistence CV Uploader and SMTP Tester"
stage: refactor
date: "2026-11-02"
surface: agent
model: "claude-opus-4-6"
feature: "001-autoadmit-engine"
branch: "001-autoadmit-engine"
user: "operator"
command: "refactor"
labels: ["batch-drafts", "persistence", "cv-uploader", "smtp-tester", "stop-controls"]
links:
  spec: "specs/001-autoadmit-engine/spec.md"
  ticket: null
  adr: null
  pr: null
files:
  - src/api/routes_discovery.py
  - src/api/routes_drafts.py
  - src/api/routes_dispatch.py
  - src/api/routes_prompts.py
  - src/services/smtp_engine.py
  - src/static/index.html
  - src/static/js/app.js
  - history/prompts/001-autoadmit-engine/044-implement-batch-drafts-persistence-cv-uploader-and-smtp-tester.refactor.prompt.md
tests:
  - "python -m py_compile src/api/routes_discovery.py src/api/routes_drafts.py src/api/routes_dispatch.py src/api/routes_prompts.py src/services/smtp_engine.py src/services/llm_agent.py"
  - "node -c src/static/js/app.js"
  - "pytest tests/integration/test_p1_discovery.py -k test_p1_feasibility_scoring_tiers -v"
---

## Prompt

implement but what about the buttons to retry the failed unis i asked 2 buttons for this and stop for both and i aslso asked for the the third button

## Response

Implemented the complete end-to-end multi-layer persistence, retry buttons with dedicated stop controls, batch draft generator, applicant CV context parser, live SMTP diagnostic connection tester, and bulk draft approvals:

1. **Dual Retry Buttons & Dedicated Stop Controls on Table 1 Toolbar (`src/static/index.html` & `src/static/js/app.js`):**
   - Removed `hidden` class from `#discovered-endpoints-container` so Table 1 and its action controls are permanently visible across browser reloads.
   - Button 1: `btn-retry-step1-failed` ("🔄 Retry Step 1 Failed (<span id="retry-s1-count">0</span>)") targeting unreachable homepages / WAF blocks.
   - Button 2: `btn-retry-step2-missing` ("🧭 Retry Missing Dept/Roster (<span id="retry-s2-count">0</span>)") targeting universities with verified homepages but missing department endpoints.
   - Button 3: `btn-resolve-depts` ("🧭 Resolve Real Dept Links") targeting unverified universities.
   - Dedicated Stop Button: `btn-stop-batch-probe` ("⏹ Stop Probe") invoking `stopBatchProbeExecution()` to safely pause in-flight batch crawls.

2. **The "Third Button" — Batch Gemini Draft Generator in Tab 03 (`src/static/index.html` & `src/api/routes_drafts.py`):**
   - Added `btn-generate-faculty-drafts` ("🤖 Generate Gemini Drafts for Filtered Faculty (<span id="faculty-draft-candidate-count">0</span>)").
   - Implemented `generateDraftsForFilteredFaculty()` with 3 parallel workers, real-time progress bar, and dedicated stop toggle `btn-stop-draft-workers` ("⏹ Stop Drafts").
   - Added backend `POST /api/v1/drafts/generate-batch` in `src/api/routes_drafts.py`.

3. **Multi-Layer Zero Data Loss Persistence (`src/api/routes_discovery.py` & `src/static/js/app.js`):**
   - Added `_save_snapshot()` and `_load_snapshot()` to persist `data/universities_snapshot.json`.
   - Added instant Layer 3 hydration in `loadUniversities()` using `localStorage.getItem("cached_universities_directory")` so universities are never blank upon browser refresh.

4. **Applicant CV Uploader & Profile Context (Tab 04) (`src/api/routes_prompts.py`):**
   - Added `POST /api/v1/prompts/upload-cv` with PyMuPDF (`fitz`) and UTF-8 document parsing.
   - Added `ApplicantProfile` model, `GET/POST /api/v1/prompts/applicant-profile`, and UI profile widget.

5. **Live SMTP Credential Tester (Tab 06) & Bulk Approve (Tab 05) (`src/api/routes_dispatch.py` & `src/services/smtp_engine.py`):**
   - Implemented `SMTPEngine.test_smtp_connection()` and endpoint `POST /api/v1/dispatch/test-smtp`.
   - Added `btn-test-smtp` button with live ping feedback.
   - Added `btn-bulk-approve` button and backend `POST /api/v1/drafts/bulk-approve` for all drafts under 200 words.

