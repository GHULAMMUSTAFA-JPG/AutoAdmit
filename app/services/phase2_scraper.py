"""Phase 2A: Main-body-only profile link extractor, Deterministic Roster Verification Gate, polite crawler & Clean Markdown."""

import asyncio
import hashlib
import random
import re
import time
import uuid
from typing import Any
from urllib.parse import urljoin, urlparse
import httpx
from markdownify import markdownify as md_convert
from selectolax.lexbor import LexborHTMLParser

from app.core.config import settings
from app.core.logging import current_domain, current_job_id, get_logger
from app.core.types import ErrorCode, StepResult
from app.db.repositories import Repository
from app.schemas.entities import HttpFetchTraceDoc, PageSnapshotDoc, Phase2LinkAuditDoc
from app.schemas.filters import AdminConfig
from app.services.colab_client import ColabClient, colab_client
from app.services.nav_agent import _default_playwright_fetch
from app.services.phase1_discovery import decode_bytes_safely

logger = get_logger("services.phase2_scraper")

SURNAMES = set(
    "王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤常温康施文牛樊葛邢安齐易乔伍庞颜倪庄聂章鲁岳翟殷詹申欧耿关兰焦俞左柳甘祝包宁尚符舒阮柯纪梅童凌毕单季裴霍涂成苗谷盛曲翁冉骆蓝路游辛靳管柴蒙鲍华喻祁蒲房滕屈饶解牟艾尤阳时穆农司卓古吉缪简车项连芦麦褚娄窦戚岑景党宫费卜冷晏席卫米柏宗瞿桂全佟应臧闵苟邬边卞姬师阚敖查储谌笪刁凤伏傅盖海杭赫洪花居鞠赖郎劳乐厉利廉麻满茅明皮平强裘阙荣容芮桑沙商束帅双水松谈危温闻巫奚习鲜萧宣荀阎印雍虞宇郁元云甄诸竺"
)
CJK_NAME_RE = re.compile(r"^[\u4e00-\u9fa5·]{2,4}$")
EN_NAME_RE = re.compile(r"^[A-Z][a-z]+(?: [A-Z][a-z\-]+){1,2}$")
TITLE_BRACKET_RE = re.compile(r"[\(\（\[【].*?[\)\）\]】]|教授|副教授|研究员|副研究员|博导|硕导|博士|老师|Prof\.|Dr\.")
ROLE_PREFIX_RE = re.compile(
    r"^(?:导师简介|教师简介|个人简介|个人主页|专家简介)\s*(?:——|—|-|:|：)+\s*"
)
INLINE_ROSTER_TITLE_WORDS = ("师资队伍", "硕士生导师", "博士生导师", "研究生导师", "教师名录", "导师介绍", "导师队伍", "faculty", "supervisors")
INLINE_FACULTY_RANK_WORDS = ("教授", "副教授", "讲师", "研究员", "硕士生导师", "博士生导师", "博导", "硕导")
DETAIL_ANCHOR_TEXTS = {"查看详情", "详情", "个人主页", "view details", "details", "profile", "more"}
NEXT_PAGE_TEXTS = {"下一页", "下页", "next", ">", "›", "»"}

