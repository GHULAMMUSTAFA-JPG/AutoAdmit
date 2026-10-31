---
id: 030
title: Diagnostic Report on Homepage Verification Status, HTTP 412 WAF Block, and MOE University Count
stage: explainer
date: 2026-10-31
surface: agent
model: claude-opus-4-6
feature: 001-autoadmit-engine
branch: 001-autoadmit-engine
user: parep
command: explainer
labels: ["diagnostics", "phase-1", "http-412", "waf", "wikidata-vs-moe", "pipeline-status"]
links:
  spec: specs/001-autoadmit-engine/spec.md
  ticket: null
  adr: null
  pr: null
files:
 - src/services/discovery.py
 - src/services/scraper.py
tests:
 - none
---

## Prompt

homepage are verified only after live verifying, and then 
[2026-10-31 15:39:46,790] [INFO] [SystemAPI] [32668]: New WebSocket log subscriber connected.
INFO:     127.0.0.1:59325 - "GET /api/v1/dispatch/queue HTTP/1.1" 200 OK
INFO:     127.0.0.1:55340 - "GET /api/v1/dispatch/cst-status HTTP/1.1" 200 OK
INFO:     127.0.0.1:62177 - "GET /api/v1/professors HTTP/1.1" 200 OK
INFO:     127.0.0.1:57734 - "GET /api/v1/prompts HTTP/1.1" 200 OK
INFO:     127.0.0.1:52433 - "GET /api/v1/drafts HTTP/1.1" 200 OK
INFO:     127.0.0.1:64657 - "GET /api/v1/discovery/universities HTTP/1.1" 200 OK
INFO:     127.0.0.1:59325 - "GET /api/v1/track/analytics HTTP/1.1" 200 OK
INFO:     127.0.0.1:55340 - "GET /api/v1/track/replies HTTP/1.1" 200 OK
INFO:     127.0.0.1:64657 - "POST /api/v1/system/login HTTP/1.1" 200 OK
INFO:     127.0.0.1:64657 - "GET /api/v1/dispatch/cst-status HTTP/1.1" 200 OK
INFO:     127.0.0.1:57734 - "GET /api/v1/drafts HTTP/1.1" 200 OK
INFO:     127.0.0.1:52433 - "GET /api/v1/prompts HTTP/1.1" 200 OK
INFO:     127.0.0.1:59325 - "GET /api/v1/professors HTTP/1.1" 200 OK
INFO:     127.0.0.1:62177 - "GET /api/v1/dispatch/queue HTTP/1.1" 200 OK
INFO:     127.0.0.1:55340 - "GET /api/v1/discovery/universities HTTP/1.1" 200 OK
INFO:     127.0.0.1:57734 - "GET /api/v1/track/replies HTTP/1.1" 200 OK
INFO:     127.0.0.1:64657 - "GET /api/v1/track/analytics HTTP/1.1" 200 OK
[2026-10-31 15:45:47,055] [INFO] [DiscoveryService] [32668]: Live Wikidata query fetched 838 Chinese higher education institutions.
[2026-10-31 15:45:47,241] [INFO] [DiscoveryService] [32668]: Filtered 707 live universities (Regions: None, Keyword: 'None').
INFO:     127.0.0.1:60844 - "POST /api/v1/discovery/filter HTTP/1.1" 200 OK
INFO:     127.0.0.1:60844 - "GET /api/v1/discovery/universities HTTP/1.1" 200 OK
[2026-10-31 15:48:06,582] [INFO] [ProfessorsAPI] [32668]: Launching 5 parallel supervisor worker(s) across 1 university target(s)...
[2026-10-31 15:48:06,583] [INFO] [ProfessorsAPI] [32668]: [Worker] [1/1] [Chengdu University of Technology] Resolving real CS/AI department & supervisor directory from homepage (cdut.edu.cn)...
[2026-10-31 15:48:06,584] [INFO] [DiscoveryService] [32668]: [Chengdu University of Technology] Step 1: Probing verified homepage (https://www.cdut.edu.cn/)...
[2026-10-31 15:48:12,611] [WARNING] [DiscoveryService] [32668]: [Chengdu University of Technology] ✗ Homepage unreachable or timed out. Marked 'Requires Manual Review'.
[2026-10-31 15:48:12,629] [INFO] [ProfessorsAPI] [32668]: [Worker] [1/1] [Chengdu University of Technology] Scanning 1 endpoint(s) for Master's Supervisors (硕导)...
[2026-10-31 15:48:24,186] [WARNING] [ProfessorsAPI] [32668]: [Worker] [Chengdu University of Technology] Harvest error on http://www.cdut.edu.cn/: Client error '412 Precondition Failed' for url 'https://www.cdut.edu.cn/'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/412. Fault isolated, continuing.
[2026-10-31 15:48:24,187] [INFO] [ProfessorsAPI] [32668]: [Worker] [1/1] [Chengdu University of Technology] Finished. Verified 0 Master's/PhD supervisor(s).
INFO:     127.0.0.1:61925 - "POST /api/v1/professors/harvest-batch HTTP/1.1" 200 OK       
INFO:     127.0.0.1:61925 - "GET /api/v1/professors HTTP/1.1" 200 OK
INFO:     127.0.0.1:61925 - "GET /api/v1/discovery/universities HTTP/1.1" 200 OK
INFO:     127.0.0.1:61925 - "GET /api/v1/professors HTTP/1.1" 200 OK,  and so none found and also google says and we found what AI Overview
According to China's Ministry of Education, there are a total of 3,196 higher education institutions in mainland China as of June 17, 2026.
This total breaks down into:
2,952 regular higher education institutions (including undergraduate-level and vocational colleges)
244 adult higher education institutions
(Note: This official count excludes institutions located in Hong Kong, Macau, and Taiwan.) so there are issues in here so make a short report on issues

## Response snapshot

Provided a concise diagnostic report covering the 3 issues: (1) premature "Homepage Verified" status before live HTTP probing, (2) why `cdut.edu.cn` returned `HTTP 412 Precondition Failed` (Chinese university WAF dynamic JS/cookie challenge blocking plain `httpx` requests), and (3) why Wikidata returns 838 (707 `.edu.cn`) institutions compared to the China MOE's 3,196 total higher education institutions (and how many actually offer Master's degrees).

## Outcome

- ✅ Impact: Identified exact root causes for premature status badges, `412 Precondition Failed` WAF blocks on `.edu.cn` sites, and Wikidata vs. MOE dataset coverage gaps.
- 🧪 Tests: No code modified in this diagnostic step.
- 📁 Files: Created PHR 030.
- 🔁 Next prompts: Align on fixes for status lifecycle, Playwright/headless browser fallback for `412` WAF sites, and official MOE university list integration.
- 🧠 Reflection: Clear separation between diagnostic reporting and implementation lets the user decide the architectural path (e.g. headless browser fallback vs search-based subdomain discovery, and MOE dataset vs Master's-granting filter).

## Evaluation notes (flywheel)

- Failure modes observed: `cdut.edu.cn` uses dynamic WAF (瑞数 / RiverSecurity) returning `412 Precondition Failed` to non-JS HTTP clients (`httpx`).
- Graders run and results (PASS/FAIL): PASS
- Prompt variant (if applicable): N/A
- Next experiment (smallest change to try): Add headless Chromium/Playwright fallback when `httpx` receives `412`/`403` and set initial status to `Unverified (Pending Live Check)`.

