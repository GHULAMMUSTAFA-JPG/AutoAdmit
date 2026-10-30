---
id: "024"
title: "Live Wikidata SPARQL Integration and UI Refresh Bug Fix"
stage: "refactor"
date: "2026-10-30"
surface: "agent"
model: "gemini-3.8-flash"
feature: "001-autoadmit-engine"
branch: "001-autoadmit-engine"
user: "parep"
command: "search gave 69 records instant, refresh looks like dead button, chengdu university of technology returned 0"
labels: ["refactor", "bugfix", "wikidata", "live-query", "sparql", "discovery", "ui-refresh"]
links:
  spec: "specs/001-autoadmit-engine/spec.md"
  ticket: null
  adr: "history/adr/0001-multi-source-discovery-verification.md"
  pr: null
files:
  - "src/services/discovery.py"
  - "src/api/routes_discovery.py"
  - "src/static/js/app.js"
  - "src/static/index.html"
tests:
  - "tests/integration/test_p1_discovery.py"
  - "tests/integration/test_p2_scraper.py"
---

## Prompt

now as i haev told you to remova all mock data and sample data everything has to be live so whats happening i clicked the searched and it gave me in a instant the 69 records and then when i clicked on refresh it looks like dead button and also i tried single uni think i gave name Chengdu University Of Technology and in a instant progress 100% means none and 0 accredeted even though the uni exists

## Response snapshot

1. Root Cause Analysis:
   - `filter_universities` was filtering the in-memory static catalog of 69 universities from `chinese_universities.json` instead of querying the live Wikidata SPARQL endpoint. That is why blank searches instantly returned the 69 records, and searching for "Chengdu University of Technology" returned 0 records because it was not in that static file.
   - The "↻ Refresh Feed" button called `loadAllData()` without visual active states or triggering the active search.
2. Fix Implemented:
   - Implemented `fetch_live_universities_from_wikidata` in `src/services/discovery.py` executing live SPARQL queries to `query.wikidata.org/sparql` with User-Agent header and dynamic filters.
   - Tested live query for "Chengdu University of Technology" (成都理工大学) -> returned `cdut.edu.cn` with Tier 3 Safety.
   - Updated `filter_universities_endpoint` in `src/api/routes_discovery.py` to persist live discovered institutions directly to MongoDB.
   - Updated `refreshActiveProgress()` in `app.js` and `index.html` to provide active button loading feedback and re-execute live filters.
3. Tests: All 14 integration tests passing.

## Outcome

- ✅ Impact: Complete elimination of static 69-catalog filtering; discovery is 100% dynamic and live from Wikidata open data.
- 🧪 Tests: 14/14 integration tests passing (21.61s).
- 📁 Files: `src/services/discovery.py`, `src/api/routes_discovery.py`, `src/static/js/app.js`, `src/static/index.html`.
- 🔁 Next prompts: Continue monitoring subagent audits.

## Evaluation notes (flywheel)

- Failure modes observed: None
- Graders run and results (PASS/FAIL): PASS
- Prompt variant: default
- Next experiment: N/A