# Strict URL/anchor denylist rejecting non-profile pages
NON_PROFILE_URL_DENYLIST = (
    "/news", "/notice", "/events", "/admissions", "/admission", "/application",
    "/about", "/about_us", "/overview", "/research", "/academics", "/global",
    "/careers", "/career", "/login", "/intllogin", "/open_position",
    "/internationalization", "/schools___colleges/", "/campus", "/alumni",
    "/contact", "/download", "/xwdt", "/tzgg", "/zsjy", "/kygk",
    "publications/", "news/", "notice/",
)
NON_PROFILE_ANCHOR_DENYLIST = (
    "about us", "about", "news", "notice", "events", "admissions", "overview",
    "research", "academics", "global", "careers", "login", "sign in", "contact",
    "首页", "学院概况", "新闻动态", "通知公告", "招生信息", "科学研究", "人才培养",
    "合作交流", "党群工作", "联系我们", "统一身份认证", "更多", "返回", "毕业留影",
)
FACULTY_PROFILE_URL_PATTERNS = (
    "/faculty/", "/people/", "/teacher/", "/teachers/", "/szdw/", "/jsml/",
    "/info/", "/profile/", "/staff/", "/dsjs/", "/jsjj/", "/dsjj/",
)
GLOBAL_CHROME_SELECTORS = (
    "header", "nav", "footer", "aside", ".nav", "#nav", ".sidebar", ".left-menu",
    ".breadcrumb", ".crumbs", ".pagination", ".pager", ".navbar", ".top-nav",
    ".global-nav", ".header", ".footer", "#header", "#footer", ".menu", "#menu",
    ".topbar", ".site-header", ".site-footer",
)
CAROUSEL_SELECTORS = (
    ".swiper", ".slick", ".carousel", ".slider",
    '[class*="carousel"]', '[class*="swiper"]', '[class*="slider"]', '[class*="slick"]',
)
NEWS_DATE_PATH_RE = re.compile(r"/202[0-9]/[0-9]{4}/")
ADMIN_SLUG_DENYLIST = (
    "openpositions", "djgz", "dqgz", "ndjj", "xygk", "szgk",
    "xygz", "byly", "xsgz", "twgz", "tzgg", "publications/",
)
ORG_NAME_REJECT_KEYWORDS = (
    "学院", "学系", "研究院", "研究所", "中心", "学部",
    "school", "department", "college", "institute", "center", "university",
)
ROOT_OR_INDEX_PATHS = (
    "", "/", "/index.htm", "/index.html", "/index.php", "/index.jsp",
    "/main.psp", "/default.aspx", "/default.htm", "/default.html",
)


def is_root_or_index_url(url: str) -> bool:
    """Returns True if URL is a homepage or root/index entry point (never a faculty roster)."""
    path_low = (urlparse(url or "").path or "/").lower().strip()
    return path_low in ROOT_OR_INDEX_PATHS


def registrable_domain(host: str) -> str:
    """Extracts root domain (e.g. 'tsinghua.edu.cn' from 'cs.tsinghua.edu.cn')."""
    clean = (host or "").lower().split(":")[0].strip(".")
    parts = [p for p in clean.split(".") if p]
    if len(parts) >= 3 and (clean.endswith(".edu.cn") or clean.endswith(".ac.cn") or clean.endswith(".org.cn")):
        return ".".join(parts[-3:])
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return clean


def is_same_root_domain(url: str, root_domain: str) -> bool:
    """Allows same-root academic subdomains (e.g. cs.tsinghua.edu.cn) while blocking external domains (e.g. 720yun.com)."""
    host = urlparse(url).netloc.lower().split(":")[0]
    target_root = registrable_domain(root_domain)
    if not host or not target_root:
        return False
    return host == target_root or host.endswith("." + target_root)


def _is_denied_url_or_anchor(abs_url: str, anchor_text: str) -> bool:
    parsed = urlparse(abs_url)
    path_low = (parsed.path or "/").lower()
    full_low = abs_url.lower()
    text_low = (anchor_text or "").strip().lower()

    # Reject root index pages (e.g. /, /index.htm, /index.html)
    if path_low in ("", "/", "/index.htm", "/index.html", "/index.php", "/index.jsp"):
        return True
    if any(bad in full_low for bad in NON_PROFILE_URL_DENYLIST):
        return True
    if text_low in NON_PROFILE_ANCHOR_DENYLIST:
        return True
    if path_low.endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar", ".jpg", ".png", ".mp4")):
        return True
    return False


def extract_breadcrumb_markers(html: str) -> str:
    """Extracts supervisor markers from breadcrumb/nav/title BEFORE stripping boilerplate."""
    tree = LexborHTMLParser(html or "")
    parts: list[str] = []
    title = tree.css_first("title")
    if title:
        parts.append(title.text(strip=True))
    for sel in ("nav", ".breadcrumb", ".crumbs", ".position", ".tab", ".tabs"):
        for node in tree.css(sel):
            txt = re.sub(r"\s+", " ", node.text(separator=" ", strip=True))
            if txt and any(m in txt for m in ("博士生导师", "硕士生导师", "博导", "硕导", "师资")):
                parts.append(txt[:160])
    return " | ".join(dict.fromkeys(parts))


