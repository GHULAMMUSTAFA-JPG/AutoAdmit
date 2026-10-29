# Data Model: AutoAdmit Engine

## Entity Relationship Overview

```
[University]
   │ 1
   │
   ▼ N
[FacultyProfile] (Verified Supervisors only)
   │ 1
   │
   ▼ 1..N
[OutreachDraft] (Status: PENDING_REVIEW -> APPROVED -> SENT -> REPLIED)
   │ 1
   │
   ├──► [CampaignTelemetry] (Tracking pixel opens, deliverability)
   │
   └──► [InboundReply] (IMAP harvested response headers)
```

---

## Collections & Schemas

### 1. `universities`
- `id`: string (UUID or canonical slug, e.g., `tsinghua-university`)
- `name`: string (e.g., `Tsinghua University`)
- `chinese_name`: string (e.g., `清华大学`)
- `domain`: string (e.g., `tsinghua.edu.cn`)
- `tier`: string (`Tier 1 (Dream)`, `Tier 2 (Target)`, `Tier 3 (Safety)`)
- `cs_ranking`: integer
- `project_985`: boolean
- `project_211`: boolean
- `scholarships_available`: list of strings (`CSC Type B`, `Beijing Municipal`, `Presidential`)
- `application_fee_rmb`: integer (0 for free, or 400-800 RMB)
- `target_departments`: list of objects (`name`, `url`)
- `feasibility_strategy`: string (e.g., `Focus on younger Associate Professors / new labs`)
- `created_at`: datetime (UTC)

### 2. `professors`
- `id`: string (UUID)
- `name`: string (English / Pinyin)
- `native_name`: string (Chinese characters)
- `email`: string (canonical lowercase, de-obfuscated)
- `university`: string
- `department`: string
- `lab_name`: string
- `qualification`: string (`博导`, `硕导`, `博士生导师`, `硕士生导师`)
- `is_supervisor`: boolean (must be `True`)
- `research_areas`: list of strings
- `recent_publications`: list of objects (`title`, `year`, `venue`)
- `source_url`: string
- `content_hash`: string (SHA-256 of raw scraped profile)
- `worker_id`: string
- `scraped_at`: datetime (UTC)
- `extraction_status`: string (`VERIFIED`, `EXTRACTION_FAILED`)
- `dedup_key`: string (unique index: `email`, compound index: `name` + `university`)

### 3. `outreach_drafts`
- `id`: string (UUID)
- `professor_id`: string (ref to `professors.id`)
- `recipient_email`: string
- `recipient_name`: string
- `university`: string
- `research_digest`: string (2-3 sentences from Gemini 1.5)
- `subject_line`: string
- `body_text`: string (plain text <200 words)
- `body_html`: string (HTML formatted with embedded tracking pixel)
- `status`: string (`DRAFTED`, `PENDING_REVIEW`, `APPROVED`, `REJECTED`, `QUEUED`, `SENT`, `REPLIED`)
- `rejection_reason`: optional string
- `scheduled_at`: optional datetime (UTC)
- `sent_at`: optional datetime (UTC)
- `message_id`: optional string (RFC 2822 Message-ID)
- `tracking_token`: string (unique UUID for 1x1 pixel)
- `created_at`: datetime (UTC)
- `updated_at`: datetime (UTC)

### 4. `telemetry`
- `id`: string (UUID)
- `draft_id`: string (ref to `outreach_drafts.id`)
- `tracking_token`: string
- `first_opened_at`: optional datetime (UTC)
- `last_opened_at`: optional datetime (UTC)
- `open_count`: integer (default 0)
- `smtp_response_code`: optional integer (e.g., 250)
- `delivery_latency_ms`: optional integer

### 5. `inbound_replies`
- `id`: string (UUID)
- `draft_id`: string (ref to `outreach_drafts.id`)
- `message_id`: string
- `in_reply_to`: string
- `references`: list of strings
- `from_email`: string
- `subject`: string
- `snippet`: string
- `received_at`: datetime (UTC)
- `reply_latency_hours`: float
