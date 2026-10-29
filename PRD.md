# Product Requirement Document (PRD)

## Project Title

**AutoAdmit Engine: Intelligent Multi-Tier Academic Discovery, Feasibility Analysis, & High-Conversion Outreach Platform**

---

## 1. System Vision & Foundational Directives

The **AutoAdmit Engine** is an end-to-end, multi-country graduate admission discovery, empirical profile assessment, and cold-outreach automation platform.

The primary operational target is securing supervisor acceptance letters and full funding under the **Chinese Government Scholarship (CSC Type B), Provincial Government Scholarships, and University Presidential Scholarships** for a Master's degree in Artificial Intelligence / Computer Science. The platform objectively compensates for strict academic cutoffs (such as a 2.68 CGPA) by prioritizing engineering credentials, applied AI projects, and high-alignment research synthesis.

The system is designed to run locally, on an affordable Linux VPS, or headless inside **Google Colab Pro** with background compute, exposed securely over mobile-friendly tunnels via Nginx and Cloudflare.

---

## 2. Technology Stack & Component Responsibilities

| Subsystem | Selected Technology | Primary Role & Responsibility |
| --- | --- | --- |
| **Backend & Process Gateway** | **FastAPI + Gunicorn / Uvicorn** | Coordinates routing, API endpoints, WebSocket log streaming, and manages native Python asynchronous background tasks without external queue brokers (no Redis required). |
| **Web UI Dashboard** | **Modern Single-Page App (SPA)** | UI for discovery configuration, pre-run cost approvals, supervisor review, draft modifications, and dispatch scheduling. |
| **Edge Proxy & Tunneling** | **Nginx + Cloudflare Tunnel (`cloudflared`)** | Reverse-proxies the application on port 80/443, enforces security headers, and provides a free, encrypted, public HTTPS URL for full mobile management. |
| **Authentication & Gatekeeping** | **HTTP Basic Auth / Bearer JWT** | Restricts UI, API, and WebSocket endpoints to prevent public, bot, or search engine access. |
| **Fast-Tier Data Harvester** | **Python `httpx` (Async)** | Performs fast, lightweight, direct HTTP extraction of static HTML from official university pages in milliseconds. |
| **Dynamic Harvester (Fallback)** | **Playwright (Python Async)** | Headless Chromium engine reserved strictly for JavaScript-heavy, client-rendered tables, or pagination patterns. |
| **Intelligence & Synthesis Agent** | **Gemini 1.5 Flash / Pro API** | Extracts structured entities from raw academic HTML, generates 2–3 sentence faculty research digests, and drafts contextualized outreach emails. |
| **Primary Data Store** | **MongoDB Community Server** | NoSQL document database chosen for polymorphic schemas, nested publication lists, and arbitrary faculty table variations across universities. |
| **Event Reactor** | **MongoDB Change Streams** | Natively reacts to document insertions and updates, immediately triggering LLM drafting workflows upon supervisor verification. |
| **Persistence Manager** | **Persistent Volume Mount** | Redirects MongoDB data paths (`/data/db`), environment files, and rotated logs to a persistent drive (Google Drive mount path `/content/drive/...` or VPS block volume). |
| **Outbound Email Engine** | **Python `smtplib` + SSL/TLS** | Direct SMTP transport for dispatching approved emails with dynamic delays, scheduling windows, and PDF CV attachments. |
| **Inbound Tracking & Response Harvester** | **Python `imaplib` / Async IMAP** | Continuously monitors the applicant's inbox for professor replies by cross-referencing message headers (`In-Reply-To`, `References`). |
| **Open Tracking Service** | **FastAPI Tracking Endpoint** | Serves an invisible 1x1 GIF tracking pixel to log read receipts, first-opened timestamps, and view counts. |
| **System Audit Engine** | **Python `logging` (Rotating File Handlers)** | Writes timestamped, worker-specific trace logs to isolated files on disk for monitoring, audit trails, and UI streaming. |

---

## 3. Detailed Functional Modules & Requirements

