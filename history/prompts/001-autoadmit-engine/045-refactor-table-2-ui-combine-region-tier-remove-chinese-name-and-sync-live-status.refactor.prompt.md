---
id: 045
title: "Refactor Table 2 UI Combine Region Tier Remove Chinese Name and Sync Live Status"
stage: refactor
date: "2026-11-02"
surface: agent
model: "claude-opus-4-6"
feature: "001-autoadmit-engine"
branch: "001-autoadmit-engine"
user: "operator"
command: "refactor"
labels: ["table-2-ui", "combine-columns", "remove-chinese-name", "sync-live-status", "styling"]
links:
  spec: "specs/001-autoadmit-engine/spec.md"
  ticket: null
  adr: null
  pr: null
files:
  - src/static/css/style.css
  - src/static/index.html
  - src/static/js/app.js
  - history/prompts/001-autoadmit-engine/045-refactor-table-2-ui-combine-region-tier-remove-chinese-name-and-sync-live-status.refactor.prompt.md
tests:
  - "node -c src/static/js/app.js"
  - "pytest tests/integration/test_p1_discovery.py -k test_p1_feasibility_scoring_tiers -v"
---

## Prompt

first commit and then the table shows pending live check  Pending Live Check for all unis in the 2nd table and first table is changed which is ok but 2nd has uni name and region alot of space remove chinese name from second table and then and combine region and tier in 1 and then action make it small too and make the second tabe beautiful.

## Response

Refactored Section 02 (Table 2 - Institutional Directory & Feasibility Matrix) with the following enhancements:

1. **Live Status Sync Invariant:**
   - Modified `applyMatrixTableFilter()` in `src/static/js/app.js` to automatically merge verified pipeline statuses from `lastDiscoveredUniversities`. As soon as any institution is probed in Table 1 or returned from discovery, Table 2 immediately updates its status badge (e.g. `Faculty Page Found`, `Homepage Verified`, `Step 1 Failed`) instead of falling back to `Pending Live Check`.

2. **Removed Chinese Name from Table 2:**
   - Removed the Chinese name secondary line from Table 2's University Name column, keeping the table clean, professional, and readable with English institutional names.

3. **Combined Region and Tier in 1 Column:**
   - Merged the separate "Region" and "Tier" columns into a single unified column: `Region & Tier`.
   - Renders regional badge, tier badge, national project classification (`Project 985` / `Project 211` / `Provincial Key`), and competitiveness note compactly in one cell.

4. **Compact Action Column:**
   - Added a compact Action column with a small, lightweight probe button (`🧭 Probe` with `.btn-xs`) allowing direct single-university probing from Table 2.

5. **Visual Styling & Beauty Improvements:**
   - Added `.btn-xs` and styled `#matrix-table-view` in `src/static/css/style.css` with clean borders (`#cbd5e1`), subtle headers (`#f1f5f9`), smooth hover highlighting (`#f8fafc`), and tight cell padding.