def clean_html_to_markdown(html: str) -> tuple[str, str]:
    """
    Clean Markdown pipeline:
    1. Extract breadcrumb/tab supervisor markers before stripping nav.
    2. Replace email-related <img> tags with [EMAIL_IMAGE_TAG].
    3. Strip <script>, <style>, <footer>, <nav>, <noscript> via selectolax.
    4. Convert remaining HTML to clean Markdown via markdownify.
    """
    breadcrumb = extract_breadcrumb_markers(html)
    patched_html = re.sub(
        r'<img\b[^>]*(?:email|mail|e-mail|邮箱|联系方式)[^>]*/?>',
        " [EMAIL_IMAGE_TAG] ",
        html or "",
        flags=re.I,
    )
    tree = LexborHTMLParser(patched_html)
    for tag in ("script", "style", "footer", "nav", "noscript", "iframe"):
        for node in tree.css(tag):
            node.decompose()

    cleaned_html = tree.html or ""
    markdown = md_convert(cleaned_html, heading_style="ATX")
    markdown = markdown.replace(r"[EMAIL\_IMAGE\_TAG]", "[EMAIL_IMAGE_TAG]")
    markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()
    return markdown, breadcrumb


def compute_sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def is_plausible_person_name(raw: str) -> bool:
    """Validates person-name anchors (stripping '导师简介——' prefixes) while strictly rejecting org/school names."""
    text = (raw or "").strip()
    if not text:
        return False
    low = text.lower()
    if any(kw in low for kw in ORG_NAME_REJECT_KEYWORDS):
        return False
    text = ROLE_PREFIX_RE.sub("", text).strip()
    cleaned = TITLE_BRACKET_RE.sub("", text).strip()
    if not cleaned:
        return False
    if CJK_NAME_RE.match(cleaned) and cleaned[0] in SURNAMES:
        return True
    return bool(EN_NAME_RE.match(cleaned))


def detect_inline_table_roster(html: str, url: str) -> tuple[bool, int]:
    """
    Archetype B (Single-Page / Inline Table Roster) detector:
    Returns (True, title_occurrences) when a faculty/supervisor page lists >= 4 academic rank occurrences
    directly in main body text/tables without separate per-professor bio links.
    """
    if not html or not url or is_root_or_index_url(url):
        return False, 0
    bc = extract_breadcrumb_markers(html).lower()
    if not any(w in bc or w in (url or "").lower() for w in INLINE_ROSTER_TITLE_WORDS):
        return False, 0
    tree = LexborHTMLParser(html)
    for sel in (*GLOBAL_CHROME_SELECTORS, *CAROUSEL_SELECTORS, "script", "style"):
        for node in tree.css(sel):
            node.decompose()
    body_text = tree.text(separator=" ", strip=True) or ""
    hits = sum(body_text.count(w) for w in INLINE_FACULTY_RANK_WORDS)
    return hits >= 4, hits


_looks_like_person_name = is_plausible_person_name


