"""Tree-First Site Navigation Engine: 3-Zone Extraction + Pruned BFS -> Targeted DFS + Backtracking + Serper LLM Selector."""

import json
import re
import time
import uuid
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
import httpx
from selectolax.lexbor import LexborHTMLParser

from app.core.config import settings
from app.core.llm_router import LLMRouter, llm_router
from app.core.logging import current_domain, current_job_id, get_logger
from app.core.types import ErrorCode, StepResult
from app.db.repositories import Repository
from app.schemas.entities import (
    ApiCallTraceDoc,
    SiteTreeNode,
    UniversitySiteTreeDoc,
    VerifiedRosterEntry,
    utc_now,
)
from app.schemas.filters import AdminConfig
from app.services.nav_agent import _default_playwright_fetch
from app.services.phase1_discovery import DEGREE_ZH, decode_bytes_safely
from app.services.phase2_scraper import (
    CAROUSEL_SELECTORS,
    is_root_or_index_url,
    is_same_root_domain,
    registrable_domain,
    verify_roster_html,
)

logger = get_logger("services.site_tree_builder")

SEMANTIC_NAV_SELECTORS = ("header a[href]", "nav a[href]")
DIV_NAV_SELECTORS = (".nav a[href]", "#nav a[href]", ".navbar a[href]", ".top-nav a[href]", ".menu a[href]", "#menu a[href]")
NAV_SELECTORS = (*SEMANTIC_NAV_SELECTORS, *DIV_NAV_SELECTORS)
NAV_EXCLUDE_SELECTORS = (".breadcrumb", ".crumbs", ".pagination", ".pager")
SIDEBAR_SELECTORS = ("aside a[href]", ".sidebar a[href]", ".left-menu a[href]", ".sub-nav a[href]", ".left_nav a[href]", ".side-nav a[href]")
BODY_NOISE_PATTERNS = (
    "/news", "/notice", "/events", "/login", "/intllogin", "/alumni", "/campus",
    "/careers", "/contact", "/admissions", "/admission", "/about", "/overview",
    "/xwdt", "/tzgg", "/zsjy", "/2020/", "/2021/", "/2022/", "/2023/", "/2024/", "/2025/", "/2026/",
)
SCHOOLS_DIR_KEYWORDS = ("院系设置", "学院设置", "学部院系", "机构设置", "教学单位", "schools", "colleges", "departments", "faculties")
FACULTY_BRANCH_KEYWORDS = ("师资", "教师", "导师", "在职教师", "博导", "硕导", "faculty", "people", "staff", "teachers", "supervisors")
ENGLISH_BROCHURE_PREFIXES = ("ev.", "en.", "english.", "intl.", "iso.")
BLOCKED_SUBDOMAIN_PREFIXES = (
    "stuex.", "iczu.", "iso.", "sie.", "admission.", "gs.", "hr.", "lib.", "news.", "alumni.",
)
NON_CS_COLLEGE_KEYWORDS = (
    "医学院", "法学院", "经济", "管理", "外文", "新闻", "历史", "哲学", "艺术", "体育", "农学",
    "medical", "law", "business", "shmc.",
)

DEPT_SYNONYMS: dict[str, tuple[str, ...]] = {
    "computer science": ("computer", "计算机", "计算", "cs."),
    "artificial intelligence": ("artificial intelligence", "人工智能", "智能", "ai."),
    "software engineering": ("software", "软件", "se."),
    "cyber security": ("cyber", "网络空间安全", "信息安全", "网安"),
    "electronic information": ("electronic", "电子", "信息", "ee."),
}


def is_english_brochure_host(url: str) -> bool:
    """Identifies English brochure subdomains (e.g. ev.buaa.edu.cn, en.pku.edu.cn) so Chinese portals rank higher."""
    host = urlparse(url).netloc.lower()
    return any(host.startswith(p) for p in ENGLISH_BROCHURE_PREFIXES)