### Module 1: System Security, Storage Persistence & Remote Access

* **Edge Routing & Tunneling:**
* Nginx runs as a local reverse proxy forwarding incoming requests to the internal FastAPI server (`127.0.0.1:8000`).
* Cloudflare Tunnel (`cloudflared`) creates a secure, publicly accessible HTTPS domain without open router ports or static public IPs.


* **Authentication Guard:**
* All HTTP requests and WebSocket streams require authentication via HTTP Basic Auth or Bearer tokens.
* Unauthenticated requests are rejected immediately (`401 Unauthorized`), preventing unauthorized outbound emails or data manipulation.


* **Persistent Storage Mount:**
* MongoDB engine configurations map database storage paths explicitly to a persistent disk (e.g., mounted Google Drive directory under `/content/drive/MyDrive/AutoAdmit_Data/db` when running on Colab Pro, or `/var/lib/mongodb` on Linux).
* System resumes uninterrupted across runtime restarts, notebook disconnects, or server reboots without data loss.



---

### Module 2: Discovery Configuration & Cost Gate

* **Dual Input Configuration:**
* *Option A (Direct Pre-Seeded Intake):* The user uploads or pastes a curated CSV/JSON payload of university URLs and specific department endpoints (e.g., School of Computer Science, School of Artificial Intelligence, School of Software).
* *Option B (Dynamic Global Discovery):* Dropdown selection of Target Country (China, USA, Germany, Italy, Russia) and Discipline (AI, CS, Software Engineering).


* **Pre-Run Cost & Workload Estimator:**
* Before launching network scrapers or making LLM API calls, the system calculates:
1. Total target faculty directories detected.
2. Estimated pages to fetch and parse.
3. Estimated Gemini API token consumption.
4. Expected runtime and network footprints.


* **Hard Confirmation Gate:** The extraction sequence remains locked in a pending state until the user reviews and clicks "Approve & Start" via the UI.



---

### Module 3: University Feasibility & Scholarship Intelligence

* **Multi-Scholarship Mapping Matrix:**
* Chinese Government Scholarship (CSC Type B: Full tuition waiver + accommodation + monthly stipend).
* Provincial Government Scholarships (e.g., Shanghai, Zhejiang, Jasmine: Full or partial support).
* University Presidential / Chancellor Scholarships (Often offer flexible admission standards).
* Belt and Road / Silk Road Program Grants.


* **Application Barrier Tracking:**
* Identifies whether the target university requires a non-refundable application fee (e.g., 400–800 RMB) or charges zero application fee.


* **Empirical Feasibility Scoring (2.68 CGPA Compensation Engine):**
* Evaluates institutional competitiveness against profile realities:
* **Tier 1 (Dream):** Top C9 / Project 985 institutions. Strict academic screening. Feasibility engine automatically sets outreach focus toward younger Associate Professors or newly established labs requiring hands-on engineering output.
* **Tier 2 (Target):** Project 211 / Major Provincial Engineering hubs. Flexible GPA evaluation when supported by strong technical portfolios, biometric verification projects, and GenAI implementations.
* **Tier 3 (Safety):** Accredited institutions with high international student acceptance quotas and accessible scholarship minimums.





---

### Module 4: Faculty Scraper Pool & Verification Gate

* **Strict Source Lockdown (Anti-Hallucination Domain Whitelist):**
* Crawlers are restricted strictly to official university subdomains (`.edu.cn` or accredited institutional domains). Outbound redirects and third-party aggregator portals are blocked.


