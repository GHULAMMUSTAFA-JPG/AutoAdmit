# Implementation Plan: AutoAdmit Engine

**Branch**: `001-autoadmit-engine` | **Date**: 2026-10-30 | **Spec**: [spec.md](file:///d:/Sch/specs/001-autoadmit-engine/spec.md)  
**Input**: PRD.md, rules.md, and AutoAdmit Engine Constitution

---

## Summary

The AutoAdmit Engine is an end-to-end, multi-country graduate admission discovery, empirical profile assessment, and cold-outreach automation platform. The platform specifically compensates for academic GPA cutoffs (2.68 CGPA) by strategically targeting supervisor acceptance letters and full funding under the Chinese Government Scholarship (CSC Type B), Provincial Government Scholarships, and University Presidential Scholarships for Master's in CS/AI.

The technical approach implements a clean, modular Python 3.11 asynchronous architecture utilizing FastAPI, MongoDB (Motor/PyMongo with Change Streams), `httpx` and `playwright` for grounded dual-tier scraping, Google Gemini 1.5 for factual research synthesis and GPA-compensated outreach generation, and a multi-layer defense-in-depth safety engine for outbound SMTP dispatch, pixel tracking, and IMAP inbound reply harvesting.

---

## Technical Context

* **Language/Version:** Python 3.11+
* **Primary Dependencies:**
  * Web Framework: `fastapi`, `uvicorn`, `websockets`
  * Data Validation & Settings: `pydantic`, `pydantic-settings`
  * Database: `motor`, `pymongo` (MongoDB 6.0+)
  * Networking & Scraping: `httpx`, `playwright`, `beautifulsoup4`, `lxml`
  * Intelligence & LLM: `google-genai` / `google-generativeai`
  * Email & Tracking: Python standard `smtplib`, `imaplib`, `email`
  * Templating & Security: `jinja2`, `passlib`, `python-jose` / `secrets`
* **Storage:** MongoDB Community Server (configurable path `DB_STORAGE_PATH` mapped to persistent volume `/data/db` or Google Drive `/content/drive/...`)
* **Testing:** `pytest`, `pytest-asyncio`, `httpx` (TestClient)
* **Target Platform:** Headless Google Colab Pro, Linux VPS (Ubuntu/Debian), or local Windows/Linux workstation, reverse-proxied via Nginx and exposed via Cloudflare Tunnel (`cloudflared`)
* **Project Type:** Modular Web Application (FastAPI backend + Embedded Single-Page App Dashboard)
* **Performance Goals:**
  * Fast-tier static scraping: <500ms per directory page
  * LLM generation: <3s per faculty draft
  * UI response: <100ms API response latency
* **Safety & Security Constraints:**
  * Master Kill-Switch (`SYSTEM_GATE_ACTIVE`) blocks 100% of outbound SMTP sockets
  * Sandbox Test Mode forces 100% test routing to `TEST_RECIPIENT_EMAIL`
  * CST operational sending window: strictly 09:00 - 16:30 CST
  * Rate limits: max 8-10 emails/hour, max 25 emails/day, 90-240s randomized jitter
  * 0% unverified faculty or fabricated data

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Constitutional Principle | Requirement | Compliance Strategy | Status |
|---|---|---|---|
| **I. Architectural Compliance** | FastAPI + MongoDB Change Streams; no Redis; dual-tier scraper | Native Python asyncio background tasks; Motor change streams; httpx + playwright fallback | **PASSED** |
| **II. Zero Data Fabrication** | Verified `.edu.cn` only; check `硕导`/`博导`; fixtures only | Domain whitelist validator, regex qualification detector, strict mock isolation in `tests/fixtures/` | **PASSED** |
| **III. Multi-Layer Email Safety** | Master Kill-Switch, Sandbox Mode, Human Approval | Triple-check gate in SMTP service before socket initialization; filter on `status == APPROVED` | **PASSED** |
| **IV. Async Fault Isolation** | Non-blocking I/O; isolate worker failures | `asyncio.gather` with exception isolation; `EXTRACTION_FAILED` state logging | **PASSED** |
| **V. Lineage & Persistence** | `source_url`, UTC `scraped_at`, SHA-256 hash, persistent paths | Automatic metadata injection; compound unique indexes; configurable `DB_STORAGE_PATH` and `LOG_DIR` | **PASSED** |
| **VI. Test-First Matrix** | P1 to P6 verification matrix | Automated test suite verifying all 6 phases | **PASSED** |

---

## Project Structure

```text
d:\Sch\
├── .specify/
│   ├── memory/constitution.md
│   └── templates/
├── specs/
│   └── 001-autoadmit-engine/
│       ├── spec.md
│       ├── plan.md
│       ├── tasks.md
│       ├── data-model.md
│       ├── quickstart.md
│       └── contracts/
│           ├── api-spec.yaml
│           └── schemas.json
├── src/
│   ├── __init__.py
│   ├── config.py                 # Pydantic settings, env vars, safety switches
│   ├── main.py                   # FastAPI application initialization & lifecycle
│   ├── core/
│   │   ├── __init__.py
│   │   ├── database.py           # MongoDB connection & index initialization
│   │   ├── security.py           # Basic Auth / Token verification
│   │   └── logger.py             # Rotating file logging & WebSocket log broadcaster
│   ├── models/
│   │   ├── __init__.py
│   │   ├── university.py         # University & Feasibility schema
│   │   ├── professor.py          # FacultyProfile schema with qualifications
│   │   ├── draft.py              # OutreachDraft & Review schema
│   │   └── telemetry.py          # TrackingPixel & InboundReply schema
│   ├── services/
│   │   ├── __init__.py
│   │   ├── discovery.py          # University Feasibility & Pre-Run Cost Gate
│   │   ├── scraper.py            # Dual-tier harvester (httpx + Playwright)
│   │   ├── normalizer.py         # Email de-obfuscator, deduplicator & SHA-256 hasher
│   │   ├── llm_agent.py          # Gemini 1.5 Research Digest & GPA Compensator
│   │   ├── change_stream.py      # MongoDB Change Stream listener
│   │   ├── smtp_engine.py        # Outbound SMTP with 3-Layer Safety & Jitter
│   │   ├── imap_engine.py        # Inbound reply tracker & header matcher
│   │   └── tracker.py            # 1x1 transparent tracking pixel service
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py               # Dependency injection (DB, Auth, Config)
│   │   ├── routes_discovery.py   # Intake, Feasibility, Cost approval
│   │   ├── routes_professors.py  # Faculty roster query & filter
│   │   ├── routes_drafts.py      # Review workspace, edit, approve, reject
│   │   ├── routes_dispatch.py    # Outbox queue, single/batch send, CST config
│   │   ├── routes_tracking.py    # Pixel hit endpoint & analytics stats
│   │   └── routes_system.py      # Health, Kill-Switch toggle, WebSocket logs
│   └── static/
│       ├── index.html            # 7-Tab Responsive Single-Page Application
│       ├── css/
│       │   └── style.css         # Modern dark/light dashboard theme
│       └── js/
│           └── app.js            # Reactive SPA state, API clients, WebSocket logs
├── tests/
│   ├── __init__.py
│   ├── conftest.py               # Fixtures, test client, mocked DB/SMTP/LLM
│   ├── fixtures/
│   │   ├── sample_pages/         # Sample static & dynamic university HTML pages
│   │   └── sample_data.py        # Seed records for testing
│   ├── unit/
│   │   ├── test_config.py
│   │   ├── test_security.py
│   │   ├── test_normalizer.py
│   │   ├── test_feasibility.py
│   │   └── test_qualification.py
│   └── integration/
│       ├── test_p1_discovery.py  # P1: Intake & Pre-run cost gate
│       ├── test_p2_scraper.py    # P2: Grounded scraper & supervisor filtering
│       ├── test_p3_storage.py    # P3: Persistence & deduplication
│       ├── test_p4_llm_agent.py  # P4: Gemini synthesis & GPA compensation
│       ├── test_p5_safety.py     # P5: Master Kill-Switch & SMTP safety
│       └── test_p6_tracking.py   # P6: Pixel tracking & IMAP reply poller
├── requirements.txt
├── .env.example
├── PRD.md
└── rules.md
```

---

## Detailed Component Specifications

### 1. Configuration & Safety Core (`src/config.py`)
- Manages all environment parameters with strict typing via `pydantic-settings`.
- Enforces safety defaults:
  - `SYSTEM_GATE_ACTIVE`: defaults to `True` (fail-safe on boot).
  - `SANDBOX_MODE`: defaults to `True`.
  - `TEST_RECIPIENT_EMAIL`: required for sandbox testing.
  - `DB_STORAGE_PATH`: configurable (e.g. `./data/db` or `/content/drive/...`).
  - `LOG_DIR`: configurable (e.g. `./data/logs`).
  - `CST_SEND_START_HOUR`: `9` (09:00 CST).
  - `CST_SEND_END_HOUR`: `16` (16:30 CST).
  - `MAX_EMAILS_PER_HOUR`: `10`.
  - `MAX_EMAILS_PER_DAY`: `25`.
  - `JITTER_MIN_SECONDS`: `90`.
  - `JITTER_MAX_SECONDS`: `240`.

### 2. Dual-Tier Scraper (`src/services/scraper.py`)
- Whitelist validator: ensures target URL matches `^https?://([a-zA-Z0-9-]+\.)*(edu\.cn|ac\.[a-z]{2,3})$`.
- Fast tier: Asynchronous `httpx.AsyncClient` with custom headers, timeouts, and connection pooling.
- Dynamic fallback: Headless `playwright.async_api.async_playwright` triggered when static response lacks faculty elements or exhibits client-rendering markers.
- Supervisory title parser: Matches `博导`, `硕导`, `博士生导师`, `硕士生导师` against faculty titles/biographies. Drops non-qualifying records immediately.

### 3. Normalizer & Hasher (`src/services/normalizer.py`)
- Email cleaner: De-obfuscates `[at]`, `(at)`, ` [dot] `, `&#64;`, spaces, and entity references.
- Content hash: Generates cryptographic SHA-256 string from raw page payload to detect changes and enforce audit trails.
- Deduplication key generator: Creates canonical unique tokens (`email.lower()`, `name.lower()_univ.lower()`).

### 4. Gemini LLM Synthesis Agent (`src/services/llm_agent.py`)
- Prompt A: Factual Research Digest (2-3 sentences on core lab problem and technical frameworks).
- Prompt B: Personalized Cold Outreach (<200 words, high-conversion subject line, PyTorch/Agentic AI engineering highlight, explicit declaration of applying for independent full scholarships, no GPA mention).
- Guardrails: Word count verification, forbidden keyword check (`2.68`, `GPA`, `low grades`), status initialized strictly to `PENDING_REVIEW`.

### 5. Outbound SMTP Safety Engine (`src/services/smtp_engine.py`)
- Gate 1: Check `config.SYSTEM_GATE_ACTIVE`. If `True`, raise `SecurityGateException(403)`.
- Gate 2: Check `config.SANDBOX_MODE`. If `True`, replace recipient with `config.TEST_RECIPIENT_EMAIL`.
- Gate 3: Filter database records strictly on `status == "APPROVED"`.
- CST Window Checker: Compares current UTC+8 time against `09:00` - `16:30`. Pauses if out of window.
- Rate Limiter & Jitter: Tracks hourly/daily counters and applies `asyncio.sleep(random.uniform(90, 240))`.

### 6. Telemetry & Inbound Harvester (`src/services/tracker.py` & `imap_engine.py`)
- Pixel Endpoint: `/api/v1/track/open/{draft_id}` returns transparent 1x1 GIF (`image/gif`), updates `open_count`, `first_opened_at`, `last_opened_at`.
- IMAP Harvester: Connects via `imaplib.IMAP4_SSL`, scans for `In-Reply-To` and `References` containing sent `Message-ID`s, updates draft status to `REPLIED`, records reply timestamp and latency.

### 7. Single-Page Application (SPA) Web Dashboard (`src/static/`)
- Responsive dark/light themed interface with 7 dedicated tabs matching PRD Section 5:
  1. Top Navigation & Safety Bar (Master Kill-Switch, Sandbox Switch, Live CST Clock, Volume Mount status).
  2. Campaign Setup & Resource Estimation (Pre-seeded intake, CGPA compensation profile, Cost estimator gate).
  3. University & Feasibility Directory (Interactive table with Tier 1/2/3 badges and scholarship types).
  4. Faculty Roster & Extraction Stream (Verified supervisors, qualification tags, source links).
  5. Email Review & Approval Staging (Split-pane editor: profile digest on left, subject/body on right with Approve/Discard/Regenerate).
  6. Outbox Dispatcher & Delivery Scheduler (Sending mode selector, hourly caps, queue progress bar).
  7. Analytics & Response Tracker (Delivery rate, open pixel count, reply latency, thread viewer).
  8. System Terminal & Live Log Streaming (WebSocket real-time streaming filtered by module).

---

## Phase Verification Test Matrix (P1-P6)

1. **P1 Test (`test_p1_discovery.py`):** Passes valid and invalid department URLs, verifies schema validation, and confirms extraction sequence remains blocked until Pre-Run Cost Gate is explicitly approved.
2. **P2 Test (`test_p2_scraper.py`):** Runs scraper against sample HTML fixtures, verifies supervisor qualification filters (`博导`/`硕导`), email de-obfuscation, and fault isolation (`EXTRACTION_FAILED`).
3. **P3 Test (`test_p3_storage.py`):** Tests database persistence, deduplication compound indexes, and simulated restart recovery.
4. **P4 Test (`test_p4_llm_agent.py`):** Tests prompt synthesis, checks word count (<200 words), confirms GPA is omitted and applied AI is spotlighted, and verifies draft status is `PENDING_REVIEW`.
5. **P5 Test (`test_p5_safety.py`):** Verifies Master Kill-Switch aborts SMTP dispatch with `403 Forbidden` and zero network traffic; verifies Sandbox Mode overrides recipient.
6. **P6 Test (`test_p6_tracking.py`):** Tests 1x1 tracking pixel hit logging and IMAP poller header matching (`In-Reply-To`/`References`) updating status to `REPLIED`.
