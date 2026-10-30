---
id: "011"
title: "Remove Hardcoded Applicant Academic Objective Card"
stage: "refactor"
date: "2026-10-30"
surface: "agent"
model: "gemini-3.8-flash"
feature: "001-autoadmit-engine"
branch: "001-autoadmit-engine"
user: "parep"
command: "remove applicant academic objective card"
labels: ["refactor", "ui-cleanup", "discovery", "generalization"]
links:
  spec: "specs/001-autoadmit-engine/spec.md"
  ticket: null
  adr: null
  pr: null
files:
  - "src/static/index.html"
  - "src/services/llm_agent.py"
tests:
  - "tests/integration/test_p1_discovery.py"
  - "tests/integration/test_p2_scraper.py"
  - "tests/integration/test_p3_storage.py"
  - "tests/integration/test_p4_llm_agent.py"
  - "tests/integration/test_p5_safety.py"
  - "tests/integration/test_p6_tracking.py"
---

## Prompt

on same page we have this Applicant Academic Objective:
Target Degree: Master's in CS / AI
Faculty Target: Master's Supervisors (硕士生导师 / 硕导)
Technical Strengths: PyTorch, Agentic AI, Biometrics, Deployed Systems
Scholarship Goal: CSC Type B / University Presidential Scholarship, why  goal and technical strengths are irrelevant this system is just finding data organizing and then so on i will also apply to CSC or any other like ansu or belt and road all scholorship but i dont know why you are adding useless thing to system so make sure its not there and why is it there in the first place this section why does it exist Applicant Academic Objective:
Target Degree: Master's in CS so first explain me and not very lengthy

## Response snapshot

1. Explained concisely why the section was originally placed there: PRD.md previously assumed a single persona with fixed technical skills (PyTorch, biometrics) and fixed scholarship targets, which was displayed as a static summary card.
2. Agreed with the user: this system is a data gathering and discovery pipeline, and hardcoded assumptions are unnecessary clutter.
3. Completely removed the 'Applicant Academic Objective' section from Tab 1, leaving a clean, two-column form for Region selection, Tier/Rank filter, and Academic Discipline.
4. Generalized LLM agent prompts to support any scholarship (CSC, ANSO, Presidential, Belt & Road, etc.) without hardcoding specific niches.
5. All 14 integration tests passing green.

## Outcome

- ✅ Impact: UI is decluttered and streamlined; no irrelevant static profile assumptions remain.
- 🧪 Tests: 14/14 integration tests passed.
- 📁 Files: `src/static/index.html`, `src/services/llm_agent.py`.
- 🔁 Next prompts: Continue with data discovery, harvesting, or queue workflows.
- 🧠 Reflection: Keeping configuration inputs strictly focused on what drives data discovery and crawler filtering creates a cleaner user experience.

## Evaluation notes (flywheel)

- Failure modes observed: None
- Graders run and results (PASS/FAIL): PASS
- Prompt variant: default
- Next experiment: N/A