def is_cs_engineering_department(department: str) -> bool:
    low = (department or "").strip().lower()
    return any(k in low for k in ("computer", "software", "artificial intelligence", "ai", "cyber", "engineering", "电子", "计算机", "软件", "人工智能"))


def is_blocked_academic_link(url: str, label: str = "", department: str = "") -> bool:
    """Blocks non-academic/exchange subdomains and non-CS colleges when targeting CS/Engineering."""
    host = urlparse(url or "").netloc.lower()
    if any(host.startswith(p) for p in BLOCKED_SUBDOMAIN_PREFIXES):
        return True
    if is_cs_engineering_department(department):
        blob = f"{label} {url}".lower()
        if any(kw in blob for kw in NON_CS_COLLEGE_KEYWORDS):
            return True
    return False


def extract_3zone_links_with_meta(
    html: str,
    base_url: str,
    root_domain: str,
    *,
    department: str = "",
) -> tuple[dict[str, list[dict[str, str]]], str]:
    """
    Extracts same-root-domain links tagged into [NAV], [SIDEBAR], and filtered [BODY] zones,
    and returns `(zones, nav_type)` where `nav_type` is 'SEMANTIC_NAV', 'DIV_BASED_NAV', or 'UNKNOWN'.
    Excludes breadcrumbs/pagination from [NAV] and strips carousels from [BODY].
    """
    tree = LexborHTMLParser(html or "")
    for excl in NAV_EXCLUDE_SELECTORS:
        for node in tree.css(excl):
            node.decompose()

    zones: dict[str, list[dict[str, str]]] = {"NAV": [], "SIDEBAR": [], "BODY": []}
    seen: set[str] = set()

    def _add(zone_name: str, a_node: Any, filter_noise: bool = False) -> bool:
        href = (a_node.attributes.get("href") or "").strip()
        if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
            return False
        abs_url = urljoin(base_url, href).split("#")[0]
        if abs_url in seen or abs_url.rstrip("/") == base_url.rstrip("/"):
            return False
        if not is_same_root_domain(abs_url, root_domain):
            return False
        low = abs_url.lower()
        if low.endswith((".pdf", ".doc", ".docx", ".xls", ".zip", ".rar", ".jpg", ".png", ".mp4")):
            return False
        if filter_noise and any(bad in low for bad in BODY_NOISE_PATTERNS):
            return False
        text = re.sub(r"\s+", " ", a_node.text(separator=" ", strip=True) or a_node.attributes.get("title") or "").strip()
        if not text:
            return False
        if is_blocked_academic_link(abs_url, text, department):
            return False
        seen.add(abs_url)
        zones[zone_name].append({"label": text[:80], "url": abs_url, "zone": zone_name})
        return True

    semantic_nav_count = 0
    for sel in SEMANTIC_NAV_SELECTORS:
        for node in tree.css(sel):
            if _add("NAV", node, filter_noise=False):
                semantic_nav_count += 1
            if len(zones["NAV"]) >= 60:
                break

    div_nav_count = 0
    for sel in DIV_NAV_SELECTORS:
        for node in tree.css(sel):
            if _add("NAV", node, filter_noise=False):
                div_nav_count += 1
            if len(zones["NAV"]) >= 60:
                break

    nav_type = "SEMANTIC_NAV" if semantic_nav_count > 0 else ("DIV_BASED_NAV" if div_nav_count > 0 else "UNKNOWN")

    for sel in SIDEBAR_SELECTORS:
        for node in tree.css(sel):
            _add("SIDEBAR", node, filter_noise=False)
            if len(zones["SIDEBAR"]) >= 50:
                break

    # Strip promotional carousels/sliders before extracting [BODY] links
    for csel in CAROUSEL_SELECTORS:
        for cnode in tree.css(csel):
            cnode.decompose()

    for node in tree.css("a[href]"):
        _add("BODY", node, filter_noise=True)
        if len(zones["BODY"]) >= 80:
            break

    return zones, nav_type


