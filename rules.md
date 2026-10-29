# RULES.md

1. **PRD Compliance:** Follow `PRD.md` architecture, technology stack, schemas, and workflows without unapproved changes.
2. **No Fabricated Data:** Never invent real-world data; keep mock data isolated in `tests/fixtures/`.
3. **University Discovery:** Discover universities dynamically, verify their official websites, and crawl faculty and scholarship information only from verified university domains and authorized subdomains. Reject redirects to unrelated or unverified domains.
4. **Email Safety:** Check `SYSTEM_GATE_ACTIVE` before SMTP initialization; dispatch only `APPROVED` drafts and require explicit human approval.
5. **Sandbox Mode:** When enabled, route all emails exclusively to `TEST_RECIPIENT_EMAIL`.
6. **Data Integrity:** Store `source_url`, UTC `scraped_at`, `worker_id`, and SHA-256 `content_hash`; enforce MongoDB deduplication indexes.
7. **Persistence:** Use configurable `DB_STORAGE_PATH` and `LOG_DIR` for persistent data and logs.
8. **Async and Resilience:** Use non-blocking I/O, isolate task failures, log errors, and continue processing.
9. **Security:** Authenticate API and WebSocket endpoints; load secrets from environment variables or an uncommitted `.env` file.
10. **Testing:** Build, run, and debug the application; write and execute tests and fix failures.
11. **Controlled Actions:** Do not send real emails or launch large-scale live scraping without explicit user authorization.
12. **Completion Report:** Summarize implemented features, test results, and unresolved issues.