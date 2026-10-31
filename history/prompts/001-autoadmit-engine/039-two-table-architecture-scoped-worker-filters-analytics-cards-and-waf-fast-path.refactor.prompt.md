---
id: 039
title: "Two-Table Architecture Redesign, Scoped Worker Filters, Live Analytics Cards, and WAF Fast-Path"
stage: refactor
date: "2026-10-31"
surface: agent
model: "claude-opus-4-6"
feature: "001-autoadmit-engine"
branch: "001-autoadmit-engine"
user: "operator"
command: "refactor"
labels: ["mongodb-preservation", "table1-scoped-workers", "table2-analytics-cards", "table2-7cols", "waf-fast-path", "webvpn-filter"]
links:
  spec: "specs/001-autoadmit-engine/spec.md"
  ticket: null
  adr: null
  pr: null
files:
  - src/services/discovery.py
  - src/static/index.html
  - src/static/css/style.css
  - src/static/js/app.js
tests:
  - "py_compile src/services/discovery.py src/api/routes_discovery.py"
---

## Prompt

ok work on above and also the process completed so see logs and dont delete this from db man its crucial data 5-6 hours so i dont want to loose this data man nan ever ,Alright, let's look at a few things. In our UI, we have two types of tables. One appears when we perform a search—it displays the results found. Then there is the 'discovery' process, where we verify the links; if they belong to a university and are associated with faculty, a table is generated. This is a temporary table—the kind that used to disappear whenever the page was refreshed. There is also a second table: the 'Institutional Directory, University Feasibility, and Scholarship Metrics' table. Honestly, its current UI isn't very good. Regarding the first table, we need to add options for 'Region' and 'University.' This will allow us to run queries or execute actions for a specific university or a particular region, and process their respective links. Furthermore, we need to add a 'Tier' filter. We should be able to filter by tier—either independently or in combination with a region (e.g., a specific tier within a specific region). Essentially, the workers will operate based on the filters selected; if a filter isn't chosen, it simply won't be applied. So, that’s one requirement. Additionally, regarding the university-related part... There is a second table at the end; however, it is not quite right. While it displays the official domain, the specific links we’ve gathered are missing. Additionally, there is a "native name" field—this should be integrated with the university name column. There are also two other columns: "national classification" and "feasibility"—these two should be merged into a single column. The "feasibility" section contains a line stating "target active associate"—remove that. We want to target all active professors and associate professors alike; targeting only associate professors makes no sense. The table also has too much padding, which should be reduced; right now, it takes up too much horizontal space and doesn't look good. The status should clearly indicate Step 1 and Step 2. We should be able to apply sorting filters across these columns. In the end, what we need is an overview section with cards displaying data such as the total count, how many were verified, how many succeeded, how many failed, along with a regional distribution breakdown. When performing discovery, we should be able to select a specific university, a particular region, or a tier, or even apply multiple filters simultaneously, and then run the process. The workers should operate based strictly on the selected criteria. If only one university is selected, only that university should be processed. If all options are selected, it should proceed as usual, and so forth.

## Response

1. **MongoDB Data Safety & Zero-Loss Guarantee:**
   - Ensured all updates in `src/api/routes_discovery.py` use `update_one({"domain": ...}, {"$set": ...}, upsert=True)`.
   - Never drops or truncates `universities`, `professors`, or `discovery_runs` collections. Existing verified records and endpoints are strictly preserved.

2. **Table 1 (`Discovered University Portals`) Scoped Execution:**
   - Added `#portal-univ-filter` alongside `#portal-region-filter` and `#portal-tier-filter` above Table 1.
   - Dynamic update via `populatePortalUnivDropdown()`: selecting a region or tier dynamically updates the university dropdown with matching institutions.
   - Updated `resolveRealDepartmentsForVisible()`: workers operate strictly based on active filters (Region, Tier, Specific University, or All). When a single university is selected, only that university is probed.
   - Integrated English Name and Native Chinese Name into a unified column.

3. **Table 2 (`Institutional Directory, University Feasibility & Scholarship Matrix`) UI Overhaul:**
   - Compacted padding (`padding: 0.45rem 0.65rem !important`) and eliminated excessive horizontal gaps.
   - Streamlined layout from 10 wide columns to 7 high-density columns:
     1. `#` (`.col-num`)
     2. `University & Native Name` (English bold + Chinese subtitle underneath)
     3. `Region` (Region badge)
     4. `Official Domain & Gathered Endpoints` (Root domain link + gathered department & roster links)
     5. `Tier & Classification` (Consolidated 985/211/Provincial badge + Tier badge + Competition note; removed outdated "target active associate")
     6. `Scholarships & Fee` (Fee status badge + scholarships list)
     7. `Live Verification Status` (Stacked Step 1 & Step 2 badges with error/reason tooltips)
   - Added `status-asc` sorting so verified universities sort to the top.

4. **Interactive Analytics Header & Regional Breakdown:**
   - Added `#matrix-analytics-container` above Table 2 with 4 real-time stat cards:
     - 🏛️ Indexed Institutions
     - 🌐 Step 1: Homepage Verified (count + % verified 200 OK)
     - 🎓 Step 2: Dept & Rosters Found (count + % endpoints resolved)
     - ⚠️ Step 1: Pending / Offline
   - Added interactive Regional Distribution Breakdown (`#matrix-region-pills`) showing universities per province (e.g. `Beijing (35)`, `Jiangsu (28)`). Clicking any pill instantly filters the directory to that province.

5. **WAF Fast-Path & Campus WebVPN Filter:**
   - Restrained Playwright in `_fetch_with_waf_fallback`: generic network errors and timeouts fail fast and never trigger headless Playwright. Playwright is only invoked on explicit WAF challenge status codes (`403, 412, 429, 521`) or anti-bot challenge scripts.
   - Filtered campus WebVPN / CAS login URLs and titles (`login`, `authserver`, `webvpn`, `cas`, `统一身份认证`, etc.) from being recorded as academic department links.
