---
description: "Task list for AutoAdmit Engine implementation"
---

# Tasks: AutoAdmit Engine

**Input**: Design documents from `specs/001-autoadmit-engine/` (spec.md, plan.md)  
**Prerequisites**: plan.md, spec.md, AutoAdmit Engine Constitution  
**Organization**: Tasks are grouped by foundational phase and user stories to enable progressive implementation and test-driven verification.

## Format: `[ID] [P?] [Story] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story or phase this task belongs to

---

## Phase 1: Setup & Environment Initialization

**Purpose**: Project dependency definition, environment configuration, and directory scaffolding.

- [x] T001 Scaffold project directory layout (`src/core`, `src/models`, `src/services`, `src/api`, `src/static`, `tests/fixtures`, `tests/unit`, `tests/integration`).
- [x] T002 Create `requirements.txt` with FastAPI, Uvicorn, Motor, Pydantic, HTTPX, Playwright, BeautifulSoup4, Jinja2, Pytest, and Google GenAI dependencies.
- [x] T003 [P] Create `.env.example` defining all required configuration variables, safety switches, and directory paths.

---

## Phase 2: Foundational Infrastructure (Blocking Prerequisites)

**Purpose**: Core configuration, database connection, authentication, and structured logging.

- [x] T004 Implement typed application configuration with safety defaults in `src/config.py`.
- [x] T005 [P] Implement MongoDB database manager with compound unique indexes and persistent volume support in `src/core/database.py`.
- [x] T006 [P] Implement HTTP Basic Auth and Bearer Token security guardrails in `src/core/security.py`.
- [x] T007 [P] Implement rotating file audit logger and async WebSocket log broadcaster in `src/core/logger.py`.
- [x] T008 Implement base Pydantic schemas in `src/models/` (`university.py`, `professor.py`, `draft.py`, `telemetry.py`).

---

## Phase 3: User Story 1 - Intake, Feasibility & Pre-Run Cost Gate (Priority: P1)

**Goal**: Curate intake targets, evaluate institutional feasibility tiers, and enforce pre-run cost approvals.

- [x] T009 [P] [US1] Create test suite `tests/integration/test_p1_discovery.py` verifying cost gate locking and feasibility scoring.
- [x] T010 [US1] Implement feasibility scoring matrix (Tier 1 Dream, Tier 2 Target, Tier 3 Safety with 2.68 CGPA compensation) in `src/services/discovery.py`.
- [x] T011 [US1] Implement pre-run cost and workload estimator in `src/services/discovery.py`.
- [x] T012 [US1] Implement discovery API endpoints (`/api/v1/discovery/feasibility`, `/api/v1/discovery/estimate`, `/api/v1/discovery/approve`) in `src/api/routes_discovery.py`.

---

## Phase 4: User Story 2 - Grounded Scraper & Supervisor Verification (Priority: P2)

**Goal**: Dual-tier scraping with `.edu.cn` domain whitelist and strict supervisory qualification filtering.

- [x] T013 [P] [US2] Create test fixtures and integration tests in `tests/fixtures/sample_pages/` and `tests/integration/test_p2_scraper.py`.
- [x] T014 [US2] Implement domain whitelist validation and anti-redirection safety in `src/services/scraper.py`.
- [x] T015 [US2] Implement fast-tier async HTTP extractor in `src/services/scraper.py`.
- [x] T016 [US2] Implement fallback headless Playwright extractor in `src/services/scraper.py`.
- [x] T017 [US2] Implement supervisory qualification detection (`博导`, `硕导`) and faculty parser in `src/services/scraper.py`.
- [x] T018 [US2] Implement data normalizer (email de-obfuscation, SHA-256 content hashing) in `src/services/normalizer.py`.
- [x] T019 [US2] Implement faculty API endpoints (`/api/v1/professors/`) in `src/api/routes_professors.py`.

---

## Phase 5: User Story 3 - Persistence, Deduplication & Change Streams (Priority: P3)

**Goal**: Resilient document persistence, database-level deduplication, and event-driven LLM triggering.

