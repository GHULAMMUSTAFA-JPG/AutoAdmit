"""Last-Resort Playwright + LLM Navigation Agent (queued via asyncio.Queue + Semaphore(2))."""

import asyncio
import json
import re
from typing import Any, Awaitable, Callable
from urllib.parse import urljoin, urlparse
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from app.core.llm_router import LLMRouter, llm_router
from app.core.logging import get_logger
from app.core.types import ErrorCode, StepResult

logger = get_logger("services.nav_agent")

PageFetcher = Callable[[str], Awaitable[tuple[int, str, str]]]


def extract_visible_links(html: str, base_url: str, max_links: int = 60) -> list[dict[str, str]]:
    """Extracts deduplicated clickable anchor links (text + absolute href) using selectolax."""
    tree = HTMLParser(html or "")
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for node in tree.css("a[href]"):
        href = (node.attributes.get("href") or "").strip()
        if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        abs_url = urljoin(base_url, href).split("#")[0]
        text = re.sub(r"\s+", " ", node.text(separator=" ", strip=True) or node.attributes.get("title") or "").strip()
        if not text or abs_url in seen:
            continue
        seen.add(abs_url)
        out.append({"text": text[:80], "href": abs_url})
        if len(out) >= max_links:
            break
    return out


async def _default_playwright_fetch(url: str) -> tuple[int, str, str]:
    """Renders a page with headless Chromium in a worker thread."""
    def _run() -> tuple[int, str, str]:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
            try:
                ctx = browser.new_context(ignore_https_errors=True, locale="zh-CN")
                page = ctx.new_page()
                resp = page.goto(url, wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(1000)
                status = resp.status if resp else 200
                return status, page.url, page.content()
            finally:
                browser.close()

    return await asyncio.to_thread(_run)


class NavigationAgent:
    """Bounded async queue worker that uses Playwright + LLM to navigate hard university sites (max 3 hops)."""

    def __init__(
        self,
        router: LLMRouter | None = None,
        page_fetcher: PageFetcher | None = None,
        max_concurrency: int = 2,
        max_hops: int = 3,
    ) -> None:
        self.router = router or llm_router
        self.page_fetcher = page_fetcher or _default_playwright_fetch
        self._queue: asyncio.Queue[tuple[dict[str, Any], asyncio.Future]] = asyncio.Queue()
        self._sem = asyncio.Semaphore(max(1, max_concurrency))
        self.max_hops = max_hops

    async def navigate(self, start_url: str, domain: str, department: str, degree: str) -> StepResult:
        """Queues and executes a bounded navigation job, returning chosen roster URL + navigation_path."""
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        await self._queue.put(({"start_url": start_url, "domain": domain, "department": department, "degree": degree}, fut))
        task, target_fut = await self._queue.get()
        try:
            async with self._sem:
                res = await self._run_navigation(**task)
            if not target_fut.done():
                target_fut.set_result(res)
        except Exception as exc:
            if not target_fut.done():
                target_fut.set_result(StepResult.fail(ErrorCode.AGENT_FAILED, f"Nav agent error: {exc}"))
        finally:
            self._queue.task_done()
        return await fut

    async def _run_navigation(self, start_url: str, domain: str, department: str, degree: str) -> StepResult:
        current_url = start_url
        nav_path: list[dict[str, str]] = []

        for hop in range(1, self.max_hops + 1):
            try:
                status_code, final_url, html = await self.page_fetcher(current_url)
            except Exception as exc:
                return StepResult.fail(ErrorCode.PLAYWRIGHT_ERROR, f"Hop {hop} fetch failed: {exc}", data={"navigation_path": nav_path})

            if status_code >= 400:
                return StepResult.fail(ErrorCode.HTTP_ERROR, f"Hop {hop} returned HTTP {status_code}", data={"navigation_path": nav_path})

            links = extract_visible_links(html, final_url)
            if not links:
                return StepResult.fail(ErrorCode.NO_LINKS_FOUND, f"No links on {final_url}", data={"navigation_path": nav_path})

            links_text = "\n".join(f"- [{l['text']}]({l['href']})" for l in links[:45])
            prompt = (
                f"You are navigating {domain} to find the {department} {degree} faculty/supervisor roster page.\n"
                f"Current URL: {final_url}\n"
                f"Available links:\n{links_text}\n\n"
                f'Return JSON ONLY: {{"chosen_link": "<exact href or CURRENT_IS_ROSTER>", "is_roster": true/false, "reason": "<short reason>"}}'
            )
            llm_res = await self.router.complete([{"role": "user", "content": prompt}], json_mode=True)
            if not llm_res.ok:
                return StepResult.fail(ErrorCode.AGENT_FAILED, llm_res.detail or "LLM nav failed", data={"navigation_path": nav_path})

            try:
                m = re.search(r"\{.*\}", llm_res.data["content"], re.S)
                parsed = json.loads(m.group(0)) if m else {}
            except Exception as exc:
                return StepResult.fail(ErrorCode.AGENT_FAILED, f"Invalid LLM nav JSON: {exc}", data={"navigation_path": nav_path})

            chosen = str(parsed.get("chosen_link") or "").strip()
            reason = str(parsed.get("reason") or "").strip()
            is_roster = bool(parsed.get("is_roster"))

            nav_path.append({"url": final_url, "chosen_link": chosen, "reason": reason})
            logger.info("nav_agent_hop", hop=hop, url=final_url, chosen_link=chosen, is_roster=is_roster)

            if is_roster or chosen == "CURRENT_IS_ROSTER":
                target = final_url if chosen in ("", "CURRENT_IS_ROSTER") else chosen
                return StepResult.success({"faculty_roster_url": target, "navigation_path": nav_path})

            if not chosen or urlparse(chosen).netloc == "":
                break
            current_url = chosen

        return StepResult.fail(ErrorCode.AGENT_FAILED, "Max navigation hops reached without finding roster.", data={"navigation_path": nav_path})
