# ADR-0001: Multi-Source University Discovery and Supervisor Verification Architecture

> **Scope**: Multi-source institutional discovery, truthfulness verification hierarchy, anti-negation supervisor extraction, and cryptographic data lineage for the AutoAdmit Phase 1 crawler.

- **Status:** Accepted
- **Date:** 2026-10-30
- **Feature:** 001-autoadmit-engine
- **Context:**
  The AutoAdmit Engine discovers accredited Chinese universities, evaluates institutional feasibility, resolves CS/AI department endpoints, and harvests master's supervisor profiles (硕士生导师 / 硕导) for scholarship outreach.
  
  Previously, the system relied on pre-seeded catalog files (`chinese_universities.json`), violating Rule 2 (No Fabricated Data) and Rule 3 (Dynamic Discovery) of `rules.md`. However, moving to live internet extraction presents significant reliability and truthfulness challenges:
  1. **Wikidata Limitations:** While Wikidata provides fast, structured data on university existence, official domains, and Project 985/211 tags, it does not track active admissions cycles, current scholarship quotas, or individual faculty supervisor assignments.
  2. **Search Engine Fragility:** Relying exclusively on search engine scraping (Google/Baidu) rapidly hits rate limits and CAPTCHA firewalls.
  3. **Government Registry Structure:** China's Ministry of Education (MOE / `moe.gov.cn`) provides the gold standard for accreditation (全国高等学校名单), but presents plain HTML tables without direct department directory links.
  4. **Faculty Site Nuances:** Chinese university departmental websites use mixed character encodings (`GB18030`, `GBK`, `GB2312`, `UTF-8`), obfuscate email addresses, and occasionally describe non-supervisory roles with negative affixes (e.g., `非硕士生导师`, `非博导`).

<!-- Significance checklist:
     1) Impact: Determines how university and professor data is fetched, verified, and stored across the platform. (TRUE)
     2) Alternatives: Evaluated pure Wikidata, pure Search Engine scraping, MOE-only crawling, and combined verification. (TRUE)
     3) Scope: Cross-cutting architectural decision affecting UI, API, scraper workers, and database schemas. (TRUE) -->

## Decision

We adopt a **4-Level Source-of-Truth Verification Pyramid** combined with a **Multi-Source UI Selector** and **Cryptographic Data Lineage**:

```
                       ▲
                      / \     Level 4: Faculty Profile & Supervisor Evidence
                     /   \    (Official Department Pages, 硕导 Verification, Email De-obfuscation)
                    /-----\
                   /       \   Level 3: Admission & Program Eligibility
                  /         \  (Campus China CSC Directory, University International College)
                 /-----------\
                /             \  Level 2: Official Domain Verification
               /               \ (DNS, SSL, .edu.cn Registry, HTTP Handshake)
              /-----------------\
             /                   \ Level 1: Institutional Discovery & Accreditation
            /_____________________\ (Wikidata Open Graph + MOE Official Registry + Search Engine)
```

1. **Multi-Source Discovery Engine (Level 1):**
   - The UI provides a Discovery Source Selector with 4 operating modes:
     - `Mode A (Wikidata SPARQL)`: Fast batch query for names, official domains, regions, and 985/211 tags.
     - `Mode B (China MOE Live List)`: Official accreditation cross-check via `moe.gov.cn`.
     - `Mode C (Targeted Search & Direct Intake)`: Search engine discovery and custom `.edu.cn` URL intake.
     - `Mode D (Combined Cross-Check - Default)`: Queries Wikidata for discovery, cross-validates against MOE accreditation, and performs live domain handshakes.

2. **Official Domain Verification (Level 2):**
   - Enforces `.edu.cn` syntax, live DNS resolution, and HTTP 200/301 responses before indexing.

3. **Admission & Scholarship Verification (Level 3):**
   - Cross-checks institutional participation on **CampusChina.org** (CSC Type B) and locates the university's International Student Office (`留学生院`) portal.

4. **Faculty Profile & Supervisor Evidence (Level 4):**
   - **Two-Level Scraper:** Department directory $\rightarrow$ individual professor bios.
   - **Multi-Charset Auto-Detection:** Automatically decodes `gb18030`, `gb2312`, `gbk`, and `utf-8`.
   - **Anti-Negation Qualification Guard:** Validates tokens like `硕士生导师` or `硕导` only if not preceded by negative particles (`非`, `不`, `无`, `未`, `暂停`).
   - **Email De-Obfuscation:** Normalizes obfuscation patterns (`[at]`, `(at)`, `_at_`, `&#64;`, reversed CSS text).
   - **Cryptographic Lineage:** Calculates and stores the SHA-256 hash of the raw HTML snapshot in MongoDB.

5. **Logical Database Separation (MongoDB):**
   - Collection `universities`: Institutional intelligence, accreditation status, official domains, and department links.
   - Collection `professors`: Supervisor intelligence, verified emails, research topics, `is_master_supervisor` flag, and raw HTML SHA-256 evidence.

## Consequences

### Positive

- **Zero Fabricated Data:** Fully eliminates reliance on static benchmark seed files in runtime operations.
- **High Speed + High Truthfulness:** Leverages Wikidata SPARQL for instantaneous discovery without CAPTCHAs, but grounds all admissions and supervisor claims in primary institutional web pages.
- **Defensive Against False Positives:** Anti-negation parsing prevents classifying non-supervisors (`非硕导`) as eligible targets.
- **Auditability:** SHA-256 raw HTML hashes provide cryptographic verification for every harvested supervisor.
- **Operator Autonomy:** Users can choose single-source or triple-cross-checked modes directly from the UI.

### Negative

- **Network Dependency:** Multi-level live crawling requires network connectivity and robust polite throttling (0.5s delay, concurrency caps).
- **Charset Complexity:** Older Chinese university servers using GB18030 require CPU-bound character decoding fallbacks.

## Alternatives Considered

- **Alternative A: Pure Wikidata Reliance:**
  * *Why rejected:* Wikidata lacks real-time admissions updates, active intake deadlines, and individual supervisor assignments. Using it as a final authority leads to stale or unverified data.
- **Alternative B: Pure Search Engine Scraping (Baidu/Google):**
  * *Why rejected:* Aggressive rate-limiting, CAPTCHA hurdles, and inconsistent search snippets.
- **Alternative C: Pure MOE List Scraping:**
  * *Why rejected:* MOE lists contain institution names and codes but lack direct departmental faculty URLs, requiring subsequent search steps anyway.

## References

- Feature Spec: `specs/001-autoadmit-engine/spec.md`
- Implementation Plan: `specs/001-autoadmit-engine/phase1-multi-source-architecture-and-verification.md`
- Related ADRs: None (ADR-0001 initial platform ADR)
- Evaluator Evidence: `history/prompts/001-autoadmit-engine/016-multi-source-discovery-and-truthfulness-architecture.explainer.prompt.md`