def extract_3zone_links(
    html: str,
    base_url: str,
    root_domain: str,
    *,
    department: str = "",
) -> dict[str, list[dict[str, str]]]:
    """Extracts same-root-domain links tagged into [NAV], [SIDEBAR], and filtered [BODY] zones."""
    zones, _ = extract_3zone_links_with_meta(html, base_url, root_domain, department=department)
    return zones


def format_zones_markdown(zones: dict[str, list[dict[str, str]]]) -> str:
    """Formats 3-zone links as compact Markdown to minimize LLM prompt tokens."""
    lines: list[str] = []
    for z in ("NAV", "SIDEBAR", "BODY"):
        items = zones.get(z) or []
        if not items:
            continue
        lines.append(f"### [{z}]")
        for it in items[:40]:
            lines.append(f"- [{it['label']}]({it['url']})")
    return "\n".join(lines)


def render_markdown_tree(nodes: list[SiteTreeNode]) -> str:
    """Renders compact indented Markdown tree from SiteTreeNode list."""
    lines: list[str] = []
    for n in nodes:
        indent = "  " * max(0, n.depth)
        tag = f" `{n.node_type}`" if n.node_type not in ("HOME",) else ""
        lines.append(f"{indent}- [{n.label}]({n.url}){tag}")
    return "\n".join(lines)


def _match_department_from_map(departments_map: dict[str, str], department: str) -> str | None:
    """Looks up target department in cached departments_map using EN/ZH synonyms (preferring non-brochure portals)."""
    dept_low = department.strip().lower()
    syns = DEPT_SYNONYMS.get(dept_low, (dept_low,))
    matches: list[tuple[int, str]] = []
    for label, url in departments_map.items():
        blob = f"{label} {url}".lower()
        if any(s in blob for s in syns):
            # Prefer Chinese department portals over English brochure subdomains (ev., en.)
            priority = 1 if is_english_brochure_host(url) else 10
            matches.append((priority, url))
    if not matches:
        return None
    matches.sort(key=lambda x: x[0], reverse=True)
    return matches[0][1]


def _heuristic_rank_branches(
    zones: dict[str, list[dict[str, str]]],
    department: str,
    degree: str,
    *,
    stage: str = "home",
    top_k: int = 3,
) -> list[dict[str, str]]:
    """Deterministic fallback ranker (always down-ranks English brochure subdomains ev./en. below Chinese portals)."""
    dept_low = department.strip().lower()
    dept_syns = DEPT_SYNONYMS.get(dept_low, (dept_low,))
    deg_zh = DEGREE_ZH.get(degree, "导师")
    all_links = zones["NAV"] + zones["SIDEBAR"] + zones["BODY"]
    scored: list[tuple[float, dict[str, str]]] = []

    for it in all_links:
        blob = f"{it['label']} {it['url']}".lower()
        if any(bad in blob for bad in ("/news", "/notice", "/login", "/admissions", "/alumni", "/campus")):
            continue
        score = 0.0
        if stage == "home":
            if any(k in blob for k in dept_syns):
                score += 6.0
            if any(k in blob for k in SCHOOLS_DIR_KEYWORDS):
                score += 5.0
            if any(k in blob for k in FACULTY_BRANCH_KEYWORDS):
                score += 2.5
        else:
            if any(k in blob for k in FACULTY_BRANCH_KEYWORDS):
                score += 6.0
            if deg_zh in blob or degree in blob:
                score += 3.0
            if any(k in blob for k in dept_syns):
                score += 2.0

        if score <= 0:
            continue
        if is_english_brochure_host(it["url"]):
            score -= 2.5
        if it["zone"] in ("NAV", "SIDEBAR"):
            score += 0.5
        scored.append((score, it))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:top_k]]


