---
id: 036
title: "Discuss Uvicorn vs Gunicorn on Windows, Playwright CPU/RAM Usage, and Separating Homepage vs Department Status"
stage: explainer
date: "2026-10-31"
surface: agent
model: "claude-opus-4-6"
feature: "001-autoadmit-engine"
branch: "001-autoadmit-engine"
user: "operator"
command: "explainer"
labels: ["uvicorn-vs-gunicorn", "playwright-memory", "homepage-vs-department", "architecture-discussion"]
links:
  spec: "specs/001-autoadmit-engine/spec.md"
  ticket: null
  adr: null
  pr: null
files: []
tests: []
---

## Prompt

No man Why it took 5 minutes for 22 universities (~14 seconds each) no it didnot it took alot of time man thats why i asked for workers and why are we using uvicorn not guicorn as far as i know the playwright and chromium is heavy right so dors this mean it will take alot of my cpu  and ram and if we have 5 workers that it will took alot more sodiscuss with me in simple and easy words  and also first the homapage which is 1 and then department which is 2 so if department fails this does not mean whole fails so we should show the table with correct logs

## Response

Discussed in simple, easy words:
1. Why it took so long earlier (stacking 10 sequential timeouts per university + 1-by-1 loop).
2. Why `uvicorn` is used instead of `gunicorn` (Gunicorn is Linux/macOS-only because it uses Unix `fcntl` and `os.fork()`; it crashes on Windows).
3. Playwright/Chromium CPU & RAM impact (opening 5 separate browsers eats 2+ GB RAM and spikes CPU; the right architecture is **90% lightweight HTTP (`httpx`)** + **1 single shared Chromium browser** with a strict concurrency cap of 1–2 tabs only when WAF 412/403 happens).
4. Separating **Step 1 (Homepage)** from **Step 2 (Department)** so that when Step 1 succeeds (`✓ Homepage Verified`) and Step 2 fails (`⚠ Dept Link Not Found`), we do NOT mark the whole university as failed—both the Table and Logs clearly show `✓ Step 1: Homepage OK` + `⚠ Step 2: Dept Link Missing`.

