# Feature Specification: AutoAdmit Engine

**Feature Branch**: `001-autoadmit-engine`  
**Created**: 2026-10-30  
**Status**: Approved  
**Input**: PRD.md and rules.md

---

## User Scenarios & Testing

### User Story 1 - Secure Intake, University Discovery & Pre-Run Cost Gate (Priority: P1 - MVP Core)

As an international graduate applicant with a 2.68 CGPA aiming for CSC Type B and Chinese university scholarships,
I need to upload curated university/department URLs or select target disciplines, evaluate institutional feasibility tiers, and preview resource/token costs before any network or AI resources are consumed,
So that I can strategically target feasible institutions and never incur unexpected API or crawling costs without explicit authorization.

**Why this priority**: Without verified entry points and hard pre-run cost approvals, crawlers could scrape arbitrary targets or burn LLM API budgets unchecked.

**Independent Test**: Provide pre-seeded university lists or choose CS/AI in China; verify feasibility tiering (Dream, Target, Safety) and confirm system remains in a `PENDING_APPROVAL` gate until the user triggers "Approve & Start".

**Acceptance Scenarios**:
1. **Given** a user inputs a CSV of Chinese university department URLs, **When** the pre-run cost estimator processes the payload, **Then** it calculates estimated faculty directories, pages to fetch, estimated Gemini token consumption, and displays an approval modal.
2. **Given** an unapproved discovery run, **When** background scrapers attempt to trigger, **Then** the execution halts and raises a gate block until explicit authorization is received via the API/UI.
3. **Given** an applicant with 2.68 CGPA and strong applied AI projects, **When** universities are analyzed, **Then** Project 985 institutions are tagged as Tier 1 (Dream - targeting younger associate professors), Project 211 as Tier 2 (Target), and high-quota institutions as Tier 3 (Safety).

---

### User Story 2 - Dual-Tier Grounded Faculty Harvester & Supervisor Verification (Priority: P2)

As a candidate applying for graduate research degrees,
I need an automated scraper pool that navigates official `.edu.cn` subdomains, extracts faculty profiles, and filters strictly for verified graduate supervisors (`硕士生导师`/`硕导`, `博士生导师`/`博导`),
So that outreach is directed only to faculty with legal authority to accept and supervise graduate scholarship students.

**Why this priority**: Crawling non-supervisors (administrative staff, postdocs, pure lecturers) wastes outreach quotas and destroys conversion rates.

**Independent Test**: Run scraping workers against sample static and dynamic faculty directory pages; verify fast `httpx` extraction succeeds, dynamic pages fallback seamlessly to `Playwright`, and non-supervisory profiles are filtered out.

**Acceptance Scenarios**:
1. **Given** a faculty directory page containing both lecturers and `博士生导师`, **When** the harvester executes, **Then** only faculty with `博导` or `硕导` credentials are extracted and non-supervisors are dropped.
2. **Given** an obfuscated email such as `prof_name [at] univ (dot) edu (dot) cn`, **When** normalization runs, **Then** it cleanly de-obfuscates the string into `prof_name@univ.edu.cn`.
3. **Given** an official `.edu.cn` webpage that redirects to an unauthorized third-party commercial aggregator, **When** the scraper detects the domain mismatch, **Then** the request is aborted and logged as a security violation.
4. **Given** a network failure on a specific profile URL, **When** the worker encounters the timeout, **Then** it marks the record as `EXTRACTION_FAILED`, logs the trace, and proceeds with the remaining pool without crashing.

---

### User Story 3 - Cryptographic Persistence, Deduplication & Event-Driven Change Streams (Priority: P3)

As a system operator running long-running discovery jobs on VPS or Colab Pro,
I need polymorphic document storage in MongoDB with cryptographic hashes, compound deduplication indexes, and Change Stream triggers,
So that data survives notebook reconnections or server reboots, never duplicates professors, and automatically triggers drafting pipelines.

**Why this priority**: Prevents duplicate records across repeated discovery runs and provides event-driven architecture without external message brokers.

**Independent Test**: Ingest records with identical emails and different names; verify unique constraints trigger deduplication; verify SHA-256 `content_hash` and UTC `scraped_at` are persisted; verify inserting a new professor automatically triggers the Change Stream handler.

