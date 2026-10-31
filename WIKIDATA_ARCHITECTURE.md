# Wikidata Discovery Architecture & Parameter Audit

This document explains how **AutoAdmit Engine** queries Wikidata for Chinese university discovery, which parameters are retrieved, why certain fields previously showed inaccurate defaults (`Top 50`, `Tier 3`, `0 RMB`, and template department links), and how the multi-stage verification pipeline resolves real institutional data.

---

## 1. How We Query Wikidata (Live SPARQL Protocol)

AutoAdmit connects directly to the official **Wikidata Query Service (WDQS)** endpoint over HTTPS:

- **Endpoint:** `https://query.wikidata.org/sparql`
- **Method:** `GET` with `format=json`
- **Caching:** 1-hour in-memory TTL cache (`_cached_wikidata_records`) to prevent rate-limiting after the initial bulk fetch.

### Exact SPARQL Query Used

```sparql
SELECT DISTINCT ?u ?enName ?zhName ?site ?proj WHERE {
  ?u wdt:P31/wdt:P279* wd:Q3918;
     wdt:P17 wd:Q148;
     wdt:P856 ?site.
  OPTIONAL { ?u rdfs:label ?enName FILTER (lang(?enName) = 'en') }
  OPTIONAL { ?u rdfs:label ?zhName FILTER (lang(?zhName) = 'zh') }
  OPTIONAL {
    ?u (wdt:P463|wdt:P361) ?proj.
    FILTER (?proj IN (wd:Q2502602, wd:Q1970502, wd:Q42308523))
  }
} LIMIT 1200
```

### Breakdown of SPARQL Parameters & Predicates

| Parameter / Predicate | Wikidata Entity / Property | Meaning & Purpose |
| :--- | :--- | :--- |
| `?u wdt:P31/wdt:P279* wd:Q3918` | Instance of (`P31`) / Subclass of (`P279*`) **University (`Q3918`)** | Finds all universities, polytechnics, and higher-education institutions. |
| `wdt:P17 wd:Q148` | Country (`P17`) = **People's Republic of China (`Q148`)** | Restricts results strictly to Chinese institutions. |
| `wdt:P856 ?site` | **Official Website (`P856`)** | Retrieves the official institutional root URL (e.g., `https://www.whpu.edu.cn/`). Filtered in Python to require `.edu.cn` or `.cn` academic domains. |
| `rdfs:label ?enName` | English Label (`lang = 'en'`) | Official English name (e.g., *Wuhan Polytechnic University*). |
| `rdfs:label ?zhName` | Chinese Label (`lang = 'zh'`) | Official Chinese name (e.g., *武汉轻工大学*). |
| `wdt:P463 \| wdt:P361 ?proj` | Member of (`P463`) / Part of (`P361`) | Checks membership in **Project 985 (`Q2502602`)**, **Project 211 (`Q1970502`)**, or **Double First-Class (`Q42308523`)**. |

---

## 2. Parameter Audit: Are We Getting the Right Data from Wikidata?

### What Wikidata Provides Accurately (High Reliability)
1. **Total Accredited Institutions (~745 records):** Wikidata reliably returns ~745 Chinese universities that hold official `.edu.cn` websites.
2. **English & Native Chinese Names (`enName`, `zhName`):** Highly accurate for cross-referencing and search.
3. **Official Root Homepage URL (`?site`):** Gives the real institutional homepage (such as `http://www.whpu.edu.cn/`), preserving whether the university requires `www.` or uses a bare domain.

### Where Wikidata Has Gaps (And Why the Table Previously Showed Wrong Values)

| Field in UI | What Happened Previously | Root Cause | How It Is Fixed Now |
| :--- | :--- | :--- | :--- |
| **CS Ranking (`Top 50`)** | All 745 universities displayed `Top 50` in the Feasibility table. | Wikidata does **not** store subject rankings. `cs_ranking` was `null` in Python, and `app.js` had a hardcoded fallback: `u.cs_ranking ? '#' + u.cs_ranking : 'Top 50'`. | Removed fake `'Top 50'` fallback. Now displays actual tier classification (`985 / C9 Elite`, `211 Key National`, or `Unranked / General`). |
| **Feasibility Tier (`All Tier 3`)** | Most of the 745 universities were marked `Tier 3 (Safety)`. | In Wikidata, many 985/211 universities do not attach `P463` (Member Of) to `Q2502602` / `Q1970502` on their entity page. Relying only on `?proj` missed them. | Combined Wikidata `?proj` tags with the complete official **MOE Project 985 (39 universities)** and **Project 211 (115+ universities)** domain registries in `discovery.py`. |
| **Application Fee (`0 RMB Free`)** | Every university showed `0 RMB (Free)`. | Wikidata does **not** track international application fees. `discovery.py` hardcoded `application_fee_rmb=0`. In reality, most Chinese universities charge **400–800 RMB** unless explicitly waived. | Set unverified fees to `None` (`400–800 RMB (Typical / Unverified)` in UI) and only display `0 RMB (Fee Waived)` when a university is verified as fee-free. |
| **Department URLs (`cs.whpu.edu.cn`)** | Generated `http://cs.{domain}/faculty` and `http://ai.{domain}/supervisors`, causing `DNS_PROBE_FINISHED_NXDOMAIN`. | Wikidata only knows the **University Root Homepage**, never internal department URLs. Chinese universities use varied subdomains (e.g., `sjxy.whpu.edu.cn` for Math & CS). | Stopped fabricating template URLs. Implemented **Homepage-First Department Discovery** with explicit pipeline status tracking. |

---

## 3. Multi-Stage Pipeline Status Lifecycle

Instead of pretending all 745 universities immediately have verified CS/AI faculty URLs, each discovered university moves through five explicit verification states:

1. **`University Homepage Verified`**: Root domain and homepage URL retrieved from Wikidata/MOE (e.g., `https://www.whpu.edu.cn/`).
2. **`Department URL Found`**: Crawler inspected the homepage's `院系设置` / `机构设置` (Schools & Departments) directory and resolved the real CS/AI/Math-CS school URL (e.g., `http://sjxy.whpu.edu.cn/`).
3. **`Department URL Not Found`**: Homepage was inspected, but no matching CS/AI/Information department link could be confirmed automatically.
4. **`Faculty Page Found`**: Located the active supervisor roster (`师资队伍` / `导师队伍` / `研究生导师`, e.g., `http://sjxy.whpu.edu.cn/yjsjy/dsdw_new.htm`).
5. **`Professor Extraction Completed`**: Master's supervisors (`硕导` / `博导`) extracted, verified with anti-negation checks, and persisted to MongoDB.
6. **`Requires Manual Review`**: Site blocked automated navigation, timed out, or requires operator URL input.

