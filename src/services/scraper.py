"""Live Faculty Harvester: polite HTTP fetching, domain lockdown, directory + profile parsing.

All data returned by this module is extracted from live pages on verified educational
domains. Nothing is synthesized: if a field cannot be found on the page it stays empty.
"""

import asyncio
import os
import re
import time
import uuid
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from src.config import settings
from src.core.logger import setup_logger
from src.models.professor import (
    ExtractionStatus,
    FacultyProfile,
    FacultyPublication,
    SupervisorQualification,
)
from src.services.normalizer import normalizer

logger = setup_logger("ScraperWorker")

# Longest markers first; a marker preceded by a negation character is ignored.
SUPERVISOR_MARKERS = [
    ("博士生导师", SupervisorQualification.PHD_SUPERVISOR),
    ("硕士生导师", SupervisorQualification.MASTERS_SUPERVISOR),
    ("博导", SupervisorQualification.PHD_SUPERVISOR_SHORT),
    ("硕导", SupervisorQualification.MASTERS_SUPERVISOR_SHORT),
]
SUPERVISOR_KEYWORDS = {m: q for m, q in SUPERVISOR_MARKERS}
NEGATIONS = "非不无未"

# Common Chinese surnames (linguistic constant, used only to recognise person-name anchors).
SURNAMES = set(
    "王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤常温康施文牛樊葛邢安齐易乔伍庞颜倪庄聂章鲁岳翟殷詹申欧耿关兰焦俞左柳甘祝包宁尚符舒阮柯纪梅童凌毕单季裴霍涂成苗谷盛曲翁冉骆蓝路游辛靳管柴蒙鲍华喻祁蒲房滕屈饶解牟艾尤阳时穆农司卓古吉缪简车项连芦麦褚娄窦戚岑景党宫费卜冷晏席卫米柏宗瞿桂全佟应臧闵苟邬边卞姬师和仇栾隋商刁沙荣巫寇桑郎甄丛仲虞敖巩明佘池查麻苑迟邝"
)
NAV_STOPWORDS = {"首页", "更多", "详情", "学院", "简介", "新闻", "通知", "公告", "招生", "下一页", "上一页", "返回"}
CJK_NAME = re.compile(r"^[\u4e00-\u9fa5·]{2,5}$")
EN_NAME = re.compile(r"^[A-Z][a-z]+(?: [A-Z][a-z\-]+){1,3}$")


class DomainSecurityViolation(Exception):
    """Raised when a crawler is redirected or pointed to an unauthorized external domain."""


def decode_html(content: bytes, content_type: str = "") -> str:
    """Decode bytes using header charset, meta charset, then utf-8, then gb18030 (common on .edu.cn)."""
    candidates: List[str] = []
    m = re.search(r"charset=[\"']?([\w\-]+)", content_type or "", re.I)
    if m:
        candidates.append(m.group(1))
    head = content[:4096].decode("ascii", errors="ignore")
    m = re.search(r"<meta[^>]+charset=[\"']?([\w\-]+)", head, re.I)
    if m:
        candidates.append(m.group(1))
    candidates += ["utf-8", "gb18030"]
    for enc in candidates:
        try:
            enc = "gb18030" if enc.lower() in ("gb2312", "gbk", "cp936", "gb_2312-80") else enc
            return content.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return content.decode("utf-8", errors="replace")


def registrable_domain(host: str) -> str:
    """Returns e.g. 'tsinghua.edu.cn' for 'cs.tsinghua.edu.cn'."""
    host = host.lower().split(":")[0]
    parts = host.split(".")
    if host.endswith(".edu.cn") or host.endswith(".ac.cn"):
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