def extract_profile_urls_with_audit(
    html: str,
    base_url: str,
    root_domain: str | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """
    Main-body-only professor profile link extractor with full drop-reason audit:
    1. Strips <header>, <nav>, <footer>, <aside>, .nav, #nav, .sidebar, .breadcrumb, .pagination, and carousels.
    2. Rejects /list.htm, /list.jsp, news date paths (/202[0-9]/[0-9]{4}/), and admin slugs (OpenPositions, djgz, dqgz, ndjj, xygk, szgk).
    3. Enforces strict same-root-domain lock and plausible person-name checks.
    """
    raw_tree = LexborHTMLParser(html or "")
    total_raw_links = len(raw_tree.css("a[href]"))

    tree = LexborHTMLParser(html or "")
    for sel in (*GLOBAL_CHROME_SELECTORS, *CAROUSEL_SELECTORS):
        for node in tree.css(sel):
            node.decompose()

    remaining_nodes = tree.css("a[href]")
    dropped = {
        "nav_sidebar": max(0, total_raw_links - len(remaining_nodes)),
        "list_index": 0,
        "news_date": 0,
        "admin_slug": 0,
        "other_denied": 0,
    }

    expected_root = registrable_domain(root_domain or urlparse(base_url).netloc)
    seen: set[str] = set()
    prioritized: list[tuple[int, str]] = []

    for a in remaining_nodes:
        href = (a.attributes.get("href") or "").strip()
        if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
            dropped["other_denied"] += 1
            continue
        abs_url = urljoin(base_url, href).split("#")[0]
        if abs_url in seen or abs_url.rstrip("/") == base_url.rstrip("/"):
            continue
        if expected_root and not is_same_root_domain(abs_url, expected_root):
            dropped["other_denied"] += 1
            continue

        parsed_u = urlparse(abs_url)
        path_low = (parsed_u.path or "/").lower()
        url_low = abs_url.lower()

        if path_low.endswith(("/list.htm", "/list.html", "/list.jsp")):
            dropped["list_index"] += 1
            continue
        if NEWS_DATE_PATH_RE.search(path_low):
            dropped["news_date"] += 1
            continue
        if any(slug in url_low for slug in ADMIN_SLUG_DENYLIST):
            dropped["admin_slug"] += 1
            continue

        text = re.sub(r"\s+", " ", a.text(separator=" ", strip=True) or a.attributes.get("title") or "").strip()
        if _is_denied_url_or_anchor(abs_url, text):
            dropped["other_denied"] += 1
            continue

        has_prof_pattern = any(pat in url_low for pat in FACULTY_PROFILE_URL_PATTERNS)

        if is_plausible_person_name(text):
            seen.add(abs_url)
            score = 3 if has_prof_pattern else 2
            prioritized.append((score, abs_url))
            continue

        if text.lower() in DETAIL_ANCHOR_TEXTS:
            parent = a.parent
            if parent is not None:
                card_text = re.sub(r"\s+", " ", parent.text(separator=" ", strip=True))
                tokens = [t.strip() for t in re.split(r"[\s,，|/]+", card_text) if t.strip()]
                if any(is_plausible_person_name(tok) for tok in tokens):
                    seen.add(abs_url)
                    score = 3 if has_prof_pattern else 2
                    prioritized.append((score, abs_url))
                    continue

        dropped["other_denied"] += 1

    prioritized.sort(key=lambda x: x[0], reverse=True)
    kept = [u for _, u in prioritized]
    audit = {
        "total_links": total_raw_links,
        "kept_count": len(kept),
        "dropped_breakdown": dropped,
    }
    return kept, audit


def extract_profile_urls(html: str, base_url: str, root_domain: str | None = None) -> list[str]:
    """Main-body-only professor profile link extractor."""
    urls, _ = extract_profile_urls_with_audit(html, base_url, root_domain=root_domain)
    return urls


def verify_roster_html(
    html: str,
    url: str,
    *,
    root_domain: str | None = None,
    min_profiles: int = 3,
    node_type: str | None = None,
) -> tuple[bool, list[str]]:
    """
    Shared Deterministic Roster Verification Gate (used by SiteTreeBuilder & Phase1Discovery):
    - NEVER accepts HOME, SCHOOLS_DIR, DEPT_HOME, or root/index URLs (/, /index.htm, /index.html, /main.psp).
    - Accepts ONLY if cleaned main-body (with carousels stripped) yields >= 3 plausible same-domain profile links.
    """
    if not html or not url:
        return False, []
    if node_type in ("HOME", "SCHOOLS_DIR", "DEPT_HOME"):
        return False, []
    if is_root_or_index_url(url):
        return False, []
    candidates = extract_profile_urls(html, url, root_domain=root_domain)
    return len(candidates) >= min_profiles, candidates


def find_next_page_url(html: str, base_url: str) -> str | None:
    tree = LexborHTMLParser(html or "")
    for a in tree.css("a[href]"):
        text = (a.text(strip=True) or "").lower()
        if text in NEXT_PAGE_TEXTS:
            href = (a.attributes.get("href") or "").strip()
            if href and not href.startswith(("javascript:", "#")):
                return urljoin(base_url, href).split("#")[0]
    return None


class Phase2ScraperService:
    """Fetches faculty directories & profiles politely, converts to Clean Markdown, and saves permanent snapshots."""

    def __init__(
        self,
        repo: Repository,
        admin: AdminConfig | None = None,
        colab: ColabClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        playwright_fetcher: Any = None,
        per_domain_delay: float | None = None,
    ) -> None:
        self.repo = repo
        self.admin = admin or AdminConfig()
        self.colab = colab or colab_client
        self.transport = transport
        self.playwright_fetcher = playwright_fetcher or _default_playwright_fetch
        self.per_domain_delay = settings.PER_DOMAIN_DELAY_SEC if per_domain_delay is None else per_domain_delay
        self._host_locks: dict[str, asyncio.Lock] = {}
        self._host_last: dict[str, float] = {}

    async def _polite_wait(self, host: str) -> None:
        if self.per_domain_delay <= 0:
            return
        lock = self._host_locks.setdefault(host, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            last = self._host_last.get(host, 0.0)
            if last > 0:
                jitter = random.uniform(0.05, 0.25)
                wait = (self.per_domain_delay + jitter) - (now - last)
                if wait > 0:
                    await asyncio.sleep(wait)
            self._host_last[host] = time.monotonic()

    async def _log_fetch_trace(
        self,
        *,
        stage: str,
        url: str,
        domain: str,
        engine: str,
        status_code: int | None,
        error_detail: str,
        html_bytes: int,
        markdown_chars: int,
        latency_ms: int,
    ) -> None:
        try:
            await self.repo.insert_http_fetch_trace(
                HttpFetchTraceDoc(
                    trace_id=f"ft_{uuid.uuid4().hex[:12]}",
                    job_id=current_job_id.get() or "",
                    domain=domain or current_domain.get() or "",
                    stage=stage,
                    url=url,
                    engine=engine,  # type: ignore[arg-type]
                    status_code=status_code,
                    error_detail=error_detail[:400],
                    html_bytes=html_bytes,
                    markdown_chars=markdown_chars,
                    latency_ms=latency_ms,
                )
            )
        except Exception:
            pass

    async def crawl_roster_urls(self, roster_url: str, max_pages: int = 3) -> StepResult:
        """Follows directory pagination (max 3 pages), retries via Playwright on timeout/SSL/403 or 0 links, and logs link audit."""
        profile_urls: list[str] = []
        seen_pages: set[str] = set()
        current_url: str | None = roster_url
        used_playwright = False
        root_dom = registrable_domain(urlparse(roster_url).netloc)
        roster_title = ""
        agg_total_links = 0
        agg_dropped: dict[str, int] = {"nav_sidebar": 0, "list_index": 0, "news_date": 0, "admin_slug": 0, "other_denied": 0}

        async with httpx.AsyncClient(transport=self.transport) as client:
            for _ in range(max_pages):
                if not current_url or current_url in seen_pages:
                    break
                seen_pages.add(current_url)
                host = urlparse(current_url).netloc
                await self._polite_wait(host)

                st, final_url, html = 0, current_url, ""
                t0 = time.perf_counter()
                fetch_err = ""
                try:
                    resp = await client.get(
                        current_url,
                        headers={"User-Agent": settings.CRAWL_USER_AGENT},
                        follow_redirects=True,
                        timeout=15.0,
                    )
                    st, final_url, html = resp.status_code, str(resp.url), decode_bytes_safely(resp.content)
                    md_len = len(clean_html_to_markdown(html)[0]) if html else 0
                    await self._log_fetch_trace(
                        stage="phase2a_roster",
                        url=final_url,
                        domain=root_dom,
                        engine="httpx",
                        status_code=st,
                        error_detail="" if st == 200 else f"HTTP {st}",
                        html_bytes=len(resp.content),
                        markdown_chars=md_len,
                        latency_ms=int((time.perf_counter() - t0) * 1000),
                    )
                except Exception as exc:
                    fetch_err = f"{type(exc).__name__}: {exc}"
                    await self._log_fetch_trace(
                        stage="phase2a_roster",
                        url=current_url,
                        domain=root_dom,
                        engine="httpx",
                        status_code=None,
                        error_detail=fetch_err,
                        html_bytes=0,
                        markdown_chars=0,
                        latency_ms=int((time.perf_counter() - t0) * 1000),
                    )

                # Auto-retry via Playwright on httpx timeout/SSL/403/412/521
                if (st in (0, 403, 412, 521) or fetch_err) and self.admin.enable_playwright and self.playwright_fetcher is not None:
                    t_pw = time.perf_counter()
                    try:
                        st, final_url, html = await self.playwright_fetcher(current_url)
                        used_playwright = True
                        fetch_err = ""
                        md_len_pw = len(clean_html_to_markdown(html)[0]) if html else 0
                        await self._log_fetch_trace(
                            stage="phase2a_roster",
                            url=final_url,
                            domain=root_dom,
                            engine="playwright",
                            status_code=st,
                            error_detail="",
                            html_bytes=len((html or "").encode("utf-8")),
                            markdown_chars=md_len_pw,
                            latency_ms=int((time.perf_counter() - t_pw) * 1000),
                        )
                    except Exception as pw_exc:
                        pw_err = f"{type(pw_exc).__name__}: {pw_exc}"
                        await self._log_fetch_trace(
                            stage="phase2a_roster",
                            url=current_url,
                            domain=root_dom,
                            engine="playwright",
                            status_code=None,
                            error_detail=pw_err,
                            html_bytes=0,
                            markdown_chars=0,
                            latency_ms=int((time.perf_counter() - t_pw) * 1000),
                        )
                        return StepResult.fail(ErrorCode.HTTP_ERROR, f"Roster fetch failed: {fetch_err or pw_err}")

                if fetch_err:
                    return StepResult.fail(ErrorCode.HTTP_ERROR, f"Roster fetch failed: {fetch_err}")

                if not roster_title and html:
                    t_node = LexborHTMLParser(html).css_first("title")
                    if t_node:
                        roster_title = t_node.text(strip=True)[:160]

                links, audit = extract_profile_urls_with_audit(html, final_url, root_domain=root_dom) if st == 200 else ([], {"total_links": 0, "kept_count": 0, "dropped_breakdown": {}})

                if st == 200 and len(links) == 0 and self.admin.enable_playwright and self.playwright_fetcher is not None and not used_playwright:
                    t_pw = time.perf_counter()
                    try:
                        st, final_url, html = await self.playwright_fetcher(final_url)
                        links, audit = extract_profile_urls_with_audit(html, final_url, root_domain=root_dom)
                        used_playwright = True
                        md_len_spa = len(clean_html_to_markdown(html)[0]) if html else 0
                        await self._log_fetch_trace(
                            stage="phase2a_roster_spa",
                            url=final_url,
                            domain=root_dom,
                            engine="playwright",
                            status_code=st,
                            error_detail="",
                            html_bytes=len((html or "").encode("utf-8")),
                            markdown_chars=md_len_spa,
                            latency_ms=int((time.perf_counter() - t_pw) * 1000),
                        )
                    except Exception as exc:
                        return StepResult.fail(ErrorCode.PLAYWRIGHT_ERROR, f"Playwright directory render failed: {type(exc).__name__}: {exc}")

                agg_total_links += int(audit.get("total_links") or 0)
                for dk, dv in (audit.get("dropped_breakdown") or {}).items():
                    agg_dropped[dk] = agg_dropped.get(dk, 0) + int(dv or 0)

                for u in links:
                    if u not in profile_urls:
                        profile_urls.append(u)
                    if len(profile_urls) >= self.admin.max_professors_per_uni:
                        break
                if len(profile_urls) >= self.admin.max_professors_per_uni:
                    break
                current_url = find_next_page_url(html, final_url)

        try:
            await self.repo.insert_phase2_link_audit(
                Phase2LinkAuditDoc(
                    audit_id=f"la_{uuid.uuid4().hex[:12]}",
                    job_id=current_job_id.get() or "",
                    domain=root_dom or current_domain.get() or "",
                    roster_url=roster_url,
                    total_links=agg_total_links,
                    kept_count=len(profile_urls),
                    dropped_breakdown=agg_dropped,
                )
            )
        except Exception:
            pass

        roster_mode = "BIO_LINKS"
        inline_snapshot = None
        if len(profile_urls) < 3 and html:
            is_inline, _ = detect_inline_table_roster(html, roster_url)
            if is_inline:
                roster_mode = "INLINE_TABLE"
                md_inline, bc_inline = clean_html_to_markdown(html)
                inline_snapshot = PageSnapshotDoc(
                    url=roster_url,
                    domain=root_dom or current_domain.get() or "",
                    markdown=md_inline,
                    breadcrumb=bc_inline,
                    sha256=compute_sha256(md_inline),
                )

        return StepResult.success({
            "profile_urls": profile_urls,
            "used_playwright": used_playwright,
            "roster_title": roster_title,
            "roster_mode": roster_mode,
            "inline_snapshot": inline_snapshot,
            "link_audit": {"total_links": agg_total_links, "kept_count": len(profile_urls), "dropped_breakdown": agg_dropped},
        })

    async def fetch_and_snapshot_profile(
        self,
        profile_url: str,
        domain: str,
        *,
        use_colab_readerlm: bool = False,
    ) -> StepResult:
        """Fetches a single profile page, generates Clean Markdown via selectolax+markdownify, and upserts snapshot."""
        host = urlparse(profile_url).netloc
        await self._polite_wait(host)
        t0 = time.perf_counter()

        try:
            async with httpx.AsyncClient(transport=self.transport) as client:
                resp = await client.get(
                    profile_url,
                    headers={"User-Agent": settings.CRAWL_USER_AGENT},
                    follow_redirects=True,
                    timeout=15.0,
                )
        except Exception as exc:
            err_s = f"{type(exc).__name__}: {exc}"
            await self._log_fetch_trace(
                stage="phase2a_profile",
                url=profile_url,
                domain=domain,
                engine="httpx",
                status_code=None,
                error_detail=err_s,
                html_bytes=0,
                markdown_chars=0,
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )
            return StepResult.fail(ErrorCode.HTTP_ERROR, f"Profile fetch failed: {err_s}")

        if resp.status_code != 200:
            await self._log_fetch_trace(
                stage="phase2a_profile",
                url=str(resp.url),
                domain=domain,
                engine="httpx",
                status_code=resp.status_code,
                error_detail=f"HTTP {resp.status_code}",
                html_bytes=len(resp.content),
                markdown_chars=0,
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )
            return StepResult.fail(ErrorCode.HTTP_ERROR, f"Profile returned HTTP {resp.status_code}")

        html = decode_bytes_safely(resp.content)
        markdown, breadcrumb = clean_html_to_markdown(html)
        await self._log_fetch_trace(
            stage="phase2a_profile",
            url=str(resp.url),
            domain=domain,
            engine="httpx",
            status_code=200,
            error_detail="",
            html_bytes=len(resp.content),
            markdown_chars=len(markdown),
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )

        snap = PageSnapshotDoc(
            url=str(resp.url),
            domain=domain.lower().strip(),
            markdown=markdown,
            sha256=compute_sha256(markdown),
            breadcrumb=breadcrumb,
            etag=resp.headers.get("etag"),
            last_modified=resp.headers.get("last-modified"),
        )
        await self.repo.upsert_page_snapshot(snap)
        logger.info("snapshot_saved", url=snap.url, sha256=snap.sha256[:12])
        return StepResult.success(snap)
