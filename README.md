# AutoAdmit Engine ⚡

**Intelligent Multi-Tier Academic Discovery, Empirical Feasibility Analysis, & High-Conversion Outreach Platform**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.128.0-009688.svg)](https://fastapi.tiangolo.com/)
[![MongoDB](https://img.shields.io/badge/MongoDB-Community%20Server-47A248.svg)](https://www.mongodb.com/)
[![Tests Passing](https://img.shields.io/badge/tests-14%2F14%20passed%20(100%25)-brightgreen.svg)]()
[![Spec-Driven Development](https://img.shields.io/badge/methodology-SpecKit%20Plus%20(SDD)-orange.svg)]()

The **AutoAdmit Engine** is an end-to-end graduate admission discovery, empirical profile assessment, and cold-outreach automation platform. The platform is designed specifically to secure faculty acceptance letters and full scholarships (**Chinese Government Scholarship CSC Type B, Provincial Government Scholarships, and University Presidential Scholarships**) for Master's programs in Computer Science and Artificial Intelligence. 

The system compensates for strict academic cutoffs (such as a **2.68 CGPA**) by prioritizing production engineering credentials, PyTorch implementations, biometric systems, Agentic AI, and independent scholarship financing.

---

## Key Features & Architecture

* **Dual-Tier Grounded Scraper:** Fast static HTML extraction via `httpx` (milliseconds) with headless `Playwright` Chromium fallback for JavaScript-rendered tables. Restricts scraping strictly to official `.edu.cn` subdomains with anti-redirection safety.
* **Supervisor Verification Filter:** Discards administrative staff and non-supervisory lecturers, filtering exclusively for verified graduate advisors (`博士生导师`/`博导`, `硕士生导师`/`硕导`).
* **Level 1 Cryptographic Lineage:** De-obfuscates anti-spam emails (`[at]`, `(dot)`) and computes SHA-256 content hashes with compound unique deduplication indexes.
* **Pre-Run Cost Gate:** Halts crawlers and LLM workers until estimated directory pages, faculty counts, and Gemini tokens are explicitly reviewed and approved.
* **2.68 CGPA Feasibility Compensation:** Categorizes institutions into **Tier 1 (Dream - C9/985)**, **Tier 2 (Target - 211/Key)**, and **Tier 3 (Safety - High Quota/0 Fee)**, targeting younger Associate Professors and active research labs.
* **Gemini 1.5 Synthesis Agent:** Generates factual 2–3 sentence research digests and drafts concise (<200 words) personalized emails assuring complete financial independence (zero lab stipend required), locked to `PENDING_REVIEW`.
* **Triple-Gate Outbound Safety Engine:**
  1. **Gate 1 (Master Kill-Switch):** `SYSTEM_GATE_ACTIVE=True` blocks 100% of outbound SMTP sockets with `403 Forbidden`.
  2. **Gate 2 (Sandbox Test Mode):** Overrides recipients to `TEST_RECIPIENT_EMAIL` with diagnostic headers.
  3. **Gate 3 (Explicit Human Approval):** SMTP workers query only drafts marked `APPROVED`.
* **CST Smart Scheduling & Jitter:** Enforces dispatch strictly during China business hours (**09:00 – 16:30 CST / UTC+8**), hourly caps (10/hr), daily limits (25/day), and randomized pauses (90–240s).
* **Telemetry & Inbound IMAP Harvester:** Invisible 1x1 transparent tracking pixel logs read receipts; async IMAP poller cross-references `In-Reply-To` and `References` headers to transition campaign status to `REPLIED`.
* **Responsive 7-Tab SPA Dashboard:** Real-time web UI featuring split-pane review, dispatch queue manager, live analytics, and WebSocket terminal log streaming.

---

## System Requirements & Prerequisites

1. **Operating System:** Windows, Linux (Ubuntu/Debian), or macOS. (Supports headless execution on **Google Colab Pro** and Linux VPS).
2. **Python:** Version **3.11** or higher.
3. **MongoDB Community Server:** Local MongoDB instance running on port `27017` or cloud MongoDB URI. *(Note: If MongoDB is offline, the system automatically runs with an in-memory test fallback).*
4. **Google Gemini API Key:** For factual research digests and cold outreach generation ([Get Gemini API Key](https://aistudio.google.com/)).
5. **SMTP & IMAP Credentials:** An email account with App Password support (e.g., Gmail, Outlook, or custom academic domain).

---

## Quickstart: How to Run the System

### Step 1: Clone & Install Dependencies

Open PowerShell or your bash terminal in the project directory:

```bash
# Optional: Create and activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1    # On Windows
# source venv/bin/activate     # On Linux / macOS

# Install required dependencies
pip install -r requirements.txt

# Install Playwright browser engines (for dynamic page fallback)
playwright install chromium
```

---

### Step 2: Configure Environment Variables

Create your `.env` configuration from the provided example:

```bash
# Windows PowerShell
Copy-Item .env.example .env

# Linux / macOS
cp .env.example .env
```

Edit `.env` with your settings:

```env
# System Safety Switches
SYSTEM_GATE_ACTIVE=true              # Set to false only when ready for live dispatch
SANDBOX_MODE=true                    # Routes all test emails to your test address
TEST_RECIPIENT_EMAIL=your_email@gmail.com

# Web UI Authentication
BASIC_AUTH_USERNAME=admin
BASIC_AUTH_PASSWORD=autoadmit_secure_pass_2026

# Google Gemini API
GEMINI_API_KEY=your_actual_gemini_api_key_here
GEMINI_MODEL=gemini-1.5-flash

# Outbound Email (SMTP)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_gmail_app_password
SENDER_NAME="Your Full Name"
SENDER_EMAIL=your_email@gmail.com
CV_PATH=./data/cv.pdf

# Inbound Response Tracking (IMAP)
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USERNAME=your_email@gmail.com
IMAP_PASSWORD=your_gmail_app_password

# Public URL for Tracking Pixel (Localhost or Cloudflare tunnel URL)
TRACKING_BASE_URL=http://localhost:8000
```

---

### Step 3: Run Automated Verification Tests

Verify that all subsystems, safety gates, and guardrails pass:

```bash
# Run complete test suite (P1 through P6)
pytest -v
```

Expected output:
```text
tests/integration/test_p1_discovery.py::test_p1_feasibility_scoring_tiers PASSED
tests/integration/test_p1_discovery.py::test_p1_pre_run_cost_gate_locking PASSED
tests/integration/test_p2_scraper.py::test_p2_email_deobfuscation PASSED
tests/integration/test_p2_scraper.py::test_p2_domain_whitelist_and_anti_redirection PASSED
tests/integration/test_p2_scraper.py::test_p2_supervisor_qualification_filtering PASSED
tests/integration/test_p3_storage.py::test_p3_deduplication_key_generation PASSED
tests/integration/test_p3_storage.py::test_p3_content_hash_integrity PASSED
tests/integration/test_p4_llm_agent.py::test_p4_research_digest_and_gpa_compensation PASSED
tests/integration/test_p4_llm_agent.py::test_p4_guardrail_validator_rejection PASSED
tests/integration/test_p5_safety.py::test_p5_master_kill_switch_gate_1 PASSED
tests/integration/test_p5_safety.py::test_p5_human_approval_gate_3 PASSED
tests/integration/test_p5_safety.py::test_p5_sandbox_mode_gate_2 PASSED
tests/integration/test_p6_tracking.py::test_p6_tracking_pixel_endpoint PASSED
tests/integration/test_p6_tracking.py::test_p6_imap_inbound_reply_header_matching PASSED

============================= 14 passed in 3.28s ==============================
```

---

### Step 4: Start the AutoAdmit Engine Server

Launch the FastAPI application with Uvicorn:

```bash
uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload
```

---

### Step 5: Access the Web Dashboard

1. Open your browser and navigate to: **`http://localhost:8000`**
2. When prompted by your browser for credentials, enter:
   * **Username:** `admin` (or the value set in `BASIC_AUTH_USERNAME`)
   * **Password:** `autoadmit_secure_pass_2026` (or the value set in `BASIC_AUTH_PASSWORD`)

---

## Step-by-Step Campaign Workflow (Using the Dashboard)

### Tab 1: Campaign Setup & Pre-Run Cost Gate
1. Paste official `.edu.cn` department directory URLs (e.g. `http://cs.tsinghua.edu.cn/faculty`, `http://ai.pku.edu.cn/supervisors`).
2. Click **"Calculate Pre-Run Cost Estimate"**.
3. Review estimated pages, faculty count, and Gemini token requirements.
4. Click **"Approve & Start Discovery"** to unlock the crawler gate.

### Tab 2: University Feasibility & Scholarship Directory
* Browse accredited Chinese universities categorized by **Tier 1 (Dream)**, **Tier 2 (Target)**, and **Tier 3 (Safety)**.
* Check scholarship mappings (CSC Type B, Provincial, Presidential) and application fee barriers (0 vs 800 RMB).

### Tab 3: Verified Faculty Roster
* View discovered faculty filtered for verified graduate supervisory credentials (`博导` or `硕导`).
* Inspect de-obfuscated email addresses, research keywords, and SHA-256 audit hashes.

### Tab 4: Split-Pane Email Review Workspace
1. Select a draft from the dropdown menu (initial status: `PENDING_REVIEW`).
2. Inspect the synthesized 2–3 sentence faculty research digest on the left.
3. Edit the customized cold email subject line and body text on the right (real-time word counter enforces <200 words).
4. Click **"Approve for Dispatch"** to stage the draft for sending, or **"Regenerate with Gemini"** to produce a new angle.

### Tab 5: Outbox Dispatcher & Scheduler
1. Check the live China Standard Time (CST) operational clock.
2. Ensure drafts in the queue are in `APPROVED` status.
3. Click **"Dry-Run Test Batch"** to test dispatch logic without touching external mail servers.
4. Click **"Dispatch Batch (With Jitter)"** to send approved messages with 90–240s randomized pauses.

### Tab 6: Analytics & Response Tracker
* Monitor real-time delivery rates, pixel open counts, and reply latency.
* Click **"Poll IMAP Inbox Now"** to scan for inbound responses matching sent message threads.

### Tab 7: Terminal & Live WebSocket Logs
* Monitor real-time logs streamed from background workers (`ScraperWorker`, `Normalizer`, `LLMAgent`, `SMTPEngine`, `IMAPHarvester`).

---

## Remote Access & Mobile Tunneling (Cloudflare Tunnels)

To manage campaigns from your phone or access a remote VPS/Colab instance without opening router ports:

```bash
# Expose the local FastAPI port via Cloudflare Tunnel
cloudflared tunnel --url http://localhost:8000
```

Cloudflare will output a public HTTPS URL (e.g., `https://random-subdomain.trycloudflare.com`). Open this URL on your mobile browser; HTTP Basic Auth protects the application from search engines and unauthorized access.

---

## Project Structure & Architecture Reference

```text
d:\Sch\
├── .specify/
│   └── memory/constitution.md    # Supreme repository principles & rules
├── specs/
│   └── 001-autoadmit-engine/
│       ├── spec.md               # User Stories (P1-P7) & Functional Requirements
│       ├── plan.md               # Architecture, Tech Stack & Complexity Plan
│       ├── tasks.md              # 41 Actionable Implementation Tasks
│       ├── data-model.md         # Data Schemas & Relationships
│       ├── quickstart.md         # Deployment & Setup Reference
│       └── implementation.md     # Verification & Implementation Report
├── src/
│   ├── config.py                 # Typed configuration & safety switches
│   ├── main.py                   # FastAPI application & lifecycle
│   ├── core/
│   │   ├── database.py           # MongoDB connection & compound unique indexes
│   │   ├── security.py           # Basic Auth / Bearer Token verification
│   │   └── logger.py             # Rotating file logging & WebSocket broadcaster
│   ├── models/
│   │   ├── university.py         # University & Feasibility models
│   │   ├── professor.py          # FacultyProfile & Qualification models
│   │   ├── draft.py              # OutreachDraft & Approval models
│   │   └── telemetry.py          # TrackingHit & InboundReply models
│   ├── services/
│   │   ├── discovery.py          # Feasibility scoring & Pre-run cost gate
│   │   ├── scraper.py            # Grounded harvester (httpx + Playwright)
│   │   ├── normalizer.py         # Email de-obfuscation & SHA-256 content hashing
│   │   ├── llm_agent.py          # Gemini 1.5 factual digest & outreach generator
│   │   ├── change_stream.py      # MongoDB Change Stream event reactor
│   │   ├── smtp_engine.py        # Outbound SMTP with 3 safety gates & jitter
│   │   ├── imap_engine.py        # Inbound reply tracking & thread matcher
│   │   └── tracker.py            # 1x1 transparent tracking pixel service
│   ├── api/
│   │   ├── deps.py               # Dependency injection
│   │   ├── routes_discovery.py   # Intake, Feasibility & Cost gate routes
│   │   ├── routes_professors.py  # Faculty roster query & harvest routes
│   │   ├── routes_drafts.py      # Review workspace & edit routes
│   │   ├── routes_dispatch.py    # Outbox & CST scheduler routes
│   │   ├── routes_tracking.py    # Tracking pixel & analytics routes
│   │   └── routes_system.py      # System health, safety toggles & WebSocket logs
│   └── static/
│       ├── index.html            # 7-Tab Responsive Single-Page Application
│       ├── css/style.css         # Modern Dark Theme Styling
│       └── js/app.js             # Reactive SPA State & WebSocket Client
├── tests/
│   ├── conftest.py               # Test client & basic auth fixtures
│   ├── fixtures/sample_pages/    # HTML fixtures for supervisors & lecturers
│   └── integration/
│       ├── test_p1_discovery.py  # P1: Cost gate locking & feasibility scoring
│       ├── test_p2_scraper.py    # P2: Scraper, supervisor filter & de-obfuscation
│       ├── test_p3_storage.py    # P3: Persistence & deduplication
│       ├── test_p4_llm_agent.py  # P4: Gemini synthesis & GPA compensation
│       ├── test_p5_safety.py     # P5: Master Kill-Switch & safety gates
│       └── test_p6_tracking.py   # P6: Pixel tracking & IMAP reply poller
├── .env.example                  # Environment template
├── PRD.md                        # Master Product Requirement Document
├── rules.md                      # Operational & Safety Rules
└── requirements.txt              # Python package dependencies
```

---

## License & Operational Compliance

This repository is governed by the rules set forth in [.specify/memory/constitution.md](file:///d:/Sch/.specify/memory/constitution.md) and [rules.md](file:///d:/Sch/rules.md):
- Real emails MUST NOT be dispatched without explicit human sign-off (`APPROVED` status).
- All crawls are strictly restricted to official university domains (`.edu.cn`).
- No fabricated real-world data is permitted.
