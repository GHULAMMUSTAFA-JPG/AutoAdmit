---
id: 046
title: "Table 2 Redesign Hide Fees 3 Row Links Table 1 Minimize and Header Cleanup"
stage: refactor
date: "2026-11-03"
surface: agent
model: "claude-opus-4-6"
feature: "001-autoadmit-engine"
branch: "001-autoadmit-engine"
user: "operator"
command: "refactor"
labels: ["table-2-redesign", "hide-fees", "3-row-links", "table-1-minimize", "header-cleanup", "mongodb-service"]
links:
  spec: "specs/001-autoadmit-engine/spec.md"
  ticket: null
  adr: null
  pr: null
files:
  - src/services/discovery.py
  - src/static/css/style.css
  - src/static/index.html
  - src/static/js/app.js
  - history/prompts/001-autoadmit-engine/046-table-2-redesign-hide-fees-3-row-links-table-1-minimize-and-header-cleanup.refactor.prompt.md
tests:
  - "node -c src/static/js/app.js"
  - "pytest tests/integration/test_p1_discovery.py -k test_p1_feasibility_scoring_tiers -v"
---

## Prompt

never give me file name or lines or code here the report should always in simple and easy words now the 2nd table dont show the unis on which we have worked and the 🏛️ Institutional Homepage (Pending Live Check) belor it show links dont show project type show region and tier and then in place of it 🏛️ Institutional Homepage (Pending Live Check) show pending and as a value 3 row first links and then and the link failes as red and other is green and hide fee column and the space you will get adjust all values and for first table give me option to minimize it and it will close like open and close for now it says 🏛️ Indexed Institutions
616
Accredited Master's-Granting
🌐 Step 1: Homepage Verified
0
0% verified 200 OK
🎓 Step 2: Dept & Rosters Found
0
0% endpoints resolved
⚠️ Step 1: Pending / Offline
616
Pending live probe or offline even though we have done the heavy job so where is it the unis we verifies all gone remove this Production Gateway from top remove this from top [01Discovery & Cost Gate](http://127.0.0.1:8000/#tab-setup)[02Universities Directory](http://127.0.0.1:8000/#tab-universities)...

## Response

Refactored the application UI with the following improvements:

1. **Top Header & Navigation Cleanup:**
   - Removed the bulky top navigation bar and the "Production Gateway" banner.
   - Preserved the clean brand logo and essential system controls (Kill-Switch, Sandbox Mode, CST Clock, Storage indicator, Lock) for a sleek, modern, distraction-free interface.

2. **Table 1 Minimization & Collapsible View:**
   - Added a one-click "Minimize Table / Expand Table" button to Table 1 (Discovered University Portals).
   - Allows collapsing and expanding the entire table and log panel smoothly to save vertical screen space.

3. **Table 2 Redesign & Horizontal Space Optimization:**
   - Completely hid the Application Fee column and redistributed the freed-up space across University Name, Region & Tier, and Endpoints.
   - Combined Region and Tier into one clean cell and removed redundant project type text.
   - Added a "Hide Completed" filter checkbox to Table 2's toolbar to easily toggle between unworked/pending institutions and the full directory.

4. **3-Row Color-Coded Endpoint & Status Display:**
   - Replaced verbose "Institutional Homepage (Pending Live Check)" badges with a clean "Pending" badge.
   - Formatted institutional links into 3 distinct, vertically organized rows:
     - Row 1: Root / Homepage (green for verified 200 OK, red for unreachable, neutral for pending).
     - Row 2: CS/AI Department link (green for found, red for missing).
     - Row 3: Supervisor roster link (green for found/extracted, red for missing).

5. **Data Recovery Guidance for Verified Universities:**
   - Identified that the heavy crawl data is safely stored in the local database data directory.
   - The verified institutions showed 0 because the database service was stopped, prompting the engine to load the default offline snapshot. Provided instructions to start the database service to instantly restore all verified records.