- [x] T020 [P] [US3] Create persistence and resilience tests in `tests/integration/test_p3_storage.py`.
- [x] T021 [US3] Implement deduplication handlers and audit trail injector in `src/services/normalizer.py` and `src/core/database.py`.
- [x] T022 [US3] Implement async MongoDB Change Stream listener in `src/services/change_stream.py`.

---

## Phase 6: User Story 4 - Gemini LLM Synthesis & GPA Compensation (Priority: P4)

**Goal**: Factual research digest generation and high-conversion cold outreach under 200 words.

- [x] T023 [P] [US4] Create LLM synthesis and guardrail tests in `tests/integration/test_p4_llm_agent.py`.
- [x] T024 [US4] Implement prompt engineering for factual 2-3 sentence research digest in `src/services/llm_agent.py`.
- [x] T025 [US4] Implement GPA-compensated outreach generator (<200 words, financial independence, PyTorch/applied AI focus) in `src/services/llm_agent.py`.
- [x] T026 [US4] Implement draft review workspace API endpoints (`/api/v1/drafts/`) in `src/api/routes_drafts.py`.

---

## Phase 7: User Story 5 - SMTP Safety Engine & CST Dispatch (Priority: P5)

**Goal**: Triple-gate outbound email safety, Master Kill-Switch, sandbox routing, and CST schedule with jitter.

- [x] T027 [P] [US5] Create safety gate and dispatch tests in `tests/integration/test_p5_safety.py`.
- [x] T028 [US5] Implement Master Kill-Switch (`SYSTEM_GATE_ACTIVE`) and Sandbox Mode router in `src/services/smtp_engine.py`.
- [x] T029 [US5] Implement CST operational window validator (09:00 - 16:30 CST) and rate limiter (8-10/hr, 25/day) in `src/services/smtp_engine.py`.
- [x] T030 [US5] Implement randomized jitter control (90-240s) and PDF attachment handler in `src/services/smtp_engine.py`.
- [x] T031 [US5] Implement dispatch API endpoints (`/api/v1/dispatch/queue`, `/api/v1/dispatch/send`) in `src/api/routes_dispatch.py`.

---

## Phase 8: User Story 6 - Pixel Tracking & Inbound IMAP Response Poller (Priority: P6)

**Goal**: Transparent 1x1 tracking pixel logging and asynchronous IMAP reply matching.

- [x] T032 [P] [US6] Create tracking and telemetry tests in `tests/integration/test_p6_tracking.py`.
- [x] T033 [US6] Implement 1x1 transparent GIF tracking endpoint in `src/services/tracker.py` and `src/api/routes_tracking.py`.
- [x] T034 [US6] Implement asynchronous IMAP response poller with `In-Reply-To` and `References` header matching in `src/services/imap_engine.py`.

---

## Phase 9: User Story 7 - Unified SPA Web Dashboard & WebSocket Terminal (Priority: P7)

**Goal**: Responsive 7-tab dashboard with safety bar, review editor, dispatch queue, analytics, and live terminal.

- [x] T035 [P] [US7] Implement system status and WebSocket log streaming endpoint in `src/api/routes_system.py`.
- [x] T036 [US7] Implement single-page dashboard HTML with 7 tabs matching PRD specifications in `src/static/index.html`.
- [x] T037 [US7] Implement dashboard styles (modern dark/light theme, split-pane layout) in `src/static/css/style.css`.
- [x] T038 [US7] Implement reactive JavaScript application (safety toggles, draft editing, queue manager, live log stream) in `src/static/js/app.js`.

---

## Phase 10: End-to-End Verification & Production Readiness

**Purpose**: Execute test suite, verify P1-P6 matrix, validate zero fabrication rules, and generate implementation report.

- [x] T039 Execute test suite across all modules (`pytest tests/`).
- [x] T040 Verify complete P1 to P6 test matrix compliance and zero mock data in production paths.
- [x] T041 Generate `implementation.md` documenting verified architecture, deployment commands, and verification logs.

