---
id: 035
title: "Fix Windows Playwright Event Loop, Add Parallel Dept Probe Workers, Auto-Pause on Server Disconnect & Deduplicate Subdomains"
stage: refactor
date: "2026-10-31"
surface: agent
model: "claude-opus-4-6"
feature: "001-autoadmit-engine"
branch: "001-autoadmit-engine"
user: "operator"
command: "refactor"
labels: ["playwright-windows-fix", "parallel-workers", "subdomain-dedup", "auto-pause"]
links:
  spec: "specs/001-autoadmit-engine/spec.md"
  ticket: null
  adr: null
  pr: null
files:
  - src/services/scraper.py
  - src/services/discovery.py
  - src/api/routes_discovery.py
  - src/static/index.html
  - src/static/js/app.js
tests: []
---

## Prompt

so somehow my server stopped ... INFO: Shutting down ... KeyboardInterrupt ... but UI after 35 did this [19:33:08] [HomepageCrawler] [195/694] [Hunan University of Science and Technology] Failed: TypeError: Failed to fetch ... [694/694] [Zhejiang Wanli University] Failed: TypeError: Failed to fetch

## Response

1. **Why the Server Stopped & Why the UI Printed `TypeError: Failed to fetch`:**
   - The terminal received a `SIGINT`/`KeyboardInterrupt` (`INFO: Shutting down` / `Stopping reloader process`) at `19:30:54` after repeated unhandled Playwright `NotImplementedError` tasks.
   - Once the backend server stopped (`(sch) PS D:\Sch>`), the browser's `for` loop kept calling `fetch("/api/v1/discovery/resolve-departments")` against the dead port, which immediately failed with `TypeError: Failed to fetch` for the remaining rows.
2. **Fixes Implemented:**
   - **Windows Playwright Fix (`src/services/scraper.py`):** Switched `fetch_html_dynamic()` to run `sync_playwright` inside `asyncio.to_thread` with `asyncio.WindowsProactorEventLoopPolicy()` so `NotImplementedError` never happens under `uvicorn --reload` on Windows.
   - **Smart WAF Check & Parallel Subdomain Probing (`src/services/discovery.py`):** Stopped launching Playwright on DNS failures (`getaddrinfo failed`) and changed CS/AI subdomain fallback probing (`cs.`, `cist.`, `ai.`, `jsj.`, `scse.`, `sist.`, `cie.`) to run concurrently with `asyncio.gather`.
   - **Root Domain Normalization & Duplicate Removal (`src/services/discovery.py`, `src/api/routes_discovery.py`):** Normalized `.edu.cn` / `.ac.cn` subdomains (e.g. `ar.shisu.edu.cn`, `en.bjtu.edu.cn`) to their 3-part registrable root (`shisu.edu.cn`, `bjtu.edu.cn`) and deduplicated by both domain and university name so universities like `Shanghai International Studies University` never appear 25 times.
   - **Parallel Worker Pool (`5` / `8` / `12` Workers) + Auto-Pause on Server Disconnect (`src/static/index.html`, `src/static/js/app.js`, `src/api/routes_discovery.py`):** Added `#portal-probe-workers` (default `5 Workers (Parallel)`) next to `🧭 Resolve Real Dept Links`, parallelized `POST /api/v1/discovery/resolve-departments` with `asyncio.Semaphore` + `asyncio.gather`, and added automatic batch pause if `Failed to fetch` occurs.

