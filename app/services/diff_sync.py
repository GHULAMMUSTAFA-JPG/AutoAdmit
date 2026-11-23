"""Admin 3-Step Smart Diff-Sync: HTTP 304/ETag -> Roster URL Diff -> Markdown SHA-256 Diff ($0 LLM on unchanged pages)."""

from typing import Any
import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.core.types import ErrorCode, StepResult
from app.db.repositories import Repository
from app.schemas.entities import PageSnapshotDoc
from app.services.phase1_discovery import decode_bytes_safely
from app.services.phase2_extractor import Phase2ExtractorService
from app.services.phase2_scraper import Phase2ScraperService, clean_html_to_markdown, compute_sha256

logger = get_logger("services.diff_sync")


class DiffSyncService:
    """On-demand re-validation service that avoids unnecessary LLM calls via 3-step diffing."""

    def __init__(
        self,
        repo: Repository,
        scraper: Phase2ScraperService,
        extractor: Phase2ExtractorService,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.repo = repo
        self.scraper = scraper
        self.extractor = extractor
        self.transport = transport

    async def sync_profile(
        self,
        profile_url: str,
        domain: str,
        department: str,
        source_roster_url: str,
    ) -> StepResult:
        """Step 1 (HTTP 304/ETag) + Step 3 (SHA-256 Markdown Diff) for one profile URL."""
        existing_snap = await self.repo.get_page_snapshot(profile_url)
        headers: dict[str, str] = {"User-Agent": settings.CRAWL_USER_AGENT}
        if existing_snap:
            if existing_snap.etag:
                headers["If-None-Match"] = existing_snap.etag
            if existing_snap.last_modified:
                headers["If-Modified-Since"] = existing_snap.last_modified

        try:
            async with httpx.AsyncClient(transport=self.transport) as client:
                resp = await client.get(profile_url, headers=headers, follow_redirects=True, timeout=15.0)
        except Exception as exc:
            return StepResult.fail(ErrorCode.HTTP_ERROR, f"Diff-sync fetch failed: {exc}")

        # Step 1: HTTP 304 Not Modified -> skip ($0 LLM)
        if resp.status_code == 304:
            logger.info("diff_sync_304_skip", url=profile_url)
            return StepResult.success({"action": "skipped_304", "llm_called": False})

        if resp.status_code != 200:
            return StepResult.fail(ErrorCode.HTTP_ERROR, f"Profile returned HTTP {resp.status_code}")

        html = decode_bytes_safely(resp.content)
        markdown, breadcrumb = clean_html_to_markdown(html)
        new_hash = compute_sha256(markdown)

        # Step 3: Identical SHA-256 -> skip ($0 LLM)
        if existing_snap and existing_snap.sha256 == new_hash:
            logger.info("diff_sync_sha256_skip", url=profile_url)
            return StepResult.success({"action": "skipped_sha256", "llm_called": False})

        snap = PageSnapshotDoc(
            url=str(resp.url),
            domain=domain.lower().strip(),
            markdown=markdown,
            sha256=new_hash,
            breadcrumb=breadcrumb,
            etag=resp.headers.get("etag"),
            last_modified=resp.headers.get("last-modified"),
        )
        await self.repo.upsert_page_snapshot(snap)
        ext_res = await self.extractor.extract_from_snapshot(
            snap, department=department, source_roster_url=source_roster_url
        )
        return StepResult.success({"action": "re_extracted", "llm_called": True, "extracted_ok": ext_res.ok})

    async def sync_roster(self, domain: str, department: str, source_roster_url: str) -> StepResult:
        """Step 2 (Roster URL Diff): extracts new URLs, marks vanished URLs POSSIBLY_INACTIVE, diff-checks existing."""
        crawl_res = await self.scraper.crawl_roster_urls(source_roster_url)
        if not crawl_res.ok:
            return crawl_res

        live_urls = set(crawl_res.data["profile_urls"])
        stored_profs = await self.repo.list_professors_by_roster(source_roster_url)
        stored_urls = {p.canonical_profile_url for p in stored_profs}

        new_urls = sorted(live_urls - stored_urls)
        vanished_urls = sorted(stored_urls - live_urls)
        kept_urls = sorted(live_urls & stored_urls)

        summary: dict[str, Any] = {
            "domain": domain,
            "new_extracted": 0,
            "marked_inactive": 0,
            "skipped_unchanged": 0,
            "re_extracted_changed": 0,
        }

        # Mark vanished professors as POSSIBLY_INACTIVE (never delete)
        for url in vanished_urls:
            await self.repo.mark_professor_status(url, "POSSIBLY_INACTIVE")
            summary["marked_inactive"] += 1

        # Scrape + extract newly discovered URLs
        for url in new_urls:
            snap_res = await self.scraper.fetch_and_snapshot_profile(url, domain)
            if snap_res.ok:
                ext_res = await self.extractor.extract_from_snapshot(
                    snap_res.data, department=department, source_roster_url=source_roster_url
                )
                if ext_res.ok:
                    summary["new_extracted"] += 1

        # Diff-check existing kept URLs (304 / SHA-256)
        for url in kept_urls:
            sync_res = await self.sync_profile(url, domain, department, source_roster_url)
            if sync_res.ok:
                if sync_res.data["llm_called"]:
                    summary["re_extracted_changed"] += 1
                else:
                    summary["skipped_unchanged"] += 1

        return StepResult.success(summary)
