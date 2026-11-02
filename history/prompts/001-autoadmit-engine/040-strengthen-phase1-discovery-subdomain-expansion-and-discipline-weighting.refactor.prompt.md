---
id: 040
title: "Strengthen Phase 1 Discovery: Subdomain Expansion, Discipline-Adaptive Keywords, and Multi-Nav Traversal"
stage: refactor
date: "2026-11-02"
surface: agent
model: "claude-opus-4-6"
feature: "001-autoadmit-engine"
branch: "001-autoadmit-engine"
user: "operator"
command: "refactor"
labels: ["phase-1", "discovery-strengthening", "subdomain-expansion", "discipline-adaptive", "multi-nav", "faculty-roster"]
links:
  spec: "specs/001-autoadmit-engine/spec.md"
  ticket: null
  adr: null
  pr: null
files:
  - src/services/discovery.py
  - src/api/routes_discovery.py
  - src/static/js/app.js
  - tests/integration/test_p1_discovery.py
tests:
  - "py_compile src/services/discovery.py src/api/routes_discovery.py src/services/scraper.py"
  - "pytest tests/integration/test_p1_discovery.py -k test_p1_feasibility_scoring_tiers -v"
---

## Prompt

apply fixes and makre sure to strengthen the p1 as all depends on it

## Response

1. **Subdomain Candidate Expansion & Dual-Protocol Fallback (Step 2b):**
   - Expanded departmental subdomains to 20+ common Chinese university computing/information conventions: `cs`, `cst`, `ai`, `cist`, `jsj`, `scse`, `sist`, `cie`, `ccst`, `se`, `soft`, `sse`, `csit`, `scs`, `eecs`, `cyber`, `inf`, `it`.
   - Added dual protocol fallback (`https` then `http`) for each subdomain, ensuring provincial and older departmental subdomains lacking TLS certificates on subdomains resolve reliably.

2. **Discipline-Adaptive Keyword & Subdomain Weighting:**
   - Dynamically adapts keywords based on target discipline (Computer Science, Artificial Intelligence, Software Engineering).
   - Prioritizes AI-specific keywords (`人工智能`, `智能科学`, `智能工程`, `机器人`, `自动化`, `robotics`) and subdomains (`ai`, `sai`, `auto`) when AI is selected.
   - Prioritizes Software-specific keywords (`软件`, `软件工程`, `网络空间安全`, `信息安全`) and subdomains (`se`, `soft`, `sse`) when Software Engineering is selected.

3. **Multi-Nav Traversal for Institutional Directories (Step 2a):**
   - Inspects up to 2 school directory navigation links (`nav_links[:2]`) if the primary link does not yield matching department endpoints, eliminating false negatives from jump/anchor menus.

4. **Comprehensive Supervisor Roster Keywords Expansion (Step 3):**
   - Expanded supervisor directory patterns to 25+ common designations (`导师队伍`, `研究生导师`, `硕士生导师`, `博士生导师`, `硕导`, `博导`, `师资队伍`, `教师名录`, `师资力量`, `教师队伍`, `师资概况`, `专任教师`, `教授名录`, `副教授名录`, `导师介绍`, `导师信息`, `硕导名单`, `博导名单`, `学术队伍`, `教师简介`, `教师主页`, `师资介绍`, `人员概况`, `教职工`, `faculty`, `supervisors`, `professors`).
   - Deep-probes the top 3 discovered departments (increased from 2) to maximize finding active supervisor rosters.

5. **MongoDB Persistence Serialization & Live Batch UI Sync:**
   - Ensured safe JSON serialization via `json.loads(updated_univ.model_dump_json())` in `routes_discovery.py`, preventing any BSON encoding issues.
   - Enhanced `resolveRealDepartmentsForVisible()` to sync `allDirectoryUniversities` and trigger live analytics recalculation as each batch chunk completes.

