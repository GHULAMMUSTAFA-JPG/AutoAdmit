---
id: "010"
title: "Refine Regional Discovery Flow and Scholarship Outreach Tone"
stage: "refactor"
date: "2026-10-30"
surface: "agent"
model: "gemini-3.8-flash"
feature: "001-autoadmit-engine"
branch: "001-autoadmit-engine"
user: "parep"
command: "refine discovery & scholarship tone"
labels: ["refactor", "discovery", "crawler-architecture", "scholarship-tone", "gemini-tokens"]
links:
  spec: "specs/001-autoadmit-engine/spec.md"
  ticket: null
  adr: null
  pr: null
files:
  - "src/api/routes_discovery.py"
  - "src/api/routes_professors.py"
  - "src/models/university.py"
  - "src/services/discovery.py"
  - "src/services/llm_agent.py"
  - "src/static/index.html"
  - "src/static/js/app.js"
  - "tests/integration/test_p4_llm_agent.py"
  - "README.md"
  - "specs/001-autoadmit-engine/spec.md"
tests:
  - "tests/integration/test_p1_discovery.py"
  - "tests/integration/test_p2_scraper.py"
  - "tests/integration/test_p3_storage.py"
  - "tests/integration/test_p4_llm_agent.py"
  - "tests/integration/test_p5_safety.py"
  - "tests/integration/test_p6_tracking.py"
---

## Prompt

first this is wrong Zero-Cost Financial Independence: It explicitly assures professors that you are applying for independent full scholarships (CSC Type B or Presidential), reassuring them that accepting you requires zero financial stipend from their lab budget. and second which gemini cost are we calculating the system had 2 thing first was direct internet data gathering starting from gathering names of all universities in china and then filtering them based on the rank and region and then when we get the universities then we run parallel processes each process is tasked with a university and that process finds the uni official link navigate to its departments and go into the related departments and and then in their department faculty and from faculty it gathers the data of masters supervisors this is the rough explanation there can be more filters but this is rough explanation

## Response snapshot

1. Refined the outreach communication tone: removed all presumptuous 'zero lab stipend from your budget' phrasing, replacing it with respectful statements expressing direct intention to apply for the Chinese Government Scholarship (CSC Type B) or University Presidential Scholarship under the professor's academic supervision.
2. Clarified the 2-stage discovery vs. LLM token cost breakdown: web scraping across universities and department portals is $0 network I/O; Gemini tokens are only consumed downstream when generating research digests and drafting cold emails for discovered Master's supervisors (硕导).
3. Overhauled Tab 1 with Automated Regional Discovery: introduced dynamic multi-select filtering by Chinese region (Beijing, Shanghai, Jiangsu, Zhejiang, etc.) and tier/rank, automatic resolution of CS/AI department endpoints, and concurrent multi-university harvesting (`POST /api/v1/professors/harvest-batch`).
4. Re-verified test suite: all 14 integration tests passing green.

## Outcome

- ✅ Impact: The system matches the exact regional discovery and supervisor harvesting architecture envisioned, with professional, culturally respectful scholarship inquiry language.
- 🧪 Tests: 14/14 integration tests passed (P1–P6).
- 📁 Files: Updated routes, services, frontend UI/JS, spec, README, and test assertions.
- 🔁 Next prompts: User can trigger regional discovery from the UI or run crawler workers.
- 🧠 Reflection: Clear division between network crawler operations ($0 cost) and LLM synthesis tokens makes the pre-run cost gate intuitive.

## Evaluation notes (flywheel)

- Failure modes observed: None
- Graders run and results (PASS/FAIL): PASS
- Prompt variant: default
- Next experiment: Add real-time progress bar tracking for parallel university worker completion.

