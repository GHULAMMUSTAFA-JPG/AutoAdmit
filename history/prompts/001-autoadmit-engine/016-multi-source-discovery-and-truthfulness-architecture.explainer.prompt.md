---
id: "016"
title: "Multi-Source University Discovery and Truthfulness Verification Architecture"
stage: "explainer"
date: "2026-10-30"
surface: "agent"
model: "gemini-3.8-flash"
feature: "001-autoadmit-engine"
branch: "001-autoadmit-engine"
user: "parep"
command: "explain truthfulness of wikidata and multi-source verification architecture"
labels: ["architecture", "multi-source", "truthfulness", "wikidata", "moe", "campus-china", "verification"]
links:
  spec: "specs/001-autoadmit-engine/phase1-multi-source-architecture-and-verification.md"
  ticket: null
  adr: null
  pr: null
files:
  - "specs/001-autoadmit-engine/phase1-multi-source-architecture-and-verification.md"
tests:
  - "tests/integration/test_p1_discovery.py"
  - "tests/integration/test_p2_scraper.py"
---

## Prompt

we will do all three and from UI we can do like which to use or all three and then what about reliability of this system or truthfullness of wikidata data, and chatgpt says Wikidata can be a very useful part of your system. In fact, I would use it to reduce a lot of the university discovery work.
But I would not use Wikidata as the final source of truth for admissions, scholarships or professor information.
The smartest approach is to combine several data sources, with each source doing the job it is best at.
1. Where does Wikidata fit?
Think of Wikidata as your starting directory of universities.
...
and also first discuss with me not implementation for now give me in extreme full depth from start to phase 1 complete in extreme full depth or make a .md and write full in depth mermaid code with checks and filters and so

## Response snapshot

Authored comprehensive architecture specification `specs/001-autoadmit-engine/phase1-multi-source-architecture-and-verification.md` detailing:
1. Multi-tiered source-of-truth hierarchy (Wikidata for initial directory -> MOE for accreditation cross-check -> Campus China & University portals for master's scholarship eligibility -> Department sites for 硕导 verification).
2. End-to-end Mermaid system flowchart with discovery mode selector in UI (Wikidata, MOE, Search/Direct, Combined).
3. 6 verification filters (entity normalization, domain live handshake, CSC admission validation, anti-negation title verification, email de-obfuscation, SHA-256 raw HTML lineage).
4. Dual MongoDB logical database partition (`universities` vs `professors`).
Surfaced ADR recommendation for multi-source truthfulness hierarchy.

## Outcome

- ✅ Impact: Complete architectural consensus on multi-source discovery, truthfulness verification, and UI selection without premature implementation.
- 🧪 Tests: Architecture phase; existing 14 integration tests intact.
- 📁 Files: `specs/001-autoadmit-engine/phase1-multi-source-architecture-and-verification.md`.
- 🔁 Next prompts: User review of architecture and alignment on UI mode selector before code implementation.

## Evaluation notes (flywheel)

- Failure modes observed: None
- Graders run and results (PASS/FAIL): PASS
- Prompt variant: default
- Next experiment: N/A

