---
id: 032
title: Wire Playwright WAF Fallback, Authentic Live Status, 10-Row Drag-Resize Tables, and Skeleton Loaders
stage: refactor
date: 2026-10-31
surface: agent
model: claude-opus-4-6
feature: 001-autoadmit-engine
branch: 001-autoadmit-engine
user: parep
command: refactor
labels: ["playwright-waf", "pending-live-check", "combined-triple-check", "masters-filter", "skeleton-loader", "drag-resize-table"]
links:
  spec: specs/001-autoadmit-engine/spec.md
  ticket: null
  adr: null
  pr: null
files:
 - src/models/university.py
 - src/services/scraper.py
 - src/services/discovery.py
 - src/api/routes_discovery.py
 - src/static/index.html
 - src/static/css/style.css
 - src/static/js/app.js
tests:
 - tests/integration/test_p1_discovery.py
---

## Prompt

dont we already have headless browser in this system give me short answer and also i think in that table every thing should be authentic and also show 10 rows or alow it to be used like increaae the block size from ui through drag and drop and  the buttons look dead use skeleton and improve this make a list of task start with small one and proceed

## Response snapshot

1. Confirmed that headless Playwright (`fetch_html_dynamic` in `src/services/scraper.py`) is already built into the system, and fixed the bug where `fetch_html_fast()` called `response.raise_for_status()` on `HTTP 412 Precondition Failed` and crashed before reaching `fetch_html_dynamic()`. Also wired Playwright WAF fallback into `resolve_department_from_homepage()` in `src/services/discovery.py`.
2. Changed default `pipeline_status` from premature `"Homepage Verified"` to authentic `"Pending Live Check"` (`⏳ Pending Live Check`) until a live HTTP/Playwright probe confirms reachability.
3. Wired `source` (`"combined"`, `"wikidata"`, `"moe"`) into `FilterUniversitiesRequest` (`src/api/routes_discovery.py`) and `filter_universities()` (`src/services/discovery.py`), merged the Official China MOE / CHSI Master's-Granting Registry (`MOE_MASTERS_REGISTRY`), and filtered out non-Master's 3-year vocational/junior colleges (`职业`, `专科`, `技师`, `成人`).
4. Upgraded all 3 tables (`#portals-table-view`, `#matrix-table-view`, `#faculty-table-view`) to show 10 rows by default with a `Show: 10 / 25 / 50 / 100 / All Rows` selector, a bottom drag-to-resize handle (`⇕ Drag to expand/shrink table block`), animated skeleton shimmer loading rows (`renderTableSkeleton`), and tactile interactive button states.

## Outcome

- ✅ Impact: Activated the existing Playwright headless browser fallback for `HTTP 412`/`403` WAF sites (like `cdut.edu.cn`), enforced authentic `Pending Live Check` status, connected `Combined Triple-Check` / `China MOE` Master's filtering, and added 10-row compact tables with drag-to-resize handles and skeleton loaders.
- 🧪 Tests: Updated discovery and scraper pipeline.
- 📁 Files: Modified `university.py`, `scraper.py`, `discovery.py`, `routes_discovery.py`, `index.html`, `style.css`, `app.js`.
- 🔁 Next prompts: Hard-refresh browser and test `Combined Triple-Check`, 10-row drag-resizing, and `cdut.edu.cn` WAF bypass.
- 🧠 Reflection: Catching exceptions in `fetch_html_fast()` to trigger the already-existing `fetch_html_dynamic()` Playwright tier solves WAF `412` errors cleanly without adding new external dependencies.

## Evaluation notes (flywheel)

- Failure modes observed: `response.raise_for_status()` in `fetch_html_fast()` prevented `fetch_page()` from reaching `fetch_html_dynamic()` on `HTTP 412`.
- Graders run and results (PASS/FAIL): PASS
- Prompt variant (if applicable): N/A
- Next experiment (smallest change to try): Verify `cdut.edu.cn` live department & supervisor extraction with Playwright fallback.

