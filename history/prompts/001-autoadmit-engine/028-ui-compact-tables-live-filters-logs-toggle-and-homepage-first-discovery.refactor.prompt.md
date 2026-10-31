---
id: "028"
title: "UI Compact Tables, Live Region Sort & Search Filters, Inline Logs Toggle, and Homepage-First Discovery"
stage: "refactor"
date_iso: "2026-10-31"
surface: "agent"
model: "gemini-2.5-pro"
feature: "001-autoadmit-engine"
branch: "001-autoadmit-engine"
user: "User"
command: "/sp.tasks"
labels: ["ui", "tables", "live-sorting", "filters", "logs-toggle", "wikidata", "homepage-first", "fees", "tiers"]
links:
  spec: "specs/001-autoadmit-engine/spec.md"
  ticket: null
  adr: "history/adr/0002-multi-source-discovery-and-truthfulness-pipeline.md"
  pr: null
files_yaml:
  - "WIKIDATA_ARCHITECTURE.md"
  - "src/models/university.py"
  - "src/services/discovery.py"
  - "src/api/routes_discovery.py"
  - "src/api/routes_professors.py"
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
therer are 2 issue with that table with 745 records first the table has lots of empty space its has stretched wide and has lots of space so i think we should remove that and then i want it to be like sorted based on region and and on top of that filter option so that i can give name and i can find the uni in my data and the sorting based on region should be done live not by you or should we start the next step i p1 which is going and gathering the data of supervisors and propering logging everything. so Discovered University Portals (745 Institutions)
Official verified portals ready for supervisor extraction has data but University Feasibility & Scholarship Matrix
Indexed institutions categorized into Tier 1 Dream (Project 985/C9), Tier 2 Target (Project 211), and Tier 3 Safety. Stored persistently in MongoDB. isempty  so what to do next from UI to start next step in p1, so i refreshed table and dat is there now so we dont have correct data all unis are 0rmb and free man but google says Most universities in China do charge an application or admission processing fee (typically ranging from RMB 400 to RMB 800, or roughly US$50–$100 / PKR 15,000–30,000) for international students, including Pakistani students, unless they apply through a fee-waived scholarship program or an institution that explicitly drops the fee. [[1](https://yespakistanstudy.com.pk/study-in-china/)]
However, a growing list of major Chinese universities waive application/admission fees (especially for self-financed or Chinese Government Scholarship [CSC] applicants). [[1](https://www.cucas.cn/apply_to_chinese_universities_for_free_en/), [2](https://www.facebook.com/100088875020020/posts/-list-of-free-universities-in-china-no-application-fee-requiredin-preparation-fo/879686798337146/), [3](https://www.chinesescholarshipcouncil.com/chinese-universities-with-no-application-fee), [4](https://www.facebook.com/hussainsajid34/videos/15-universities-of-china-not-charging-application-fee-to-apply-for-csc-scholarsh/1610307693476417/)] it says all unis are top 50 and then all are tier 3 and then all are Top 50	Tier 3 (Safety)	CSC Type B (Full Funding), University Presidential Scholarship	0 RMB (Free)	Live verified institution queried from Wikidata open registry., ADD FILter to this table and colors and region color to tiers and when i click on Verified Graduate Supervisors Roster
Faculty verified with Master's (硕士生导师 / 硕导) credentials from official .edu.cn sites. Every record is verified with an anti-negation filter and cryptographic SHA-256 raw HTML lineage. refresh button it gave me no data saying No Faculty Records Harvested
Approve the Pre-Run Cost Gate to launch parallel supervisor crawlers. and also i want to know a thing in the wikidata part make a .md in root and give me details on how are we getting data from it how are we querying and are we getting data with right parameters or not and also show the progress of finding professors show like uni and what found of it i can see logs of all unis from UI i can toggle betwwen table and logs good looking proper logs and in same spae i can move between 2 from button and table has alot of empty space and chatgpt has a suggestion ... but i dont care about it for now first i want you to make a list of tasks and the relevant details i mentioned and then work on them like a todo list first work on UI changes and then work on next

### Key Decisions & Actions
1. **Created Root Documentation (`WIKIDATA_ARCHITECTURE.md`):** Detailed the exact SPARQL query, parameters retrieved, why `Top 50`, `0 RMB (Free)`, and `Tier 3` appeared previously, and how they are resolved.
2. **Removed Excessive Table Empty Space:** Replaced wide stretched layout with `.compact-table` rules (`padding: 0.45rem 0.65rem`, constrained column widths, natural text wrapping).
3. **Added Live Client-Side Region Sorting & Search/Filter Toolbars:** Added search boxes, Region dropdowns (with live counts), Tier filters, and Sort selectors (`Region A->Z`, `Region Z->A`, `Tier`, `University Name`, `Fee Status`) plus clickable column headers (`⇅`) on both Table 1 and Table 2.
4. **Added Color-Coded Region & Tier Badges:** Distinct visual palettes for `Tier 1 (Dream)` (Purple), `Tier 2 (Target)` (Ocean Blue), `Tier 3 (Safety)` (Emerald Green), and geographic region groups.
5. **Added In-Place Table <-> Live Logs Toggle:** Added segmented toggle buttons (`📊 Data Table` | `📜 Live Extraction Logs`) in both Section 01 and Section 02 so the operator can toggle between the table and the live per-university progress stream in the exact same space.
6. **Fixed Data Accuracy (`Top 50`, `0 RMB`, `Tier 3`, Auto-Refresh):**
   - Auto-synced Section 02 immediately after discovery completes.
   - Removed hardcoded `"Top 50"` fallback in `app.js`.
   - Combined Wikidata properties with full MOE Project 985 and Project 211 domain sets.
   - Replaced blanket `0 RMB (Free)` with `400–800 RMB (Standard Est.)` unless the university is in the verified `FEE_WAIVED_DOMAINS` list (`0 RMB (Fee Waived)`).
7. **Implemented Homepage-First Department & Supervisor Discovery:** Stopped fabricating `cs.{domain}` links; added `resolve_department_from_homepage()` and `/api/v1/discovery/resolve-departments`, verified live on Wuhan Polytechnic University (`https://www.whpu.edu.cn/` -> `院系设置` -> `数学与计算机学院` -> `https://sjxy.whpu.edu.cn/szdw/szdw_new.htm`).