**Acceptance Scenarios**:
1. **Given** two faculty records with the same institutional email address, **When** inserted into MongoDB, **Then** deduplication preserves the canonical record and prevents duplicate entries.
2. **Given** persistent storage mapped to `/data/db` or mounted cloud volume, **When** the application daemon restarts, **Then** all previous extractions, drafts, and campaign states reload without data loss.
3. **Given** a newly verified professor is written to the `professors` collection, **When** MongoDB Change Streams detect the `insert` event, **Then** an async drafting task is dispatched to the Gemini synthesis worker.

---

### User Story 4 - Gemini LLM Factual Digest & Strategic GPA Compensation Outreach (Priority: P4)

As an applicant whose CGPA (2.68) does not meet traditional paper-screening thresholds,
I need Gemini 1.5 to synthesize recent publications into an authentic 2-3 sentence research digest and draft a personalized cold email (<200 words) that emphasizes applied AI engineering, systems development, and independent scholarship funding,
So that professors evaluate my hands-on technical merit and know I require no lab stipend.

**Why this priority**: Personalized, concise emails that highlight technical competence and guaranteed external funding dramatically boost reply rates.

**Independent Test**: Execute synthesis on sample faculty publications; inspect generated drafts to verify word count is <200, no mention of the 2.68 CGPA exists, applied AI/PyTorch experience is highlighted, external scholarship independence is confirmed, and draft status is set to `PENDING_REVIEW`.

**Acceptance Scenarios**:
1. **Given** a professor's publications in Computer Vision, **When** Gemini generates the research digest, **Then** it accurately identifies the core problem and primary architectures without hallucinating unmentioned topics.
2. **Given** the candidate profile, **When** the cold outreach email is generated, **Then** it is under 200 words, explicitly states the applicant will apply for CSC/Presidential scholarships (zero lab financial commitment), and emphasizes applied engineering skills.
3. **Given** any generated email draft, **When** written to the database, **Then** its initial status is locked to `PENDING_REVIEW` and cannot be queued for dispatch without human approval.

---

### User Story 5 - Multi-Layer Outbound Safety Engine & CST Smart Scheduling (Priority: P5)

As an applicant safeguarding my academic reputation and email domain deliverability,
I need a multi-layer safety engine featuring a Master Kill-Switch (`SYSTEM_GATE_ACTIVE`), Sandbox Test Mode, strict human approval requirements, and CST business-hour scheduling with randomized jitter,
So that no unauthorized email can ever be dispatched and sent emails emulate authentic human behavior.

**Why this priority**: Uncontrolled bulk sending results in domain blacklisting, spam tagging, or immediate faculty disqualification.

**Independent Test**: Enable `SYSTEM_GATE_ACTIVE` and attempt dispatch; verify immediate `403 Forbidden` and zero SMTP socket traffic. Enable Sandbox Mode; verify emails route only to `TEST_RECIPIENT_EMAIL`. Test batch dispatch; verify randomized jitter (90-240s) and CST working hours enforcement.

**Acceptance Scenarios**:
1. **Given** `SYSTEM_GATE_ACTIVE = True`, **When** any API or background worker attempts to initialize an SMTP connection, **Then** the operation is rejected immediately with `403 Forbidden` and zero network packets leave.
2. **Given** Sandbox Mode is `ON`, **When** an outreach message is dispatched, **Then** the recipient address is overridden with `TEST_RECIPIENT_EMAIL` with debug headers attached.
3. **Given** drafts with statuses `DRAFTED`, `PENDING_REVIEW`, and `APPROVED`, **When** the outbound dispatcher polls for candidate messages, **Then** ONLY drafts with `APPROVED` status are queued.
4. **Given** local system time outside 09:00 - 16:30 CST, **When** automated batch sending is scheduled, **Then** the dispatcher pauses until the next valid CST operational window.

---

### User Story 6 - Invisible Pixel Tracking & Inbound IMAP Response Harvester (Priority: P6)

As an applicant monitoring campaign efficacy,
I need to track email open receipts via an invisible 1x1 tracking pixel and detect incoming professor replies via an asynchronous IMAP monitor matching message headers (`In-Reply-To`, `References`),
So that I receive real-time notifications of replies and accurate analytics on email deliverability and engagement.

**Why this priority**: Automated response tracking eliminates manual inbox checking and immediately flags high-priority professor engagement.

**Independent Test**: Request tracking pixel endpoint for a test draft; verify `first_opened_at`, `last_opened_at`, and `open_count` increment in the database. Send an email with specific `Message-ID`; simulate an IMAP reply matching `In-Reply-To`; verify status updates to `REPLIED`.

