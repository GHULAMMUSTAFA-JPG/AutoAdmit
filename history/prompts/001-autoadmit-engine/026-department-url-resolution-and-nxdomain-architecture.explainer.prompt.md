---
id: "026"
title: "Department URL Resolution Strategy and NXDOMAIN Root Cause Analysis"
stage: "explainer"
date_iso: "2026-10-31"
surface: "agent"
model: "gemini-2.5-pro"
feature: "001-autoadmit-engine"
branch: "001-autoadmit-engine"
user: "User"
command: "/sp.explainer"
labels: ["discovery", "dns", "department-urls", "crawler", "architecture"]
links:
  spec: "specs/001-autoadmit-engine/spec.md"
  ticket: null
  adr: "history/adr/0002-multi-source-discovery-and-truthfulness-pipeline.md"
  pr: null
files_yaml:
  - "src/services/discovery.py"
tests_yaml: []
---

### Prompt Text
so it gave me 745 results and i did on(Wuhan Polytechnic University	武汉轻工大学	Hubei	Tier 3 (Safety)	
Wuhan Polytechnic University - School of Computer Science http://cs.whpu.edu.cn/faculty
Wuhan Polytechnic University - School of Artificial Intelligence http://ai.whpu.edu.cn/supervisors) open the link and it was This site can’t be reached
Check if there is a typo in cs.whpu.edu.cn.

If spelling is correct, try running windows network Diagnostics.
DNS_PROBE_FINISHED_NXDOMAIN, now i dont know how many unis will pass link link found so i want to know what should we do we dont have the right links give me response dont go into code discuss with me man

### Key Decisions & Actions
- Provided comprehensive architectural discussion without touching codebase as requested.
- Explained the root cause of DNS NXDOMAIN: static subdomain template generation (`cs.<domain>` / `ai.<domain>`) vs real Chinese higher-education web taxonomy.
- Analyzed 3 concrete enterprise strategies:
  1. Automated Root-to-School Crawler Navigation (`院系设置` -> `计算机` -> `师资队伍`).
  2. Targeted Search Engine / Site-Restricted Querying (`site:domain 计算机 师资`).
  3. Pre-Flight DNS/HTTP Probing with Chinese academic subdomain matrix (`jsj.`, `scse.`, `cie.`).
- Invited user decision on chosen resolution architecture.

