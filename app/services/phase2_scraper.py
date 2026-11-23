"""Phase 2A: Polite per-domain directory crawler, JS SPA fallback, Clean Markdown pipeline, and permanent snapshots."""

import asyncio
import hashlib
import random
import re
import time
from typing import Any
from urllib.parse import urljoin, urlparse
import httpx
from markdownify import markdownify as md_convert
from selectolax.lexbor import LexborHTMLParser

from app.core.config import settings
from app.core.logging import get_logger
from app.core.types import ErrorCode, StepResult
from app.db.repositories import Repository
from app.schemas.entities import PageSnapshotDoc
from app.schemas.filters import AdminConfig
from app.services.colab_client import ColabClient, colab_client
from app.services.nav_agent import _default_playwright_fetch
from app.services.phase1_discovery import decode_bytes_safely

logger = get_logger("services.phase2_scraper")

SURNAMES = set(
    "王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤常温康施文牛樊葛邢安齐易乔伍庞颜倪庄聂章鲁岳翟殷詹申欧耿关兰焦俞左柳甘祝包宁尚符舒阮柯纪梅童凌毕单季裴霍涂成苗谷盛曲翁冉骆蓝路游辛靳管柴蒙鲍华喻祁蒲房滕屈饶解牟艾尤阳时穆农司卓古吉缪简车项连芦麦褚娄窦戚岑景党宫费卜冷晏席卫米柏宗瞿桂全佟应臧闵苟邬边卞姬师"
)
CJK_NAME_RE = re.compile(r"^[\u4e00-\u9fa5·]{2,4}$")
EN_NAME_RE = re.compile(r"^[A-Z][a-z]+(?: [A-Z][a-z\-]+){1,3}$")
TITLE_BRACKET_RE = re.compile(r"[\(\（\[【].*?[\)\）\]】]|教授|副教授|研究员|副研究员|博导|硕导|博士|老师|Prof\.|Dr\.")
DETAIL_ANCHOR_TEXTS = {"查看详情", "详情", "个人主页", "view details", "details", "profile", "more"}
NEXT_PAGE_TEXTS = {"下一页", "下页", "next", ">", "›", "»"}


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
    # Replace email images before parsing/stripping
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


def _looks_like_person_name(raw: str) -> bool:
    cleaned = TITLE_BRACKET_RE.sub("", raw or "").strip()
    if CJK_NAME_RE.match(cleaned) and cleaned[0] in SURNAMES:
        return True
    return bool(EN_NAME_RE.match(cleaned))


def extract_profile_urls(html: str, base_url: str) -> list[str]:
    """Extracts candidate professor profile URLs from a directory page, handling title brackets and detail cards."""
    tree = LexborHTMLParser(html or "")
    seen: set[str] = set()
    urls: list[str] = []

    for a in tree.css("a[href]"):
        href = (a.attributes.get("href") or "").strip()
        if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        abs_url = urljoin(base_url, href).split("#")[0]
        if abs_url in seen:
            continue
        text = re.sub(r"\s+", " ", a.text(separator=" ", strip=True) or a.attributes.get("title") or "").strip()
        if _looks_like_person_name(text):
            seen.add(abs_url)
            urls.append(abs_url)
            continue
        # Check parent card for "View Details" / "查看详情" links paired with a person name
        if text.lower() in DETAIL_ANCHOR_TEXTS:
            parent = a.parent
            if parent is not None:
                card_text = re.sub(r"\s+", " ", parent.text(separator=" ", strip=True))
                tokens = [t.strip() for t in re.split(r"[\s,，|/]+", card_text) if t.strip()]
                if any(_looks_like_person_name(tok) for tok in tokens):
                    seen.add(abs_url)
                    urls.append(abs_url)
    return urls


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

    async def crawl_roster_urls(self, roster_url: str, max_pages: int = 5) -> StepResult:
        """Follows directory pagination (max 5 pages) and falls back to Playwright on HTTP 200 with 0 links."""
        profile_urls: list[str] = []
        seen_pages: set[str] = set()
        current_url: str | None = roster_url
        used_playwright = False

        async with httpx.AsyncClient(transport=self.transport) as client:
            for _ in range(max_pages):
                if not current_url or current_url in seen_pages:
                    break
                seen_pages.add(current_url)
                host = urlparse(current_url).netloc
                await self._polite_wait(host)

                try:
                    resp = await client.get(
                        current_url,
                        headers={"User-Agent": settings.CRAWL_USER_AGENT},
                        follow_redirects=True,
                        timeout=15.0,
                    )
                    st, final_url, html = resp.status_code, str(resp.url), decode_bytes_safely(resp.content)
                except Exception as exc:
                    return StepResult.fail(ErrorCode.HTTP_ERROR, f"Roster fetch failed: {exc}")

                links = extract_profile_urls(html, final_url) if st == 200 else []

                # JS SPA Trigger: HTTP 200 AND 0 candidate profile links -> re-render with Playwright
                if st == 200 and len(links) == 0 and self.admin.enable_playwright and self.playwright_fetcher is not None:
                    try:
                        st, final_url, html = await self.playwright_fetcher(final_url)
                        links = extract_profile_urls(html, final_url)
                        used_playwright = True
                    except Exception as exc:
                        return StepResult.fail(ErrorCode.PLAYWRIGHT_ERROR, f"Playwright directory render failed: {exc}")

                for u in links:
                    if u not in profile_urls:
                        profile_urls.append(u)
                    if len(profile_urls) >= self.admin.max_professors_per_uni:
                        break
                if len(profile_urls) >= self.admin.max_professors_per_uni:
                    break
                current_url = find_next_page_url(html, final_url)

        return StepResult.success({"profile_urls": profile_urls, "used_playwright": used_playwright})

    async def fetch_and_snapshot_profile(
        self,
        profile_url: str,
        domain: str,
        *,
        use_colab_readerlm: bool = False,
    ) -> StepResult:
        """Fetches a single profile page, generates Clean Markdown, and permanently upserts into page_snapshots."""
        host = urlparse(profile_url).netloc
        await self._polite_wait(host)

        try:
            async with httpx.AsyncClient(transport=self.transport) as client:
                resp = await client.get(
                    profile_url,
                    headers={"User-Agent": settings.CRAWL_USER_AGENT},
                    follow_redirects=True,
                    timeout=15.0,
                )
        except Exception as exc:
            return StepResult.fail(ErrorCode.HTTP_ERROR, f"Profile fetch failed: {exc}")

        if resp.status_code != 200:
            return StepResult.fail(ErrorCode.HTTP_ERROR, f"Profile returned HTTP {resp.status_code}")

        html = decode_bytes_safely(resp.content)
        markdown, breadcrumb = clean_html_to_markdown(html)

        # Call Colab ReaderLM-v2 if extracted text is broken/empty or A/B flag is ON
        if (not markdown or len(markdown) < 30 or use_colab_readerlm) and self.admin.enable_colab_bridge and self.colab.base_url:
            colab_res = await self.colab.html_to_markdown(html, transport=self.transport)
            if colab_res.ok and colab_res.data.get("markdown"):
                markdown = colab_res.data["markdown"]

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
