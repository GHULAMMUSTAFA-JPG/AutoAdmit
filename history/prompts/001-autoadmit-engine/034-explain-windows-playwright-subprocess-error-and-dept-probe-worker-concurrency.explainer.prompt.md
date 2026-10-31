---
id: 034
title: "Explain Windows Playwright Subprocess Error and Dept Probe Worker Concurrency"
stage: explainer
date: "2026-10-31"
surface: agent
model: "claude-opus-4-6"
feature: "001-autoadmit-engine"
branch: "001-autoadmit-engine"
user: "operator"
command: "explainer"
labels: ["playwright", "windows-event-loop", "workers", "concurrency"]
links:
  spec: "specs/001-autoadmit-engine/spec.md"
  ticket: null
  adr: null
  pr: null
files: []
tests: []
---

## Prompt

short answer how many workers are working on this ... so first explain the error in easy words and then also how many workers are doing this task coz look its taking time and very slow

## Response

1. **Easy Explanation of the `NotImplementedError`:**
   - On Windows, when `uvicorn` runs with `--reload`, Python switches to `SelectorEventLoop`, which **cannot launch child programs (`subprocess`)** like the Playwright Chromium browser (`_make_subprocess_transport -> NotImplementedError`).
   - So whenever a university like BUPT returns `HTTP 412 WAF challenge` and the backend tries to open Playwright, Windows blocks `asyncio.create_subprocess_exec` from starting Chromium unless Playwright runs in a separate thread with `WindowsProactorEventLoopPolicy` (or `sync_playwright` inside `asyncio.to_thread`).
2. **How Many Workers Are Running Right Now:**
   - Currently, **`🧭 Resolve Real Dept Links` in Section 01 is running with only `1` sequential worker** (`for (const u of targets)` sending `domains: [u.domain]` one university at a time in `src/static/js/app.js`).
   - Additionally, when a university fails or hits WAF, it sequentially tries 3 homepage URLs + 6 subdomains (`cs.`, `cist.`, `ai.`, `jsj.`, `scse.`, `sist.`), taking ~15–25 seconds per university.

