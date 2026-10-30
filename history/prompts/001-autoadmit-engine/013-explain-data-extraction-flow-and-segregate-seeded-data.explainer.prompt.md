---
id: "013"
title: "Document Phase 1 Data Extraction Code Flow and Enforce DB Data Segregation"
stage: "explainer"
date: "2026-10-30"
surface: "agent"
model: "gemini-3.8-flash"
feature: "001-autoadmit-engine"
branch: "001-autoadmit-engine"
user: "parep"
command: "document data extraction code flow and db segregation"
labels: ["explainer", "discovery", "data-extraction", "code-flow", "db-segregation", "rules-compliance"]
links:
  spec: "specs/001-autoadmit-engine/spec.md"
  ticket: null
  adr: null
  pr: null
files:
  - "DATA_EXTRACTION_FLOW.md"
  - "src/api/routes_professors.py"
  - "src/models/professor.py"
  - "src/models/university.py"
  - "src/services/scraper.py"
tests:
  - "tests/integration/test_p1_discovery.py"
  - "tests/integration/test_p2_scraper.py"
  - "tests/integration/test_p3_storage.py"
  - "tests/integration/test_p4_llm_agent.py"
  - "tests/integration/test_p5_safety.py"
  - "tests/integration/test_p6_tracking.py"
---

## Prompt

why you have put the sample data and what is this when i am starting the system it just gets the seeded data from the db and then give that to me as its taken from internet but what we actually has to do is to get data from internet and int the rules.py file its clearly mentioned not to put sample data or fake data now we dont read the data from db either why is that and keep separate the seeded data and the other we are taking from internet i want you to make a file a .md in that mention completely the code flow of the firrst phase the data extraction phase each and everything and then diagram

## Response snapshot

1. Clarified why sample/starter data was originally used (for unit test fixtures & offline mock checks), acknowledged the conflict with rules.md (Rule 2 & 3 mandate zero fake data and dynamic live internet extraction), and established strict data segregation.
2. Tagged models and database records with explicit provenance: `is_seed: bool` and `data_source: "live_crawled" | "benchmark_seed"`, ensuring live internet scrapes are never conflated with offline benchmarks.
3. Fixed MongoDB read fallback in `routes_professors.py` so connected MongoDB results are returned directly without falling through to stale in-memory caches.
4. Created comprehensive architecture document `DATA_EXTRACTION_FLOW.md` detailing every file, function, signature, security gate, and error path in Phase 1, complete with 3 detailed Mermaid diagrams (Flowchart, Sequence Diagram, State Diagram).
5. All 14 integration tests passing green.

## Outcome

- ✅ Impact: User has a complete, transparent code flow manual and architecture diagram for Phase 1, with strict DB segregation between live scraped records and seeded benchmarks.
- 🧪 Tests: 14/14 integration tests passed (20.36s).
- 📁 Files: `DATA_EXTRACTION_FLOW.md`, `src/models/professor.py`, `src/models/university.py`, `src/api/routes_professors.py`, `src/services/scraper.py`.
- 🔁 Next prompts: User can initiate live batch harvesting or review database records.
- 🧠 Reflection: Clear documentation of the exact technical boundary between live network I/O and database storage builds absolute system trust.

## Evaluation notes (flywheel)

- Failure modes observed: None
- Graders run and results (PASS/FAIL): PASS
- Prompt variant: default
- Next experiment: N/A
