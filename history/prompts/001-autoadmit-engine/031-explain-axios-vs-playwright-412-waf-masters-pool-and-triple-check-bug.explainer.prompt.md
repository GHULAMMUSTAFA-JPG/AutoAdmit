---
id: 031
title: Explain Axios vs Playwright for 412 WAF, Master's Pool Sources, and Combined Triple-Check Bug
stage: explainer
date: 2026-10-31
surface: agent
model: claude-opus-4-6
feature: 001-autoadmit-engine
branch: 001-autoadmit-engine
user: parep
command: explainer
labels: ["waf-412", "axios-vs-playwright", "combined-triple-check", "masters-universities", "chsi-moe"]
links:
  spec: specs/001-autoadmit-engine/spec.md
  ticket: null
  adr: null
  pr: null
files:
 - src/api/routes_discovery.py
 - src/services/discovery.py
 - src/static/js/app.js
tests:
 - none
---

## Prompt

ok(Required Fix:
Initial status from discovery must be Pending Live Check (grey/amber badge).
Status only upgrades to ● Homepage Verified after a live HTTP/browser check receives a valid 200 OK page, and moves to ● Dept Resolved / ● Supervisors Harvested as each stage actually succeeds.), what can we do(Root Cause (Anti-Bot WAF on Chinese .edu.cn Portals)), and can axios help if not httpx, i am targetting for masters Category	Official MOE Count	Offers Master's Degrees (硕导)?	Relevant to Your Application?
Adult Higher Education (成人高等学校)	244	❌ No (Night/retraining schools)	❌ No
Vocational / Junior Colleges (高职 / 专科院校)	~1,630	❌ No (3-year diploma only)	❌ No
Regular 4-Year Undergraduate Universities (普通本科院校)	~1,322	⚠️ Only ~650–850 have Master's authorization (硕士点)	✅ Yes (Target Pool)
Total MOE Higher Education Institutions	3,196	~650–850 Master's-granting	~500–850 Target Universities not BS , what are aternatives and what are the other options (Wikidata is incomplete for Chinese provincial colleges: Wikidata (query.wikidata.org) is a crowd-sourced global encyclopedia, not the official Chinese Ministry of Education (全国高等学校名单) registry. About ~500 regular Chinese undergraduate universities in Wikidata either have no Wikidata item or are missing their P856 (Official Website) property.) so from UI i am doing ⭐
Combined Triple-Check
Recommended so why it didnot took in all things means the options and not working and search system is broken, 

## Response snapshot

1. Explained why `axios` cannot solve `HTTP 412 Precondition Failed` (both `axios` and `httpx` are plain HTTP clients without a JavaScript engine to execute the RiverSecurity/瑞数 WAF dynamic cookie script) and how **Playwright (Headless Chromium)** solves it by executing the JS challenge and reusing the session cookies.
2. Identified the exact backend bug why `⭐ Combined Triple-Check` and `🏛️ China MOE Official List` in the UI did not work: `app.js` sent `source: activeDiscoverySource` (`"combined"`), but `FilterUniversitiesRequest` in `src/api/routes_discovery.py` lacked the `source` field and `discovery.py` only called Wikidata SPARQL.
3. Detailed the authoritative sources for Master's-granting Chinese universities (`硕士授权高校`, ~800+ institutions) so `Combined Triple-Check` merges: (1) China MOE / CHSI Graduate Admissions Registry (`yz.chsi.com.cn` Master's-granting institutions, excluding vocational/BS-only colleges), (2) Wikidata SPARQL, and (3) Open `.edu.cn` Domain & CSC/985/211 Master's Registry.

## Outcome

- ✅ Impact: Pinpointed why the UI source selector (`Combined Triple-Check`) only ran Wikidata, explained why Playwright is needed over `axios`/`httpx` for `412` WAF portals, and defined the Master's-only (`硕士点`) multi-source architecture.
- 🧪 Tests: Diagnostic & architecture alignment step.
- 📁 Files: Created PHR 031.
- 🔁 Next prompts: Implement `Pending Live Check` status, Playwright headless fallback for `412`/`403` WAFs, and true 3-source Master's-granting `Combined Triple-Check` in `discovery.py` and `routes_discovery.py`.
- 🧠 Reflection: Every UI control (like the 4 Discovery Source pills) must have real backend branching in `routes_discovery.py` and `discovery.py`.

## Evaluation notes (flywheel)

- Failure modes observed: `FilterUniversitiesRequest` in `src/api/routes_discovery.py` silently dropped the `source` parameter from the frontend payload.
- Graders run and results (PASS/FAIL): PASS
- Prompt variant (if applicable): N/A
- Next experiment (smallest change to try): Wire `source` (`combined`, `wikidata`, `moe`) in `routes_discovery.py` and `discovery.py`, add Playwright fallback for `412` WAFs, and set initial status to `Pending Live Check`.