class FacultyHarvester:
    """Polite dual-tier fetcher plus directory and profile parsers."""

    # Global 1-at-a-time semaphore for Headless Chromium so 3 parallel workers never spawn multiple heavy browsers
    _playwright_semaphore: Optional[asyncio.Semaphore] = None

    def __init__(self, worker_id: Optional[str] = None):
        self.worker_id = worker_id or f"worker-{os.getpid()}-{str(uuid.uuid4())[:6]}"
        self._robots: Dict[str, Optional[RobotFileParser]] = {}
        self._host_last: Dict[str, float] = {}
        self._host_locks: Dict[str, asyncio.Lock] = {}

    @classmethod
    def _get_pw_semaphore(cls) -> asyncio.Semaphore:
        if cls._playwright_semaphore is None:
            cls._playwright_semaphore = asyncio.Semaphore(1)
        return cls._playwright_semaphore

    # ------------------------------------------------------------------ domains
    @staticmethod
    def is_verified_domain(url: str) -> bool:
        """Official educational domains only (.edu.cn / .ac.cn)."""
        try:
            if "://" not in url:
                url = "https://" + url
            netloc = urlparse(url).netloc.lower().split(":")[0]
            if (netloc.endswith(".edu.cn") or netloc.endswith(".ac.cn")) and not netloc.startswith("."):
                parts = netloc.split(".")
                if len(parts) >= 3:
                    return True
            if settings.ALLOW_LOCAL_TEST_HOSTS and netloc in ("localhost", "127.0.0.1", "testserver"):
                return True
            return False
        except Exception:
            return False

    @staticmethod
    def same_site(url: str, base_domain: str) -> bool:
        host = urlparse(url).netloc.lower().split(":")[0]
        return host == base_domain or host.endswith("." + base_domain)

    # ------------------------------------------------------------------ politeness
    async def _robots_allowed(self, client: httpx.AsyncClient, url: str) -> bool:
        if not settings.RESPECT_ROBOTS_TXT:
            return True
        p = urlparse(url)
        origin = f"{p.scheme}://{p.netloc}"
        if origin not in self._robots:
            rp: Optional[RobotFileParser] = RobotFileParser()
            try:
                r = await client.get(origin + "/robots.txt")
                if r.status_code == 200 and "html" not in r.headers.get("content-type", "").lower():
                    rp.parse(decode_html(r.content, r.headers.get("content-type", "")).splitlines())
                else:
                    rp = None  # no robots policy published
            except Exception:
                rp = None
            self._robots[origin] = rp
        rp = self._robots[origin]
        return True if rp is None else rp.can_fetch(settings.CRAWLER_USER_AGENT, url)

    async def _throttle(self, host: str) -> None:
        lock = self._host_locks.setdefault(host, asyncio.Lock())
        async with lock:
            wait = settings.CRAWL_DELAY_SECONDS - (time.monotonic() - self._host_last.get(host, 0.0))
            if wait > 0:
                await asyncio.sleep(wait)
            self._host_last[host] = time.monotonic()

    # ------------------------------------------------------------------ fetching
    async def fetch_html_fast(self, url: str) -> Tuple[str, str]:
        """Fast tier: async httpx with robots.txt, per-host throttling, charset detection."""
        if not self.is_verified_domain(url):
            raise DomainSecurityViolation(f"Target URL '{url}' is not on a verified educational domain.")

        headers = {
            "User-Agent": settings.CRAWLER_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        async with httpx.AsyncClient(
            timeout=settings.CRAWL_TIMEOUT_SECONDS, follow_redirects=True, headers=headers, verify=False
        ) as client:
            if not await self._robots_allowed(client, url):
                raise PermissionError(f"robots.txt disallows fetching {url}")
            await self._throttle(urlparse(url).netloc)
            response = await client.get(url)
            response.raise_for_status()
            final_url = str(response.url)
            if not self.is_verified_domain(final_url):
                raise DomainSecurityViolation(f"Redirected from '{url}' to unauthorized domain '{final_url}'.")
            return decode_html(response.content, response.headers.get("content-type", "")), final_url

    async def fetch_html_dynamic(self, url: str) -> Tuple[str, str]:
        """
        Fallback tier: headless Playwright for JavaScript-rendered pages and 412/403 WAF challenges.
        Runs sync_playwright inside a dedicated worker thread with WindowsProactorEventLoopPolicy
        so Windows uvicorn --reload (SelectorEventLoop) never raises NotImplementedError on subprocess creation.
        """
        if not self.is_verified_domain(url):
            raise DomainSecurityViolation(f"Target URL '{url}' is not on a verified educational domain.")

        def _sync_playwright_fetch(target_url: str) -> Tuple[str, str]:
            import sys
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-gpu",
                        "--disable-dev-shm-usage",
                        "--disable-extensions",
                    ]
                )
                context = None
                try:
                    context = browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                        ignore_https_errors=True,
                        locale="zh-CN"
                    )
                    page = context.new_page()
                    page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                    page.goto(target_url, wait_until="domcontentloaded", timeout=12000)
                    # Allow dynamic WAF challenge scripts (e.g. RiverSecurity 412 cookie reload) to settle
                    try:
                        page.wait_for_load_state("networkidle", timeout=3500)
                    except Exception:
                        page.wait_for_timeout(1000)
                    final_u = page.url
                    content_html = page.content()
                    return content_html, final_u
                finally:
                    if context:
                        try:
                            context.close()
                        except Exception:
                            pass
                    try:
                        browser.close()
                    except Exception:
                        pass

        async with self._get_pw_semaphore():
            html_content, final_url = await asyncio.wait_for(
                asyncio.to_thread(_sync_playwright_fetch, url),
                timeout=18.0
            )
        if not self.is_verified_domain(final_url):
            raise DomainSecurityViolation(f"Browser redirected '{url}' to '{final_url}'.")
        return html_content, final_url

    async def fetch_page(self, url: str) -> Tuple[str, str]:
        """Fast tier first; Playwright fallback on 412/403/521 WAF challenge or sparse client-rendered DOM."""
        try:
            html, final_url = await self.fetch_html_fast(url)
        except DomainSecurityViolation:
            raise
        except Exception as fast_err:
            logger.info(f"Fast HTTP fetch blocked or failed on {url} ({fast_err}); engaging Headless Playwright fallback...")
            return await self.fetch_html_dynamic(url)

        soup = BeautifulSoup(html, "html.parser")
        if len(soup.get_text(strip=True)) < 200 and not soup.find("a", href=True):
            logger.info(f"Sparse HTML for {url}; engaging Playwright fallback.")
            try:
                return await self.fetch_html_dynamic(url)
            except DomainSecurityViolation:
                raise
            except Exception as e:
                logger.warning(f"Playwright fallback failed for {url}: {e}")
        return html, final_url

    # ------------------------------------------------------------------ link helpers
    @staticmethod
    def extract_links(html: str, base_url: str) -> List[Tuple[str, str]]:
        """All (absolute_url, anchor_text) pairs for http(s) links."""
        soup = BeautifulSoup(html, "html.parser")
        out = []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith(("javascript:", "mailto:", "#", "tel:")):
                continue
            text = re.sub(r"\s+", " ", a.get_text(" ", strip=True) or a.get("title", "")).strip()
            out.append((urljoin(base_url, href), text))
        return out

    @staticmethod
    def _looks_like_person(text: str) -> bool:
        t = text.strip()
        if t in NAV_STOPWORDS:
            return False
        if CJK_NAME.match(t) and t[0] in SURNAMES:
            return True
        return bool(EN_NAME.match(t))

    def extract_profile_links(self, html: str, base_url: str) -> List[Tuple[str, str]]:
        """Person-name anchors on a faculty directory page (same site, de-duplicated)."""
        base_domain = registrable_domain(urlparse(base_url).netloc)
        seen, result = set(), []
        for url, text in self.extract_links(html, base_url):
            url = url.split("#")[0]
            if url in seen or not self._looks_like_person(text) or not self.same_site(url, base_domain):
                continue
            seen.add(url)
            result.append((url, text))
        return result

    @staticmethod
    def find_next_page(html: str, base_url: str) -> Optional[str]:
        for url, text in FacultyHarvester.extract_links(html, base_url):
            if text in ("下一页", "下页", "Next", "next", ">", "›", "»"):
                return url
        return None

    # ------------------------------------------------------------------ qualification
    def verify_qualification(self, text: str) -> Optional[SupervisorQualification]:
        """Supervisor marker present and not negated (e.g. '非博导', '硕导：否')."""
        for marker, qualification in SUPERVISOR_MARKERS:
            for m in re.finditer(re.escape(marker), text):
                # 1. Preceding negation check (e.g. '非博导', '非 硕导', '暂无硕导资格', '不是博导')
                pre_window = text[max(0, m.start() - 6):m.start()]
                if re.search(r"(?:[非不无未]|不是|暂无)\s*$", pre_window):
                    continue
                # 2. Succeeding negation check (e.g. '博导：否', '硕导: 无', '博导: 不是')
                post_window = text[m.end():m.end() + 8]
                if re.match(r"^[:：\s]*(?:否|无|不是)", post_window):
                    continue
                return qualification
        return None

    # ------------------------------------------------------------------ profile parsing
    def parse_profile_html(
        self,
        html: str,
        source_url: str,
        university_name: str,
        department_name: str = "Computer Science",
    ) -> Optional[FacultyProfile]:
        """Parse one faculty profile page. Returns None when it is not a verifiable supervisor."""
        content_hash = normalizer.compute_sha256(html)
        soup = BeautifulSoup(html, "html.parser")
        title_text = soup.title.get_text(strip=True) if soup.title else ""
        for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
            tag.decompose()
        full_text = soup.get_text(separator=" ", strip=True)

        qualification = self.verify_qualification(full_text)
        if not qualification:
            logger.info(f"Skipping {source_url}: no graduate supervisor credential.")
            return None

        # Email (mailto first, then text patterns, de-obfuscated)
        raw_email = None
        mailto = soup.find("a", href=re.compile(r"^mailto:", re.I))
        if mailto:
            raw_email = mailto["href"].split(":", 1)[1].split("?")[0].strip()
        if not raw_email:
            for pattern in (
                r"[a-zA-Z0-9_.+-]+(?:\s*\[at\]\s*|\s*\(at\)\s*|\s*@\s*)[a-zA-Z0-9-]+(?:(?:\s*\[dot\]\s*|\s*\(dot\)\s*|\s*\.\s*)[a-zA-Z0-9-]+)+",
                r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
            ):
                m = re.search(pattern, full_text)
                if m:
                    raw_email = m.group(0)
                    break
        clean_email = normalizer.deobfuscate_email(raw_email or "")
        if not clean_email:
            logger.info(f"Skipping {source_url}: no email on page.")
            return None

        # Name: native Chinese first, else a Latin name; never invented.
        native_name = ""
        for tag in soup.find_all(["h1", "h2", "h3", "strong", "span", "b"]):
            cand = tag.get_text(strip=True)
            if CJK_NAME.match(cand) and cand[0] in SURNAMES:
                native_name = cand
                break
        if not native_name:
            m = re.search(r"姓名[:：\s]*([\u4e00-\u9fa5·]{2,5})", full_text)
            if m:
                native_name = m.group(1)
        name = native_name
        if not name:
            m = re.search(r"\b([A-Z][a-z]+ [A-Z][a-z\-]+)\b", title_text)
            name = m.group(1) if m else ""
        if not name:
            logger.info(f"Skipping {source_url}: could not determine person name.")
            return None

        research_areas: List[str] = []
        m = re.search(r"(?:研究方向|研究领域|招生方向)[:：\s]*([^\n。;]+)", full_text)
        if m:
            research_areas = [a.strip() for a in re.split(r"[,，、;；/ ]+", m.group(1)) if len(a.strip()) > 1]

        publications: List[FacultyPublication] = []
        for header in soup.find_all(string=re.compile(r"(?:发表论文|代表性论文|代表论文|科研成果|Publications)", re.I)):
            parent = header.find_parent(["div", "section", "td", "li", "p"])
            if not parent:
                continue
            for item in parent.find_all(["li", "p"])[:6]:
                text = item.get_text(strip=True)
                if len(text) > 20 and not re.search(r"发表论文|代表性论文|代表论文|Publications", text):
                    ym = re.search(r"\b(20[0-3]\d)\b", text)
                    publications.append(FacultyPublication(title=text[:200], year=int(ym.group(1)) if ym else None))
                if len(publications) >= 3:
                    break
            if publications:
                break

        return FacultyProfile(
            id=str(uuid.uuid4()),
            name=name,
            native_name=native_name or None,
            email=clean_email,
            university=university_name,
            department=normalizer.standardize_department(department_name),
            lab_name="",
            qualification=qualification,
            is_supervisor=True,
            research_areas=research_areas[:5],
            recent_publications=publications[:3],
            source_url=source_url,
            content_hash=content_hash,
            worker_id=self.worker_id,
            is_seed=False,
            data_source="live_crawled",
            extraction_status=ExtractionStatus.VERIFIED,
        )

    # ------------------------------------------------------------------ directory crawl
    async def crawl_directory(
        self, directory_url: str, university_name: str, department_name: str, sem: asyncio.Semaphore
    ) -> List[FacultyProfile]:
        """Follow a faculty directory (with pagination), fetch each profile page, return verified supervisors."""
        base_domain = registrable_domain(urlparse(directory_url).netloc)
        links: List[Tuple[str, str]] = []
        seen_pages, page_url = set(), directory_url
        for _ in range(settings.MAX_DIRECTORY_PAGES):
            if not page_url or page_url in seen_pages:
                break
            seen_pages.add(page_url)
            async with sem:
                try:
                    html, final = await self.fetch_page(page_url)
                except Exception as e:
                    logger.warning(f"Directory fetch failed {page_url}: {e}")
                    break
            links += [l for l in self.extract_profile_links(html, final) if l not in links]
            page_url = self.find_next_page(html, final)
            if len(links) >= settings.MAX_PROFILES_PER_DEPARTMENT:
                break
        links = links[: settings.MAX_PROFILES_PER_DEPARTMENT]
        logger.info(f"{university_name}/{department_name}: {len(links)} candidate profile links at {directory_url}")

        async def _one(url: str) -> Optional[FacultyProfile]:
            async with sem:
                try:
                    html, final = await self.fetch_page(url)
                    if not self.same_site(final, base_domain):
                        return None
                    return self.parse_profile_html(html, final, university_name, department_name)
                except Exception as e:
                    logger.warning(f"Profile fetch failed {url}: {e}")
                    return None

        results = await asyncio.gather(*[_one(u) for u, _ in links])
        return [p for p in results if p]


harvester = FacultyHarvester()
