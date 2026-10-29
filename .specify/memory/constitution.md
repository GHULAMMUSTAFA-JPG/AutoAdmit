<!-- Sync Impact Report
Version change: [CONSTITUTION_VERSION] -> 1.0.0
List of modified principles:
  - PRINCIPLE_1: PRD & Architectural Strict Compliance
  - PRINCIPLE_2: Grounded Data & Zero Fabrication (Anti-Hallucination)
  - PRINCIPLE_3: Multi-Layer Outbound Email Safety & Master Kill-Switch
  - PRINCIPLE_4: Worker Fault Isolation & Async Non-Blocking Resilience
  - PRINCIPLE_5: Cryptographic Lineage, Auditability & Persistent Storage
  - PRINCIPLE_6: Test-First & Guardrail Verification (Phases P1-P6)
Added sections:
  - Operational Constraints & CST Work Windows
  - GPA Compensation & Synthesis Guardrails
  - Technology Stack Baseline & Prohibitions
Removed sections:
  - Generic template placeholder sections
Templates requiring updates:
  - .specify/templates/plan-template.md: ✅ aligned
  - .specify/templates/spec-template.md: ✅ aligned
  - .specify/templates/tasks-template.md: ✅ aligned
Follow-up TODOs: None
-->

# AutoAdmit Engine Constitution

## Core Principles

### I. PRD & Architectural Strict Compliance
The system MUST adhere strictly to the architecture, component roles, data schemas, and workflows specified in `PRD.md` and `rules.md`. No unapproved technology substitutions are permitted. Specifically:
- FastAPI handles API routing, WebSocket log streaming, and native Python asynchronous background tasks without external queue brokers (Redis is explicitly forbidden).
- MongoDB Community Server is the primary polymorphic document store and event reactor (using native Change Streams).
- The scraping tier MUST follow the dual-tier architecture: fast-tier asynchronous `httpx` for static HTML, falling back to headless async `Playwright` strictly when client-side rendering or dynamic pagination is detected.

### II. Grounded Data & Zero Fabrication (Anti-Hallucination)
Never invent, fabricate, or extrapolate real-world institutional or faculty data.
- University and faculty data MUST originate strictly from official university websites and verified `.edu.cn` (or accredited institutional) subdomains. Crawlers MUST reject third-party aggregators and redirects to untrusted domains.
- Supervisory qualifications MUST be verified against explicit academic titles (`硕士生导师`, `硕导`, `博士生导师`, `博导`). Faculty records lacking verified graduate supervisory qualifications MUST be dropped.
- Mock data is strictly confined to `tests/fixtures/` and must never pollute production databases or runtime logs.

### III. Multi-Layer Outbound Email Safety & Master Kill-Switch
Outreach dispatch MUST be guarded by fail-safe, defense-in-depth safety gates:
1. **Gate 1 - Master Kill-Switch (`SYSTEM_GATE_ACTIVE = True`):** When active, all network socket connections to outbound SMTP transports MUST be physically aborted immediately with `403 Forbidden`.
2. **Gate 2 - Sandbox Test Mode:** When sandbox mode is active, recipient addresses MUST be rewritten exclusively to `TEST_RECIPIENT_EMAIL` with full diagnostic headers.
3. **Gate 3 - Explicit Human Approval:** The SMTP worker queue MUST query only records with `status == "APPROVED"`. Records with `DRAFTED`, `PENDING_REVIEW`, or `REJECTED` MUST NEVER be dispatched.
4. **Controlled Actions:** Under no circumstances shall real outbound emails or large-scale scraping campaigns be initiated without explicit, conscious user authorization.

### IV. Worker Fault Isolation & Async Non-Blocking Resilience
All I/O operations (HTTP fetching, database queries, file writing, LLM generation, SMTP transmission, IMAP polling) MUST be fully asynchronous and non-blocking.
- The failure of an individual scraping worker, parser, or synthesis task MUST be isolated. Failed records must be tagged `EXTRACTION_FAILED` with detailed error telemetry in the audit log, allowing batch execution to continue without interruption.
- Background tasks MUST utilize native Python asyncio event loops without blocking worker threads.

### V. Cryptographic Lineage, Auditability & Persistent Storage
Every ingested profile and outreach artifact MUST maintain cryptographic auditability:
- Every scraped document MUST store `source_url`, UTC `scraped_at`, `worker_id`, and a SHA-256 `content_hash` of the raw source content.
- Deduplication MUST be enforced at the database level via compound unique indexes (e.g., `email` and `name + university`).
- Persistent storage for MongoDB data (`DB_STORAGE_PATH`) and system log streams (`LOG_DIR`) MUST point to persistent mounted volumes (e.g., Google Drive `/content/drive/...` or VPS block volume), guaranteeing complete continuity across server reboots and notebook reconnections.

### VI. Test-First & Guardrail Verification (Phases P1-P6)
Every subsystem MUST be covered by automated test suites validating the PRD Phase Verification Matrix:
- **Phase P1 (Discovery & Config):** Valid/invalid URL schema parsing and Pre-Run Cost Gate enforcement.
- **Phase P2 (Scraping & Extraction):** Qualification filters, email de-obfuscation, and fault isolation.
- **Phase P3 (Persistence & Resilience):** Data retention across connection drops and simulated process crashes.
- **Phase P4 (AI Synthesis & Guardrails):** <200 words, strict avoidance of GPA references, empirical engineering highlighting, status locking to `PENDING_REVIEW`.
- **Phase P5 (Outbound Safety):** Verification that Master Kill-Switch blocks all outbound SMTP sockets.
- **Phase P6 (Tracking & Inbound):** Invisible 1x1 tracking pixel telemetry and IMAP `In-Reply-To`/`References` thread matching.

## Operational Constraints & Outreach Protocols

### CST Operational Window & Jitter Control
To mirror authentic human communication and safeguard sender reputation:
- Email dispatch MUST only run during target business hours: **09:00 - 16:30 China Standard Time (CST)**.
- Rate limiting MUST enforce a maximum of 8-10 emails per hour and at most 25 emails per day.
- A randomized jitter pause of 90 to 240 seconds MUST be inserted between successive email dispatches.

### Profile Synthesis & GPA Compensation Directives
- Outreach generation MUST actively compensate for the applicant's 2.68 CGPA cutoff by spotlighting production engineering capabilities, PyTorch models, Agentic AI, biometric verification systems, and applied research.
- Outreach drafts MUST explicitly state that the applicant is seeking independent full scholarship funding (CSC Type B / Presidential / Provincial), eliminating any financial burden on the faculty lab.
- Outreach drafts MUST remain under 200 words, concise, respectful, and feature a direct call-to-action requesting an introductory video meeting or review of attached CV/portfolio materials.

## Governance & Compliance

1. **Constitutional Authority:** This Constitution constitutes the supreme technical law for the AutoAdmit Engine repository. It supersedes informal instructions, ad-hoc changes, or unverified feature expansions.
2. **Amendment Protocol:** Any amendment to this document requires explicit justification, a version bump following semantic versioning, and immediate synchronization across all active feature specs, plans, and task templates.
3. **Execution Review:** Before merging any code or initiating any system release, automated checks and human review MUST certify 100% adherence to all core principles and safety gates.

**Version**: 1.0.0 | **Ratified**: 2026-10-30 | **Last Amended**: 2026-10-30
