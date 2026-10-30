---
id: "025"
title: "Clean Phase 1 Live Discovery, Obliterate Static Seed Data, and Clarify Sandbox Modes"
stage: "refactor"
date_iso: "2026-10-31"
surface: "agent"
model: "gemini-2.5-pro"
feature: "001-autoadmit-engine"
branch: "001-autoadmit-engine"
user: "User"
command: "/sp.tasks"
labels: ["phase1", "discovery", "wikidata", "zero-mock", "sandbox", "audit"]
links:
  spec: "specs/001-autoadmit-engine/spec.md"
  ticket: null
  adr: "history/adr/0002-multi-source-discovery-and-truthfulness-pipeline.md"
  pr: null
files_yaml:
  - "src/services/discovery.py"
  - "src/api/routes_discovery.py"
  - "src/static/index.html"
  - "src/static/css/style.css"
  - "src/static/js/app.js"
tests_yaml:
  - "tests/integration/test_p1_discovery.py"
  - "tests/integration/test_p2_scraper.py"
  - "tests/integration/test_p3_storage.py"
  - "tests/integration/test_p4_llm_agent.py"
  - "tests/integration/test_p5_safety.py"
  - "tests/integration/test_p6_tracking.py"
  - "tests/test_audit_db_ws_system.py"
---

### Prompt Text
why dont you remove that json file or clean it, so you see there is an issue which i caught in the Target Regions (Provinces / Municipalities): dropdown every value has list of unis and when i selected sichuan it gave me 3 names and wit all tier so we have a issue here we have added limits and boundries to our system man which you are ignoring everytime and what is sandbox on and off everytime we are running into the same shit the unis the i weant to clean the whole flow whole flow of phase 1 wach and everything and i will verifyy that so far not even once phase 1 has ran like it was supposed to

### Key Decisions & Actions
1. **Obliterated Static Seed File:** Permanently deleted `src/data/chinese_universities.json` and all local copies. Removed `_load_universities_catalog()` and `KNOWN_UNIVERSITIES_METADATA` completely from codebase.
2. **Fixed Regional & University Search:** Replaced literal name matching with multi-keyword geographical alias mapping (`PROVINCE_LOCATION_KEYWORDS`). Searching Sichuan now dynamically discovers all 29+ accredited universities in the province (including Chengdu University of Technology, UESTC, Sichuan University, SWJTU), rather than 3.
3. **Cleaned Target Regions Dropdown:** Removed hardcoded university parentheticals from the region dropdown options in the enterprise UI.
4. **Resolved Sandbox Clarification:** Documented and explained the difference between AutoAdmit's outbound SMTP Sandbox Gate (application-level safety lock against accidental live professor email delivery) versus local OS socket/process sandboxing.
5. **Phase 1 Pipeline Audit & Test Verification:** Audited end-to-end extraction flow (Wikidata live discovery -> department endpoints -> crawler -> MongoDB persistence). All 19 integration tests pass cleanly (100% green).