**Acceptance Scenarios**:
1. **Given** a sent email with tracking pixel `<img src="/api/v1/track/open/{draft_id}" />`, **When** the recipient client loads images, **Then** the tracking endpoint returns a 1x1 transparent GIF and records timestamp and count.
2. **Given** an incoming email in the applicant's inbox, **When** the IMAP background poller checks headers every 15-30 minutes, **Then** it matches `In-Reply-To` to the sent `Message-ID`, transitions the campaign status to `REPLIED`, and calculates reply latency.

---

### User Story 7 - Unified SPA Dashboard & Live WebSocket Terminal (Priority: P7)

As a candidate managing the entire admission campaign from desktop or mobile,
I need a single-page application dashboard featuring safety toggles, campaign configuration, university feasibility view, split-pane review workspace, dispatch manager, analytics metrics, and real-time WebSocket log streaming,
So that I have full operational visibility and granular control over every aspect of the engine.

**Why this priority**: A unified UI enables seamless mobile/desktop monitoring over Cloudflare tunnels without requiring shell access.

**Independent Test**: Load the SPA dashboard; verify authentication challenge; toggle Master Kill-Switch and Sandbox Mode; review draft in split-pane editor; inspect real-time log terminal streaming via WebSockets.

**Acceptance Scenarios**:
1. **Given** an unauthenticated request to the dashboard or WebSocket endpoint, **When** accessed, **Then** HTTP Basic Auth / Bearer token rejects the request with `401 Unauthorized`.
2. **Given** the split-pane review tab, **When** the user edits the generated email body and clicks "Approve for Dispatch", **Then** the database status updates to `APPROVED` and stages the draft for dispatch.
3. **Given** background scrapers and synthesis workers running, **When** log events are emitted, **Then** the WebSocket terminal streams filtered live logs to the browser.

---

## Edge Cases

- **Domain Redirection:** If a university department link redirects to a non-educational or external third-party domain (e.g. commercial ads or unverified servers), the scraper MUST abort the request immediately.
- **Obfuscated / Anti-Spam Contact Info:** Faculty emails formatted as `[at]`, `(at)`, `&#64;`, spaces, or JavaScript strings must be normalized or flagged if unparseable.
- **Dynamic Content & Anti-Bot Protection:** If static `httpx` returns empty containers or client-side rendering placeholders, fall back to headless `Playwright` with randomized delay.
- **LLM Rate Limits & Quota Exhaustion:** If Gemini API responds with 429 Too Many Requests, apply exponential backoff (up to 3 retries) and isolate failed records with status `DRAFT_FAILED`.
- **Network Interruption During Dispatch:** If SMTP fails during a batch send, the current message remains `APPROVED` (not marked `SENT`), the error is logged, and dispatch pauses to avoid duplicate messages.
- **Multiple Faculty Replies:** If a professor replies multiple times, the IMAP poller updates the latest reply timestamp and appends to the reply thread without corrupting original metrics.

---

## Requirements

### Functional Requirements

