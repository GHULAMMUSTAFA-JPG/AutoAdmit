"""Phase 1 Layer 3 Search-First Discovery Provider (Serper / Tavily / DuckDuckGo HTML fallback with Budget Policy Enforcement)."""

from dataclasses import dataclass
import re
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse
from bs4 import BeautifulSoup
import httpx

from src.config import settings
from src.core.policies import policy_manager
from src.core.telemetry import ErrorCode, StepResult


@dataclass
class SearchCandidate:
    """Validated candidate URL returned by Layer 3 Search-First discovery."""
    url: str
    title: str
    snippet: str = ""
    is_faculty_roster: bool = False
    inherited_label_zh: str = ""
    inherited_degree: str = "master"
    provider: str = "serper"


# Bilingual discipline query expansion dictionary
DISCIPLINE_SYNONYMS: Dict[str, Tuple[List[str], List[str]]] = {
    "computer_science": (
        ["计算机", "计算机科学与技术", "计算机学院", "计算学部", "信息与计算机"],
        ["Computer Science", "School of Computer", "College of Computer"],
    ),
    "artificial_intelligence": (
        ["人工智能", "智能科学与技术", "人工智能学院", "智能学院", "机器智能"],
        ["Artificial Intelligence", "School of AI", "Intelligent Science"],
    ),
    "software_engineering": (
        ["软件工程", "软件学院", "大数据与软件", "计算机与软件"],
        ["Software Engineering", "School of Software"],
    ),
    "cyber_security": (
        ["网络空间安全", "网络安全", "信息安全", "网络空间安全学院"],
        ["Cyber Security", "Information Security"],
    ),
    "electronic_information": (
        ["电子信息", "信息工程", "信息科学与工程学院", "通信工程", "自动化"],
        ["Electronic Information", "Information Engineering"],
    ),
}

AUTH_URL_EXCLUSIONS = (
    "login", "authserver", "webvpn", "clientvpn", "cas.", "sso.", "passport",
    "userlogin", "mail.", "webmail", "/info/", "/news/", "/notice/", "/article/",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".jpg", ".png"
)

FACULTY_ROSTER_MARKERS = (
    ("硕士生导师", "master"),
    ("硕导", "master"),
    ("研究生导师", "master"),
    ("博士生导师", "phd"),
    ("博导", "phd"),
    ("导师队伍", "master"),
    ("导师名录", "master"),
    ("师资队伍", "master"),
    ("教师名录", "master"),
    ("专任教师", "master"),
    ("师资力量", "master"),
    ("faculty", "master"),
    ("supervisors", "master"),
)


def normalize_discipline_key(discipline: str) -> str:
    """Normalizes free-text discipline name into canonical discipline_key."""
    low = (discipline or "Computer Science").strip().lower()
    if any(k in low for k in ("artif", "ai", "人工智能", "智能")):
        return "artificial_intelligence"
    if any(k in low for k in ("soft", "软件")):
        return "software_engineering"
    if any(k in low for k in ("cyber", "security", "安全", "网安")):
        return "cyber_security"
    if any(k in low for k in ("electron", "telecom", "电子", "通信")):
        return "electronic_information"
    return "computer_science"