* **Supervisory Qualification Filter:**
* Extracts only faculty explicitly marked with Master's or Ph.D. supervisory credentials:
* Required verification markers: `硕士生导师` (Master's Supervisor), `硕导`, `博士生导师` (Ph.D. Supervisor), `博导`.
* Automatically drops administrative staff, undergraduate lecturers, and postdocs without graduate supervision rights.




* **Dual-Tier Dynamic Fetching:**
* *Fast Tier (`httpx`):* Concurrently retrieves raw static HTML.
* *Fallback Tier (`Playwright`):* Initiates an isolated, headless Chromium context only if the page utilizes client-side rendering or dynamic pagination.


* **Extracted Schema:**
* Full Name (both Native script and Romanized/English).
* Institutional Email (with de-obfuscation for `[at]`, `(at)`, and spaced characters).
* Department, Research Center, and Laboratory Name.
* Primary Research Areas and Specialization Keywords.
* 2 to 3 Recent Publication Titles with years.
* Direct source profile URL.


* **Worker Lineage & Fault Isolation:**
* Concurrent pool of 10 to 30 asynchronous workers.
* If a profile parsing fails, the system logs the incident, tags the record as `EXTRACTION_FAILED`, and moves to the next profile without interrupting the batch.



---

### Module 5: Data Normalization, Audit Trail & Change Streams

* **Normalization Rules:**
* Deduplication enforced via unique compound constraints (`email` and `name + university`).
* Standardizes diverse departmental naming variations into uniform tags (`CS_AI_SE`).


* **Level 1 Extraction Audit:**
* Every saved document includes:
* `source_url`: Verifiable URL of the faculty profile.
* `scraped_at`: Timestamp.
* `worker_id`: Identifier of the worker process that performed the extraction.
* `content_hash`: Cryptographic hash (SHA-256) of raw page content to detect future changes or re-scrapes.




* **Reactive MongoDB Change Streams:**
* Listens natively for inserts into the `professors` collection.
* Instantly triggers the Gemini LLM Drafting Agent worker asynchronously without requiring polling loops.



---

### Module 6: Gemini LLM Research Synthesis & Email Drafting Agent

* **Sub-Task A: Factual Research Digest:**
* Gemini processes extracted publications and research interests to generate a 2-to-3 sentence research digest:
1. The core theoretical or engineering problem the lab is actively solving.
2. Primary algorithms, architectures, or frameworks in use.




* **Sub-Task B: Contextualized Cold Outreach Generation:**
* Synthesizes applicant background against the professor's research digest.
* **Drafting Rules:**
* **GPA Compensation:** Highlights technical strengths (Python, PyTorch, Agentic AI, biometrics, deployed systems) and avoids drawing focus to the 2.68 CGPA.
* **Financial Independence:** Explicitly confirms the applicant is applying for external full funding (CSC / Provincial / Presidential scholarships), reassuring the professor that no lab stipend or financial support is required.
* **Structure:** Under 200 words, compelling custom subject line, clear problem alignment, and a call-to-action requesting a brief introductory meeting or review of attached credentials.


* Sets draft document status to `PENDING_REVIEW`.



---

### Module 7: Review Workspace, Tracking & Outbound Safety Engine

* **Review Interface:**
* Split-pane UI displaying extracted profile details, research summary, and an inline editor for the generated subject line and body text.


* **Multi-Layer Outbound Safety Gates:**
* **Gate 1: Master Kill-Switch (`SYSTEM_GATE_ACTIVE = True`):**
* Global toggle that blocks all outbound network socket connections to the SMTP server.


* **Gate 2: Sandbox / Test Mode:**
* Overrides recipient fields, routing all outbound test messages to the applicant's personal email with full diagnostic metadata headers.


* **Gate 3: Explicit Human Approval:**
* The SMTP worker query strictly limits its queue to `status == "APPROVED"`. Records with `DRAFTED`, `PENDING_REVIEW`, or `REJECTED` are ignored by the sender.




* **Dispatch Modes & Smart Scheduling:**
* **Send Modes:** Single Send, Selected Batch Send, or All Approved Queue.
* **Operational Time Window:** Restricts sending to target working hours (09:00 – 16:30 China Standard Time / CST).
* **Rate Limiting:** Enforces caps (max 8–10 emails/hour, max 25 emails/day).
* **Jitter Control:** Applies randomized pauses between 90 and 240 seconds between successive sends.
* **Automated Attachments:** Attaches academic CV (PDF) and portfolio references.


* **Level 2 Outreach Tracking & Audit:**
* **Open Tracking Engine:**
* Embeds an invisible 1x1 tracking pixel: `<img src="https://<domain>/api/v1/track/open/{draft_id}" width="1" height="1" alt="" />`.
* Logs `first_opened_at`, `last_opened_at`, and `open_count` inside the campaign record.


* **Inbound IMAP Response Polling:**
* Background worker connects via IMAP over SSL every 15–30 minutes.
* Scans for incoming messages containing matching `In-Reply-To` or `References` headers tied to sent messages.
* Automatically updates status from `SENT` to `REPLIED`, records reply latency, and alerts the UI.





---

## 4. Phase-by-Phase Verification & Test Matrix

| Phase | Test Type | Execution Criteria & Expected Result |
| --- | --- | --- |
| **P1: Discovery & Config** | Unit / Gate Test | Pass valid and invalid department URLs; verify schema validation and confirm execution halts until the Pre-Run Cost Gate is explicitly approved. |
| **P2: Scraping & Extraction** | Integration Test (Dry Run) | Run 1 worker against 5 sample department URLs; verify complete field population, de-obfuscation of malformed emails, and supervisor qualification detection. |
| **P3: Persistence & Storage** | Resilience Test | Insert 10 documents, disconnect the runtime or restart FastAPI, and verify all records, hashes, and log files persist intact across restarts. |
| **P4: Gemini AI Synthesis** | Quality & Guardrail Test | Test prompts against 3 distinct research domains; verify drafts stay under 200 words, exclude GPA references, highlight applied engineering, and set status to `PENDING_REVIEW`. |
| **P5: Safety & Dispatch** | Security Gate Test | Enable the Master Kill-Switch and trigger a send. Verify the application returns a `403 Forbidden` error with zero outbound SMTP traffic. |
| **P6: Tracking & Inbound** | Telemetry Test | Send a test email to your own inbox. Open the email to verify the tracking pixel fires, then reply to the thread and confirm the IMAP poller updates the database status to `REPLIED`. |

---

## 5. UI Dashboard Specification

1. **Top Navigation & Safety Bar:**
* Global toggles for **Master Kill-Switch (ACTIVE/INACTIVE)** and **Sandbox Test Mode (ON/OFF)**.
* System health status, Google Drive / volume mount indicator, and CST live clock.


2. **Tab 1: Campaign Setup & Resource Estimation:**
* Controls for Pre-seeded list upload or Country/Field selectors.
* Feasibility profile input (CGPA, primary technical skills, CV upload).
* Pre-Run Cost Estimation breakdown with "Approve & Execute" button.


3. **Tab 2: University & Feasibility Directory:**
* Interactive table showing University Name, Location, CS Rank, Scholarships Available, Application Fee Requirements, and Feasibility Tier (Dream, Target, Safety).


4. **Tab 3: Faculty Roster & Extraction Stream:**
* Live list of discovered supervisors with qualification status badges, research keywords, and extraction source URLs.


5. **Tab 4: Email Review & Approval Staging:**
* Split-pane workspace: Professor profile and synthesized research digest on the left; editable email subject line and body on the right.
* Action buttons: "Approve for Dispatch", "Discard", and "Regenerate Draft".


6. **Tab 5: Outbox Dispatcher & Delivery Scheduler:**
* Visual queue of approved drafts.
* Sending mode selectors (Single, Batch, All Approved).
* Configuration for daily sending limits, hourly caps, and CST operational hours.
* Real-time progress bar with live delivery statuses.


7. **Tab 6: Analytics & Response Tracker:**
* Metrics display: Total Sent, Delivered (250 OK), Opened Count (Pixel), Responses Received, Average Reply Time.
* Thread viewer displaying inbound replies detected by the IMAP poller.


8. **Tab 7: System Terminal & Live Log Streaming:**
* Real-time WebSocket terminal displaying log feeds filtered by module (`Scraper`, `Normalizer`, `LLM_Agent`, `SMTP`, `IMAP`).