- **FR-001**: System MUST provide authenticated API endpoints guarded by HTTP Basic Auth or Bearer tokens for all actions and WebSocket streams.
- **FR-002**: System MUST calculate pre-run cost and workload estimates (pages, faculty count, estimated LLM tokens) and require explicit human approval before launching network harvesters or LLM pipelines.
- **FR-003**: System MUST calculate institutional feasibility scores categorizing universities into Tier 1 (Dream), Tier 2 (Target), and Tier 3 (Safety) with specialized GPA compensation logic.
- **FR-004**: System MUST restrict crawling exclusively to official accredited university domains (`.edu.cn` or equivalent whitelist) and reject unauthorized redirects.
- **FR-005**: System MUST verify supervisory credentials (`硕导`, `博导`, `硕士生导师`, `博士生导师`) and discard unverified faculty profiles.
- **FR-006**: System MUST utilize asynchronous `httpx` for fast static extraction and fall back to async `Playwright` for client-rendered pages.
- **FR-007**: System MUST record `source_url`, UTC `scraped_at`, `worker_id`, and SHA-256 `content_hash` on every extracted faculty record.
- **FR-008**: System MUST enforce database-level deduplication via compound unique indexes on `email` and `name + university`.
- **FR-009**: System MUST persist MongoDB data to a configurable directory (`DB_STORAGE_PATH`) and log files to `LOG_DIR` to support Linux VPS and Google Drive persistent volume mounts.
- **FR-010**: System MUST utilize MongoDB Change Streams to asynchronously trigger LLM drafting workers upon new professor document insertion.
- **FR-011**: System MUST use Gemini 1.5 to synthesize recent publications into a 2-3 sentence factual research digest.
- **FR-012**: System MUST draft personalized cold outreach emails under 200 words, highlighting applied engineering/biometrics/AI, confirming independent external scholarship funding (CSC Type B / Presidential), and omitting GPA references.
- **FR-013**: System MUST initialize all generated drafts with status `PENDING_REVIEW`.
- **FR-014**: System MUST enforce a Master Kill-Switch (`SYSTEM_GATE_ACTIVE = True`) that aborts all outbound SMTP socket connections with `403 Forbidden`.
- **FR-015**: System MUST provide Sandbox Test Mode routing all outbound messages exclusively to `TEST_RECIPIENT_EMAIL`.
- **FR-016**: System MUST restrict dispatch strictly to drafts explicitly marked `APPROVED` by human review.
- **FR-017**: System MUST enforce CST operational dispatch windows (09:00 - 16:30 China Standard Time), hourly rate caps (8-10/hr), daily caps (25/day), and randomized inter-send jitter (90-240 seconds).
- **FR-018**: System MUST support attaching academic CVs (PDF) and portfolio links to outbound outreach emails.
- **FR-019**: System MUST embed an invisible 1x1 tracking pixel to track email open timestamps and open counts.
- **FR-020**: System MUST run an asynchronous IMAP response worker polling inbox messages and matching `In-Reply-To` and `References` headers to sent emails.
- **FR-021**: System MUST transition campaign status to `REPLIED` and record response latency upon matching an inbound reply.
- **FR-022**: System MUST provide a responsive 7-tab Single-Page Application (SPA) dashboard for end-to-end management, review, dispatch, and WebSocket live log streaming.

### Key Entities

- **University**: Represents institutional targets. Attributes: `id`, `name`, `chinese_name`, `domain`, `tier` (Tier 1/2/3), `scholarships_available`, `application_fee_rmb`, `cs_ranking`, `created_at`.
- **FacultyProfile**: Represents verified academic supervisors. Attributes: `id`, `name`, `native_name`, `email`, `university`, `department`, `lab_name`, `qualifications` (Master/PhD supervisor), `research_areas`, `recent_publications`, `source_url`, `content_hash`, `worker_id`, `scraped_at`, `extraction_status`.
- **OutreachDraft**: Represents customized cold outreach emails. Attributes: `id`, `professor_id`, `recipient_email`, `subject_line`, `body_html`, `body_text`, `research_digest`, `status` (`DRAFTED`, `PENDING_REVIEW`, `APPROVED`, `REJECTED`, `QUEUED`, `SENT`, `REPLIED`), `scheduled_for`, `sent_at`, `message_id`, `tracking_id`, `created_at`, `updated_at`.
- **CampaignTelemetry**: Represents delivery and engagement metrics. Attributes: `id`, `draft_id`, `tracking_pixel_hits`, `first_opened_at`, `last_opened_at`, `replied_at`, `reply_latency_hours`, `smtp_response_code`.
- **InboundReply**: Represents received email responses. Attributes: `id`, `draft_id`, `from_email`, `subject`, `snippet`, `received_at`, `in_reply_to_header`.

---

## Success Criteria

- **SC-001**: 100% of outbound SMTP attempts halt when `SYSTEM_GATE_ACTIVE` is enabled.
- **SC-002**: 0% unverified faculty (non-supervisors or unverified domains) are queued for drafting or outreach.
- **SC-003**: 100% of LLM-generated drafts adhere to the <200-word constraint and exclude references to the 2.68 CGPA.
- **SC-004**: Database deduplication prevents 100% of duplicate professor records across repeat batch scans.
- **SC-005**: Complete state persistence across daemon restarts without loss of queued or dispatched campaign states.
- **SC-006**: Open tracking pixel and IMAP reply header matching achieve >95% accuracy in matching outbound to inbound threads.
- **SC-007**: Web dashboard loads within 1.5 seconds on desktop and mobile over Cloudflare tunnel connections.
- **SC-008**: Full passing status across Phase P1 through P6 automated test suites.
