"""Phase 1 Multi-Strategy Discovery: DB Hit -> Strategy A (Serper) -> B (Direct+NLP) -> C (Playwright) -> D (Nav Agent)."""

import re
from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
from charset_normalizer import from_bytes
import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.core.types import ErrorCode, StepResult
from app.db.repositories import Repository
from app.schemas.entities import NeedsReviewDoc, UniversityDeptDoc
from app.schemas.filters import AdminConfig
from app.services.colab_client import ColabClient, colab_client
from app.services.nav_agent import NavigationAgent, _default_playwright_fetch, extract_visible_links

logger = get_logger("services.phase1_discovery")

DEGREE_ZH = {
    "masters": "硕士生导师",
    "phd": "博士生导师",
    "both": "研究生导师",
}

FACULTY_KEYWORDS = ("师资", "导师", "教师", "博导", "硕导", "faculty", "professor", "supervisor", "people", "staff")
REJECT_PAGE_KEYWORDS = ("统一身份认证", "cas login", "新闻中心", "本科招生", "sign in to continue")
DEPT_KEYWORDS = ("计算机", "人工智能", "软件", "信息", "电子", "computer", "ai", "software", "cyber", "学院", "school", "department")


def decode_bytes_safely(content: bytes) -> str:
    """Decodes UTF-8 or GB18030/GBK HTML bytes cleanly using charset-normalizer."""
    if not content:
        return ""
    best = from_bytes(content).best()
    if best is not None:
        return str(best)
    for enc in ("utf-8", "gb18030"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def keyword_score_links(query: str, links: list[dict[str, str]], top_k: int = 3) -> list[dict[str, Any]]:
    """Deterministic CPU fallback scorer when Colab GPU bridge is offline or disabled."""
    q_tokens = [t.lower() for t in re.split(r"[\s/,]+", query) if len(t) > 1]
    scored = []
    for lk in links:
        blob = f"{lk.get('text', '')} {lk.get('href', '')}".lower()
        score = 0.0
        for kw in FACULTY_KEYWORDS:
            if kw in blob:
                score += 3.0
        for kw in DEPT_KEYWORDS:
            if kw in blob:
                score += 2.0
        for tok in q_tokens:
            if tok in blob:
                score += 1.5
        if score > 0:
            scored.append({"text": lk["text"], "href": lk["href"], "score": round(score, 2)})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def is_valid_faculty_page(status_code: int, html: str, url: str) -> bool:
    """Verification Gate: confirms HTTP 200 + faculty keyword presence and rejects login/news pages."""
    if status_code != 200 or not html:
        return False
    low = (html[:12000] + " " + url).lower()
    if any(bad in low for bad in REJECT_PAGE_KEYWORDS):
        return False
    return any(kw in low for kw in FACULTY_KEYWORDS)


class Phase1DiscoveryService:
    """Orchestrates permanent DB check and Strategies A -> B -> C -> D with strict robots.txt compliance."""

    def __init__(
        self,
        repo: Repository,
        admin: AdminConfig | None = None,
        colab: ColabClient | None = None,
        nav_agent: NavigationAgent | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        playwright_fetcher: Any = None,
    ) -> None:
        self.repo = repo
        self.admin = admin or AdminConfig()
        self.colab = colab or colab_client
        self.nav_agent = nav_agent or NavigationAgent()
        self.transport = transport
        self.playwright_fetcher = playwright_fetcher or _default_playwright_fetch

    async def _check_robots_allowed(self, client: httpx.AsyncClient, url: str) -> bool:
        p = urlparse(url)
        robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
        try:
            resp = await client.get(robots_url, timeout=8.0)
            if resp.status_code != 200:
                return True
            rp = RobotFileParser()
            rp.parse(decode_bytes_safely(resp.content).splitlines())
            return rp.can_fetch(settings.CRAWL_USER_AGENT, url)
        except Exception as exc:
            logger.warning("robots_check_failed", robots_url=robots_url, error=str(exc))
            return True

    async def _http_get(self, client: httpx.AsyncClient, url: str) -> tuple[int, str, str]:
        resp = await client.get(
            url,
            headers={"User-Agent": settings.CRAWL_USER_AGENT},
            follow_redirects=True,
            timeout=15.0,
        )
        return resp.status_code, str(resp.url), decode_bytes_safely(resp.content)

    async def _strategy_a_serper(
        self,
        client: httpx.AsyncClient,
        domain: str,
        department: str,
        degree: str,
    ) -> StepResult:
        """Strategy A: Search-First via Serper.dev using bilingual EN + ZH site:{domain} query."""
        if not self.admin.enable_serper or not settings.SERPER_API_KEY:
            return StepResult.fail(ErrorCode.HTTP_ERROR, "Serper disabled or API key unset.")

        deg_zh = DEGREE_ZH.get(degree, "导师")
        query = f'site:{domain} "{department}" ({degree} OR {deg_zh}) (faculty OR supervisor OR 师资)'
        try:
            resp = await client.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": settings.SERPER_API_KEY, "Content-Type": "application/json"},
                json={"q": query, "num": 5},
                timeout=12.0,
            )
            if resp.status_code != 200:
                return StepResult.fail(ErrorCode.HTTP_ERROR, f"Serper HTTP {resp.status_code}")
            organic = resp.json().get("organic", [])[:3]
        except Exception as exc:
            return StepResult.fail(ErrorCode.HTTP_TIMEOUT, f"Serper failed: {exc}")

        for item in organic:
            cand_url = item.get("link", "")
            if not cand_url:
                continue
            try:
                st, final_u, html = await self._http_get(client, cand_url)
                if is_valid_faculty_page(st, html, final_u):
                    return StepResult.success({
                        "faculty_roster_url": final_u,
                        "department_url": final_u,
                        "parent_url": f"https://www.{domain}",
                        "navigation_path": [{"strategy": "SEARCH_FIRST", "query": query, "url": final_u}],
                    })
            except Exception as exc:
                logger.warning("serper_candidate_fetch_failed", url=cand_url, error=str(exc))
                continue

        return StepResult.fail(ErrorCode.VERIFICATION_FAILED, "No Serper candidates passed Verification Gate.")

    async def _rank_links(self, query: str, links: list[dict[str, str]]) -> list[dict[str, Any]]:
        if self.admin.enable_colab_bridge and self.colab.base_url:
            res = await self.colab.score_links(query, links, model="minilm", top_k=3, transport=self.transport)
            if res.ok and res.data.get("results"):
                return res.data["results"]
        return keyword_score_links(query, links, top_k=3)

    async def _strategy_b_and_c_direct(
        self,
        client: httpx.AsyncClient,
        domain: str,
        department: str,
        degree: str,
    ) -> StepResult:
        """Strategy B (Direct httpx + NLP/keyword link scoring, max 2 hops) + Strategy C (Playwright on WAF/JS-empty)."""
        home_url = f"https://www.{domain}"
        allowed = await self._check_robots_allowed(client, home_url)
        if not allowed:
            return StepResult.fail(ErrorCode.ROBOTS_DISALLOWED, f"robots.txt disallows crawling {home_url}")

        nav_path: list[dict[str, Any]] = []
        used_playwright = False
        try:
            st, cur_url, html = await self._http_get(client, home_url)
        except Exception as exc:
            st, cur_url, html = 0, home_url, ""
            nav_path.append({"url": home_url, "error": str(exc)})

        links = extract_visible_links(html, cur_url) if st == 200 else []

        # Strategy C: Playwright render fallback ONLY on WAF (403/412/521) or JS-empty page
        if (st in (403, 412, 521) or (st == 200 and len(links) == 0)) and self.admin.enable_playwright:
            if self.playwright_fetcher is not None:
                try:
                    st, cur_url, html = await self.playwright_fetcher(home_url)
                    links = extract_visible_links(html, cur_url)
                    used_playwright = True
                    nav_path.append({"strategy": "PLAYWRIGHT_FALLBACK", "url": cur_url, "links": len(links)})
                except Exception as exc:
                    return StepResult.fail(ErrorCode.PLAYWRIGHT_ERROR, f"Playwright fallback failed: {exc}")

        if st != 200 or not links:
            code = ErrorCode.WAF_BLOCKED if st in (403, 412, 521) else ErrorCode.NO_LINKS_FOUND
            return StepResult.fail(code, f"Could not extract links from {home_url} (HTTP {st})")

        query = f"{department} {degree} {DEGREE_ZH.get(degree, '')} faculty supervisor 师资"

        # Hop 1 -> Hop 2
        top_hop1 = await self._rank_links(query, links)
        for cand in top_hop1[:3]:
            c_url = cand["href"]
            nav_path.append({"hop": 1, "from": cur_url, "to": c_url, "score": cand.get("score")})
            try:
                st1, final1, html1 = await self._http_get(client, c_url)
            except Exception as exc:
                logger.warning("serper_candidate_fetch_failed", url=cand_url, error=str(exc))
                continue
            if is_valid_faculty_page(st1, html1, final1):
                return StepResult.success({
                    "faculty_roster_url": final1,
                    "department_url": final1,
                    "parent_url": cur_url,
                    "winning_strategy": "PLAYWRIGHT_FALLBACK" if used_playwright else "DIRECT_CRAWL",
                    "navigation_path": nav_path,
                })
            # Hop 2 inside department page
            hop2_links = extract_visible_links(html1, final1)
            top_hop2 = await self._rank_links(f"faculty supervisor 师资 导师 {DEGREE_ZH.get(degree, '')}", hop2_links)
            for cand2 in top_hop2[:2]:
                c2_url = cand2["href"]
                nav_path.append({"hop": 2, "from": final1, "to": c2_url, "score": cand2.get("score")})
                try:
                    st2, final2, html2 = await self._http_get(client, c2_url)
                except Exception:
                    continue
                if is_valid_faculty_page(st2, html2, final2):
                    return StepResult.success({
                        "faculty_roster_url": final2,
                        "department_url": final1,
                        "parent_url": cur_url,
                        "winning_strategy": "PLAYWRIGHT_FALLBACK" if used_playwright else "DIRECT_CRAWL",
                        "navigation_path": nav_path,
                    })

        return StepResult.fail(ErrorCode.VERIFICATION_FAILED, "Direct crawl could not verify a faculty roster page.")

    async def discover(self, domain: str, department: str, degree: str) -> StepResult:
        """Executes full Phase 1 discovery for (domain, department, degree) and persists permanently."""
        clean_domain = domain.lower().strip()

        # 0. Permanent DB Check ($0, 0 HTTP calls)
        existing = await self.repo.get_department_doc(clean_domain, department, degree)
        if existing and existing.status == "COMPLETE" and existing.faculty_roster_url:
            logger.info("phase1_db_hit", domain=clean_domain, department=department, degree=degree)
            return StepResult.success(existing)

        async with httpx.AsyncClient(transport=self.transport) as client:
            # Strategy A: Search-First (Serper)
            res_a = await self._strategy_a_serper(client, clean_domain, department, degree)
            if res_a.ok:
                doc = UniversityDeptDoc(
                    domain=clean_domain,
                    department=department,
                    degree=degree,  # type: ignore[arg-type]
                    department_url=res_a.data["department_url"],
                    faculty_roster_url=res_a.data["faculty_roster_url"],
                    parent_url=res_a.data["parent_url"],
                    winning_strategy="SEARCH_FIRST",
                    navigation_path=res_a.data["navigation_path"],
                    status="COMPLETE",
                )
                await self.repo.upsert_department_doc(doc)
                return StepResult.success(doc)

            # Strategy B + C: Direct Crawl + Link Scoring (+ Playwright WAF/JS fallback)
            res_bc = await self._strategy_b_and_c_direct(client, clean_domain, department, degree)
            if res_bc.ok:
                doc = UniversityDeptDoc(
                    domain=clean_domain,
                    department=department,
                    degree=degree,  # type: ignore[arg-type]
                    department_url=res_bc.data["department_url"],
                    faculty_roster_url=res_bc.data["faculty_roster_url"],
                    parent_url=res_bc.data["parent_url"],
                    winning_strategy=res_bc.data["winning_strategy"],
                    navigation_path=res_bc.data["navigation_path"],
                    status="COMPLETE",
                )
                await self.repo.upsert_department_doc(doc)
                return StepResult.success(doc)

            # Never bypass robots.txt — route straight to needs_review
            if res_bc.error_code == ErrorCode.ROBOTS_DISALLOWED.value:
                await self._record_failure(clean_domain, department, degree, res_bc.error_code, res_bc.detail or "")
                return res_bc

            # Strategy D: Last-Resort Navigation Agent
            if self.admin.enable_agent_fallback:
                res_d = await self.nav_agent.navigate(f"https://www.{clean_domain}", clean_domain, department, degree)
                if res_d.ok:
                    doc = UniversityDeptDoc(
                        domain=clean_domain,
                        department=department,
                        degree=degree,  # type: ignore[arg-type]
                        department_url=res_d.data["faculty_roster_url"],
                        faculty_roster_url=res_d.data["faculty_roster_url"],
                        parent_url=f"https://www.{clean_domain}",
                        winning_strategy="NAV_AGENT",
                        navigation_path=res_d.data.get("navigation_path", []),
                        status="COMPLETE",
                    )
                    await self.repo.upsert_department_doc(doc)
                    return StepResult.success(doc)
                err_code = res_d.error_code or ErrorCode.AGENT_FAILED.value
                detail = res_d.detail or "Navigation agent failed."
            else:
                err_code = res_bc.error_code or ErrorCode.VERIFICATION_FAILED.value
                detail = f"Strategies A/B/C failed and enable_agent_fallback=False ({res_bc.detail})"

        await self._record_failure(clean_domain, department, degree, err_code, detail)
        return StepResult.fail(err_code, detail)

    async def _record_failure(self, domain: str, department: str, degree: str, error_code: str, detail: str) -> None:
        doc = UniversityDeptDoc(
            domain=domain,
            department=department,
            degree=degree,  # type: ignore[arg-type]
            winning_strategy="NONE",
            status="NEEDS_REVIEW",
            error_code=error_code,
        )
        await self.repo.upsert_department_doc(doc)
        await self.repo.add_needs_review(
            NeedsReviewDoc(
                domain=domain,
                url=f"https://www.{domain}",
                stage="phase1_discovery",
                error_code=error_code,
                detail=detail,
                payload={"department": department, "degree": degree},
            )
        )