class SearchFirstProvider:
    """Executes targeted `site:<domain>` queries behind ToolPolicyManager budget and kill-switch guardrails."""

    def build_site_query(self, domain: str, discipline: str) -> str:
        disc_key = normalize_discipline_key(discipline)
        zh_terms, en_terms = DISCIPLINE_SYNONYMS.get(disc_key, DISCIPLINE_SYNONYMS["computer_science"])
        zh_clause = " OR ".join(f'"{t}"' for t in zh_terms[:3])
        return f'site:{domain} ({zh_clause} OR "{en_terms[0]}") ("师资队伍" OR "硕士生导师" OR "教师名录" OR "学院")'

    @staticmethod
    def _is_same_domain(url: str, domain: str) -> bool:
        try:
            host = urlparse(url).netloc.lower().split(":")[0]
            clean_dom = domain.lower().strip()
            return host == clean_dom or host.endswith("." + clean_dom)
        except Exception:
            return False

    @classmethod
    def _classify_and_filter_items(
        cls,
        raw_items: List[Dict[str, str]],
        domain: str,
        provider_name: str,
    ) -> List[SearchCandidate]:
        candidates: List[SearchCandidate] = []
        seen_urls = set()

        for item in raw_items:
            raw_url = (item.get("url") or "").strip()
            title = (item.get("title") or "").strip()
            snippet = (item.get("snippet") or "").strip()
            if not raw_url or not cls._is_same_domain(raw_url, domain):
                continue
            u_low = raw_url.lower()
            if any(bad in u_low for bad in AUTH_URL_EXCLUSIONS):
                continue
            clean_url = raw_url.split("#")[0]
            if clean_url in seen_urls:
                continue
            seen_urls.add(clean_url)

            combined_text = f"{title} {snippet}".lower()
            is_roster = False
            label_zh = ""
            degree = "master"
            for marker, deg in FACULTY_ROSTER_MARKERS:
                if marker in combined_text:
                    is_roster = True
                    label_zh = marker
                    degree = deg
                    break

            candidates.append(
                SearchCandidate(
                    url=clean_url,
                    title=title or clean_url,
                    snippet=snippet,
                    is_faculty_roster=is_roster,
                    inherited_label_zh=label_zh,
                    inherited_degree=degree,
                    provider=provider_name,
                )
            )

        # Prioritize direct faculty roster hits first, then department homepages
        candidates.sort(key=lambda c: 0 if c.is_faculty_roster else 1)
        return candidates

    async def search_department_and_roster(
        self,
        domain: str,
        discipline: str,
        custom_transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> StepResult[List[SearchCandidate]]:
        """
        Runs Layer 3 Search-First fallback for `(domain, discipline)`.
        Enforces ToolPolicyManager switches and monthly budget caps before making network calls.
        """
        t0 = time.monotonic()
        allowed, err_code, cost_usd = await policy_manager.reserve_search_call()
        if not allowed:
            return StepResult(
                ok=False,
                value=[],
                error_code=err_code,
                error_detail=f"L3 Search API blocked by policy ({err_code.value})",
                layer="L3_SEARCH_API",
                latency_ms=int((time.monotonic() - t0) * 1000),
                cost_usd=0.0,
            )

        query = self.build_site_query(domain, discipline)
        provider = (settings.SEARCH_PROVIDER or "serper").lower().strip()

        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, transport=custom_transport) as client:
                if provider == "serper" and settings.SERPER_API_KEY:
                    return await self._query_serper(client, query, domain, cost_usd, t0)
                if provider == "tavily" and settings.TAVILY_API_KEY:
                    return await self._query_tavily(client, query, domain, cost_usd, t0)
                if settings.SERPER_API_KEY:
                    return await self._query_serper(client, query, domain, cost_usd, t0)
                if settings.TAVILY_API_KEY:
                    return await self._query_tavily(client, query, domain, cost_usd, t0)

                # Zero-key DuckDuckGo HTML fallback when no paid API key is configured
                return await self._query_duckduckgo_html(client, query, domain, t0)
        except httpx.TimeoutException as exc:
            return StepResult(
                ok=False,
                value=[],
                error_code=ErrorCode.CONNECTION_TIMEOUT,
                error_detail=f"L3 Search API timeout: {exc}",
                layer="L3_SEARCH_API",
                latency_ms=int((time.monotonic() - t0) * 1000),
                cost_usd=cost_usd,
            )
        except Exception as exc:
            return StepResult(
                ok=False,
                value=[],
                error_code=ErrorCode.HTTP_5XX_SERVER_ERROR,
                error_detail=f"L3 Search API error: {exc}",
                layer="L3_SEARCH_API",
                latency_ms=int((time.monotonic() - t0) * 1000),
                cost_usd=cost_usd,
            )

    async def _query_serper(
        self,
        client: httpx.AsyncClient,
        query: str,
        domain: str,
        cost_usd: float,
        t0: float,
    ) -> StepResult[List[SearchCandidate]]:
        resp = await client.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": settings.SERPER_API_KEY, "Content-Type": "application/json"},
            json={"q": query, "num": 10, "gl": "cn", "hl": "zh-cn"},
        )
        latency = int((time.monotonic() - t0) * 1000)
        if resp.status_code != 200:
            return StepResult(
                ok=False,
                value=[],
                error_code=ErrorCode.HTTP_5XX_SERVER_ERROR if resp.status_code >= 500 else ErrorCode.HTTP_4XX_NOT_FOUND,
                error_detail=f"Serper returned HTTP {resp.status_code}",
                layer="L3_SEARCH_API",
                http_status=resp.status_code,
                latency_ms=latency,
                cost_usd=cost_usd,
            )
        data = resp.json()
        organic = data.get("organic") or []
        raw_items = [
            {"url": r.get("link", ""), "title": r.get("title", ""), "snippet": r.get("snippet", "")}
            for r in organic
        ]
        candidates = self._classify_and_filter_items(raw_items, domain, "serper")
        if not candidates:
            return StepResult(
                ok=False,
                value=[],
                error_code=ErrorCode.DEPT_LINK_NOT_FOUND,
                error_detail=f"Serper returned {len(organic)} hits, 0 valid for {domain}",
                layer="L3_SEARCH_API",
                http_status=200,
                latency_ms=latency,
                cost_usd=cost_usd,
            )
        return StepResult(
            ok=True,
            value=candidates,
            error_code=ErrorCode.NONE,
            layer="L3_SEARCH_API",
            http_status=200,
            latency_ms=latency,
            cost_usd=cost_usd,
        )

    async def _query_tavily(
        self,
        client: httpx.AsyncClient,
        query: str,
        domain: str,
        cost_usd: float,
        t0: float,
    ) -> StepResult[List[SearchCandidate]]:
        resp = await client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": settings.TAVILY_API_KEY,
                "query": query,
                "max_results": 10,
                "include_domains": [domain],
            },
        )
        latency = int((time.monotonic() - t0) * 1000)
        if resp.status_code != 200:
            return StepResult(
                ok=False,
                value=[],
                error_code=ErrorCode.HTTP_5XX_SERVER_ERROR if resp.status_code >= 500 else ErrorCode.HTTP_4XX_NOT_FOUND,
                error_detail=f"Tavily returned HTTP {resp.status_code}",
                layer="L3_SEARCH_API",
                http_status=resp.status_code,
                latency_ms=latency,
                cost_usd=cost_usd,
            )
        data = resp.json()
        results = data.get("results") or []
        raw_items = [
            {"url": r.get("url", ""), "title": r.get("title", ""), "snippet": r.get("content", "")}
            for r in results
        ]
        candidates = self._classify_and_filter_items(raw_items, domain, "tavily")
        if not candidates:
            return StepResult(
                ok=False,
                value=[],
                error_code=ErrorCode.DEPT_LINK_NOT_FOUND,
                error_detail=f"Tavily returned {len(results)} hits, 0 valid for {domain}",
                layer="L3_SEARCH_API",
                http_status=200,
                latency_ms=latency,
                cost_usd=cost_usd,
            )
        return StepResult(
            ok=True,
            value=candidates,
            error_code=ErrorCode.NONE,
            layer="L3_SEARCH_API",
            http_status=200,
            latency_ms=latency,
            cost_usd=cost_usd,
        )

    async def _query_duckduckgo_html(
        self,
        client: httpx.AsyncClient,
        query: str,
        domain: str,
        t0: float,
    ) -> StepResult[List[SearchCandidate]]:
        resp = await client.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": settings.CRAWLER_USER_AGENT},
        )
        latency = int((time.monotonic() - t0) * 1000)
        if resp.status_code not in (200, 202):
            return StepResult(
                ok=False,
                value=[],
                error_code=ErrorCode.HTTP_4XX_NOT_FOUND,
                error_detail=f"DuckDuckGo HTML search returned HTTP {resp.status_code}",
                layer="L3_SEARCH_API",
                http_status=resp.status_code,
                latency_ms=latency,
                cost_usd=0.0,
            )
        soup = BeautifulSoup(resp.text, "html.parser")
        raw_items: List[Dict[str, str]] = []
        for a in soup.select("a.result__a"):
            href = a.get("href", "")
            if "uddg=" in href:
                qs = parse_qs(urlparse(href).query)
                href = unquote(qs.get("uddg", [href])[0])
            title = a.get_text(" ", strip=True)
            raw_items.append({"url": href, "title": title, "snippet": ""})

        candidates = self._classify_and_filter_items(raw_items, domain, "duckduckgo")
        if not candidates:
            return StepResult(
                ok=False,
                value=[],
                error_code=ErrorCode.DEPT_LINK_NOT_FOUND,
                error_detail=f"DuckDuckGo HTML returned 0 matching URLs for {domain}",
                layer="L3_SEARCH_API",
                http_status=resp.status_code,
                latency_ms=latency,
                cost_usd=0.0,
            )
        return StepResult(
            ok=True,
            value=candidates,
            error_code=ErrorCode.NONE,
            layer="L3_SEARCH_API",
            http_status=200,
            latency_ms=latency,
            cost_usd=0.0,
        )


search_provider = SearchFirstProvider()