class SiteTreeBuilder:
    """Builds and caches pruned university site trees via Pruned BFS -> Targeted DFS + Backtracking + Serper Safety Net."""

    def __init__(
        self,
        repo: Repository,
        admin: AdminConfig | None = None,
        router: LLMRouter | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        playwright_fetcher: Any = None,
        max_depth: int = 5,
        beam_width: int = 3,
    ) -> None:
        self.repo = repo
        self.admin = admin or AdminConfig()
        self.router = router or llm_router
        self.transport = transport
        self.playwright_fetcher = playwright_fetcher or _default_playwright_fetch
        self.max_depth = max_depth
        self.beam_width = beam_width

    async def _check_robots(self, client: httpx.AsyncClient, url: str) -> bool:
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
            logger.warning("tree_robots_check_failed", robots_url=robots_url, error=str(exc))
            return True

    async def _fetch_page(self, client: httpx.AsyncClient, url: str) -> tuple[int, str, str]:
        try:
            resp = await client.get(
                url,
                headers={"User-Agent": settings.CRAWL_USER_AGENT},
                follow_redirects=True,
                timeout=15.0,
            )
            st, final_u, html = resp.status_code, str(resp.url), decode_bytes_safely(resp.content)
        except Exception as exc:
            logger.warning("tree_http_fetch_failed", url=url, error=str(exc))
            st, final_u, html = 0, url, ""

        if st in (403, 412, 521) and self.admin.enable_playwright and self.playwright_fetcher is not None:
            try:
                st, final_u, html = await self.playwright_fetcher(url)
                logger.info("tree_playwright_waf_recovered", url=url, status=st)
            except Exception as exc:
                logger.warning("tree_playwright_waf_failed", url=url, error=str(exc))
        return st, final_u, html

    async def _llm_select_branches(
        self,
        url: str,
        zones: dict[str, list[dict[str, str]]],
        department: str,
        degree: str,
        *,
        stage: str,
        top_k: int = 3,
    ) -> list[dict[str, str]]:
        """Uses 3-Tier LLM Router (Colab Qwen -> DeepSeek -> Gemini) to prune irrelevant branches; falls back to heuristic."""
        md_links = format_zones_markdown(zones)
        if not md_links:
            return []

        goal = (
            f"Find the '{department}' department or the Schools/Colleges directory (院系设置) that leads to '{department}'."
            if stage == "home"
            else f"Find the Faculty / Supervisors roster page (师资队伍 / 教师名录 / {DEGREE_ZH.get(degree, '导师')}) for '{department}'."
        )
        prompt = (
            f"Current page: {url}\nGoal: {goal}\n"
            f"Prefer official Chinese department/faculty portals over English brochure subdomains (ev., en.).\n"
            f"Ignore News, Admissions, Alumni, Campus Life, Careers, Login.\n\n"
            f"Links:\n{md_links}\n\n"
            f'Return JSON ONLY: {{"branches": [{{"label": str, "url": str, "zone": "NAV"|"SIDEBAR"|"BODY"}}]}} '
            f"(max {top_k} ranked best-first)."
        )

        llm_res = await self.router.complete(
            [{"role": "user", "content": prompt}],
            json_mode=True,
            max_tokens=300,
            use_colab=self.admin.enable_colab_bridge,
            transport=self.transport,
        )
        if llm_res.ok:
            try:
                m = re.search(r"\{.*\}", llm_res.data["content"], re.S)
                parsed = json.loads(m.group(0)) if m else {}
                raw_branches = parsed.get("branches") or []
                valid_urls = {it["url"]: it for z in zones.values() for it in z}
                chosen: list[dict[str, str]] = []
                for b in raw_branches:
                    bu = str(b.get("url") or "").strip()
                    if bu in valid_urls and bu not in {c["url"] for c in chosen}:
                        chosen.append(valid_urls[bu])
                if chosen:
                    # Down-rank English brochure subdomains below Chinese portals
                    chosen.sort(key=lambda x: 1 if is_english_brochure_host(x["url"]) else 0)
                    return chosen[:top_k]
            except Exception as exc:
                logger.warning("tree_llm_branch_parse_failed", url=url, error=str(exc))

        return _heuristic_rank_branches(zones, department, degree, stage=stage, top_k=top_k)

    async def _serper_llm_fallback(
        self,
        client: httpx.AsyncClient,
        domain: str,
        department: str,
        degree: str,
    ) -> StepResult:
        """Safety Net: bilingual Serper search -> LLM Selector ranks top 3 -> Deterministic Roster Verification Gate."""
        if not self.admin.enable_serper or not settings.SERPER_API_KEY:
            return StepResult.fail(ErrorCode.HTTP_ERROR, "Serper disabled or API key unset.")

        deg_zh = DEGREE_ZH.get(degree, "导师")
        dept_syns = DEPT_SYNONYMS.get(department.strip().lower(), (department,))
        zh_dept = next((s for s in dept_syns if any("\u4e00" <= c <= "\u9fff" for c in s)), department)
        query = f'site:{domain} ("{department}" OR {zh_dept}) (faculty OR people OR 师资队伍 OR 教师名录 OR {deg_zh})'

        try:
            t0 = time.perf_counter()
            req_body = {"q": query, "num": 10}
            resp = await client.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": settings.SERPER_API_KEY, "Content-Type": "application/json"},
                json=req_body,
                timeout=12.0,
            )
            lat_ms = int((time.perf_counter() - t0) * 1000)
            if resp.status_code != 200:
                st_label = "auth_error_401_403" if resp.status_code in (401, 403) else ("rate_limited_429" if resp.status_code == 429 else f"http_error_{resp.status_code}")
                await self.repo.insert_api_call_trace(
                    ApiCallTraceDoc(
                        trace_id=f"tr_{uuid.uuid4().hex[:12]}",
                        job_id=current_job_id.get() or "",
                        domain=current_domain.get() or domain,
                        stage="serper_fallback",
                        provider="serper",
                        model="google.serper.dev/search",
                        tier=0,
                        status=st_label,
                        http_status=resp.status_code,
                        error_detail=f"Serper returned HTTP {resp.status_code}: {resp.text[:240]}",
                        latency_ms=lat_ms,
                        request_payload=json.dumps(req_body, ensure_ascii=False),
                        response_payload=resp.text[:8000],
                    )
                )
                return StepResult.fail(ErrorCode.HTTP_ERROR, f"Serper returned HTTP {resp.status_code}")
            await self.repo.insert_api_call_trace(
                ApiCallTraceDoc(
                    trace_id=f"tr_{uuid.uuid4().hex[:12]}",
                    job_id=current_job_id.get() or "",
                    domain=current_domain.get() or domain,
                    stage="serper_fallback",
                    provider="serper",
                    model="google.serper.dev/search",
                    tier=0,
                    status="ok",
                    http_status=200,
                    error_detail="",
                    latency_ms=lat_ms,
                    request_payload=json.dumps(req_body, ensure_ascii=False),
                    response_payload=resp.text[:8000],
                )
            )
            organic = [
                item for item in (resp.json().get("organic") or [])[:10]
                if item.get("link")
                and is_same_root_domain(item["link"], domain)
                and not is_blocked_academic_link(item["link"], item.get("title", ""), department)
            ]
        except Exception as exc:
            await self.repo.insert_api_call_trace(
                ApiCallTraceDoc(
                    trace_id=f"tr_{uuid.uuid4().hex[:12]}",
                    job_id=current_job_id.get() or "",
                    domain=current_domain.get() or domain,
                    stage="serper_fallback",
                    provider="serper",
                    model="google.serper.dev/search",
                    tier=0,
                    status="timeout" if isinstance(exc, httpx.TimeoutException) else "connection_error",
                    http_status=None,
                    error_detail=f"Serper request failed: {exc}",
                    latency_ms=0,
                    request_payload=json.dumps({"q": query, "num": 10}, ensure_ascii=False),
                    response_payload="",
                )
            )
            return StepResult.fail(ErrorCode.HTTP_TIMEOUT, f"Serper request failed: {exc}")

        if not organic:
            return StepResult.fail(ErrorCode.NO_LINKS_FOUND, "Serper returned 0 same-domain results.")

        # Ask LLM Selector to reject admissions/news/brochures and rank top 3 real faculty rosters
        candidates_md = "\n".join(
            f"- Title: {it.get('title', '')} | URL: {it['link']} | Snippet: {it.get('snippet', '')[:120]}"
            for it in organic
        )
        prompt = (
            f"Select up to 3 URLs most likely to be the REAL faculty/supervisor roster list for '{department}' ({degree}) at {domain}.\n"
            f"REJECT admissions, news, overview brochures, login pages, and English brochure subdomains (ev., en.) when Chinese faculty lists exist.\n\n"
            f"{candidates_md}\n\n"
            f'Return JSON ONLY: {{"urls": ["url1", "url2", "url3"]}}'
        )
        ranked_urls: list[str] = []
        llm_res = await self.router.complete(
            [{"role": "user", "content": prompt}],
            json_mode=True,
            max_tokens=200,
            use_colab=self.admin.enable_colab_bridge,
            transport=self.transport,
        )
        if llm_res.ok:
            try:
                m = re.search(r"\{.*\}", llm_res.data["content"], re.S)
                parsed = json.loads(m.group(0)) if m else {}
                allowed = {it["link"] for it in organic}
                ranked_urls = [u for u in (parsed.get("urls") or []) if u in allowed][:3]
            except Exception as exc:
                logger.warning("serper_llm_selector_parse_failed", domain=domain, error=str(exc))

        if not ranked_urls:
            organic.sort(key=lambda it: 1 if is_english_brochure_host(it["link"]) else 0)
            ranked_urls = [it["link"] for it in organic[:3]]

        for cand_url in ranked_urls:
            st, final_u, html = await self._fetch_page(client, cand_url)
            if st != 200:
                continue
            ok_gate, profiles = verify_roster_html(html, final_u, root_domain=domain, min_profiles=3)
            logger.info("serper_gate_check", domain=domain, url=final_u, passed=ok_gate, profile_count=len(profiles))
            if ok_gate:
                return StepResult.success({
                    "roster_url": final_u,
                    "department_url": final_u,
                    "strategy": "SERPER_LLM_FALLBACK",
                    "candidate_profile_count": len(profiles),
                    "hops": 1,
                })

        return StepResult.fail(ErrorCode.VERIFICATION_FAILED, "No Serper candidate passed >=3 profile Verification Gate.")

    async def build_and_find_roster(
        self,
        domain: str,
        department: str,
        degree: str,
        *,
        force_refresh: bool = False,
    ) -> StepResult:
        """
        Tree-First Discovery:
        Step 0: DB Tree Cache (verified_rosters or departments_map jump)
        Hop 0:  Pruned BFS on homepage (3-zone extraction -> top 3 branches)
        Hop 1-4: Targeted DFS + Schools/Colleges departments_map harvesting + Backtracking + Deterministic Gate (>=3 profiles)
        Safety Net: Serper + LLM Selector + Deterministic Gate
        """
        clean_dom = registrable_domain(domain)
        roster_key = f"{department.strip()}::{degree}"
        root_url = f"https://www.{clean_dom}"

        tree = await self.repo.get_site_tree(clean_dom)
        if tree is None:
            tree = UniversitySiteTreeDoc(domain=clean_dom, root_url=root_url)

        # Step 0A: Verified roster cache hit ($0)
        if not force_refresh and roster_key in tree.verified_rosters:
            cached = tree.verified_rosters[roster_key]
            logger.info("tree_cache_hit", domain=clean_dom, roster_key=roster_key, roster_url=cached.roster_url)
            return StepResult.success({
                "roster_url": cached.roster_url,
                "department_url": cached.department_url or cached.roster_url,
                "strategy": "TREE_CACHE",
                "candidate_profile_count": cached.candidate_profile_count,
                "hops": 0,
                "tree": tree,
            })

        nodes_by_url: dict[str, SiteTreeNode] = {n.url: n for n in tree.nodes}

        def _record_node(
            url: str,
            label: str,
            zone: str,
            depth: int,
            node_type: str,
            parent_url: str | None = None,
        ) -> None:
            if url not in nodes_by_url:
                nodes_by_url[url] = SiteTreeNode(
                    url=url, label=label, zone=zone, depth=depth, node_type=node_type, parent_url=parent_url  # type: ignore[arg-type]
                )
            else:
                nodes_by_url[url].node_type = node_type  # type: ignore[arg-type]
            if parent_url and parent_url in nodes_by_url and url not in nodes_by_url[parent_url].children:
                nodes_by_url[parent_url].children.append(url)

        async with httpx.AsyncClient(transport=self.transport) as client:
            if not await self._check_robots(client, root_url):
                return StepResult.fail(ErrorCode.ROBOTS_DISALLOWED, f"robots.txt disallows crawling {root_url}")

            visited: set[str] = set()
            hops_taken = 0

            async def _dfs(
                cur_url: str,
                cur_label: str,
                cur_zone: str,
                depth: int,
                parent_url: str | None,
                dept_url_seen: str | None,
            ) -> dict[str, Any] | None:
                nonlocal hops_taken
                if depth > self.max_depth or cur_url in visited:
                    return None
                visited.add(cur_url)
                hops_taken += 1

                st, final_u, html = await self._fetch_page(client, cur_url)
                if st != 200 or not html:
                    _record_node(cur_url, cur_label, cur_zone, depth, "DEAD_END", parent_url)
                    return None

                zones, page_nav_type = extract_3zone_links_with_meta(html, final_u, clean_dom, department=department)
                if tree.nav_type == "UNKNOWN" and page_nav_type != "UNKNOWN":
                    tree.nav_type = page_nav_type  # type: ignore[assignment]
                logger.info(
                    "tree_zones_extracted",
                    domain=clean_dom,
                    depth=depth,
                    url=final_u,
                    nav_type=page_nav_type,
                    nav=len(zones["NAV"]),
                    sidebar=len(zones["SIDEBAR"]),
                    body=len(zones["BODY"]),
                )

                # Classify page structure BEFORE running Deterministic Roster Gate
                low_page = f"{cur_label} {final_u} {html[:3000]}".lower()
                is_schools_dir = any(k in low_page for k in SCHOOLS_DIR_KEYWORDS) and len(zones["BODY"]) >= 4
                is_root_idx = is_root_or_index_url(final_u)
                is_dept_entry = (
                    not is_schools_dir
                    and (
                        is_root_idx
                        or (
                            dept_url_seen is None
                            and any(s in low_page for s in DEPT_SYNONYMS.get(department.lower(), (department.lower(),)))
                            and not any(fk in f"{cur_label} {final_u}".lower() for fk in FACULTY_BRANCH_KEYWORDS)
                        )
                    )
                )
                inferred_node_type = "SCHOOLS_DIR" if is_schools_dir else ("DEPT_HOME" if is_dept_entry else "FACULTY_SECTION")

                # NEVER allow HOME, SCHOOLS_DIR, DEPT_HOME, or root/index URLs to pass verify_roster_html
                ok_gate, profiles = verify_roster_html(
                    html,
                    final_u,
                    root_domain=clean_dom,
                    min_profiles=3,
                    node_type=inferred_node_type,
                )
                logger.info("tree_dfs_gate", domain=clean_dom, depth=depth, url=final_u, node_type=inferred_node_type, passed=ok_gate, profiles=len(profiles))
                if ok_gate:
                    _record_node(final_u, cur_label, cur_zone, depth, "VERIFIED_ROSTER", parent_url)
                    return {
                        "roster_url": final_u,
                        "department_url": dept_url_seen or final_u,
                        "strategy": "TREE_DFS",
                        "candidate_profile_count": len(profiles),
                        "hops": hops_taken,
                    }

                # Detect Schools/Colleges directory (院系设置) and harvest ALL departments into departments_map
                if is_schools_dir:
                    _record_node(final_u, cur_label, cur_zone, depth, "SCHOOLS_DIR", parent_url)
                    for b_link in zones["BODY"]:
                        tree.departments_map[b_link["label"]] = b_link["url"]
                    logger.info("tree_departments_mapped", domain=clean_dom, count=len(tree.departments_map))

                    direct_dept = _match_department_from_map(tree.departments_map, department)
                    if direct_dept and direct_dept not in visited:
                        hit = await _dfs(direct_dept, department, "BODY", depth + 1, final_u, direct_dept)
                        if hit:
                            return hit
                else:
                    _record_node(final_u, cur_label, cur_zone, depth, inferred_node_type, parent_url)
                    if inferred_node_type == "DEPT_HOME" and not dept_url_seen:
                        dept_url_seen = final_u

                if depth >= self.max_depth:
                    _record_node(final_u, cur_label, cur_zone, depth, "DEAD_END", parent_url)
                    return None

                next_branches = await self._llm_select_branches(
                    final_u, zones, department, degree, stage="dept", top_k=2
                )
                for nb in next_branches:
                    hit = await _dfs(nb["url"], nb["label"], nb["zone"], depth + 1, final_u, dept_url_seen)
                    if hit:
                        return hit

                logger.info("tree_dfs_backtrack", domain=clean_dom, depth=depth, dead_end_url=final_u)
                return None

            winner: dict[str, Any] | None = None

            # Step 0B: Jump straight to Hop 2 if departments_map already has the target department URL
            cached_dept_url = _match_department_from_map(tree.departments_map, department)
            if cached_dept_url and not force_refresh:
                logger.info("tree_dept_map_jump", domain=clean_dom, dept_url=cached_dept_url)
                winner = await _dfs(cached_dept_url, department, "BODY", 2, root_url, cached_dept_url)

            # Hop 0: Pruned BFS on homepage -> Top 3 ranked branches -> DFS with backtracking
            if not winner:
                st0, final0, html0 = await self._fetch_page(client, root_url)
                if st0 == 200 and html0:
                    _record_node(final0, clean_dom, "NAV", 0, "HOME", None)
                    zones0, home_nav_type = extract_3zone_links_with_meta(html0, final0, clean_dom, department=department)
                    tree.nav_type = home_nav_type  # type: ignore[assignment]
                    logger.info(
                        "tree_hop0_bfs",
                        domain=clean_dom,
                        nav_type=home_nav_type,
                        nav=len(zones0["NAV"]),
                        sidebar=len(zones0["SIDEBAR"]),
                        body=len(zones0["BODY"]),
                    )
                    top_branches = await self._llm_select_branches(
                        final0, zones0, department, degree, stage="home", top_k=self.beam_width
                    )
                    for idx, br in enumerate(top_branches, start=1):
                        logger.info("tree_dfs_branch_start", domain=clean_dom, branch_rank=idx, label=br["label"], url=br["url"])
                        winner = await _dfs(br["url"], br["label"], br["zone"], 1, final0, None)
                        if winner:
                            break

            # Safety Net: Serper + LLM Selector Fallback
            if not winner:
                serp_res = await self._serper_llm_fallback(client, clean_dom, department, degree)
                if serp_res.ok:
                    winner = serp_res.data
                    _record_node(winner["roster_url"], f"{department} Roster (Serper)", "BODY", 1, "VERIFIED_ROSTER", root_url)

            # Persist pruned tree (even if no winner, save departments_map & pruned skeleton)
            tree.nodes = list(nodes_by_url.values())
            tree.markdown_tree = render_markdown_tree(tree.nodes)
            if winner:
                tree.verified_rosters[roster_key] = VerifiedRosterEntry(
                    roster_url=winner["roster_url"],
                    department_url=winner.get("department_url"),
                    strategy=winner["strategy"],
                    candidate_profile_count=winner.get("candidate_profile_count", 0),
                    verified_at=utc_now(),
                )
            await self.repo.upsert_site_tree(tree)

            if winner:
                winner["tree"] = tree
                return StepResult.success(winner)

        return StepResult.fail(ErrorCode.VERIFICATION_FAILED, f"Tree BFS/DFS and Serper fallback found no verified roster (>=3 profiles) for {clean_dom}.")
