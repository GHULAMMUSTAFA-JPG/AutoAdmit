"""Slice 4 Tests: Clean Markdown pipeline, Playwright SPA trigger, and permanent page_snapshots storage."""

from pathlib import Path
from unittest.mock import AsyncMock
import httpx
import pytest

from app.core.config import settings
from app.db.mongo import MongoManager
from app.db.repositories import Repository
from app.schemas.filters import AdminConfig
from app.services.phase2_scraper import (
    Phase2ScraperService,
    clean_html_to_markdown,
    extract_profile_urls,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_clean_markdown_strips_boilerplate_extracts_breadcrumb_and_email_image_tag():
    html = (FIXTURES / "profile_page.html").read_text(encoding="utf-8")
    md, breadcrumb = clean_html_to_markdown(html)

    assert "博士生导师" in breadcrumb
    assert "[EMAIL_IMAGE_TAG]" in md
    assert "张伟" in md
    assert "多模态大模型" in md
    assert "tracking noise" not in md
    assert "版权所有" not in md


def test_directory_extract_profile_urls_handles_brackets_and_detail_cards():
    html = (FIXTURES / "directory_page.html").read_text(encoding="utf-8")
    urls = extract_profile_urls(html, "https://cs.tsinghua.edu.cn/faculty/index.html")
    assert "https://cs.tsinghua.edu.cn/faculty/zhangwei.html" in urls
    assert "https://cs.tsinghua.edu.cn/faculty/liming.html" in urls


@pytest.mark.asyncio
async def test_spa_zero_links_triggers_playwright_and_snapshot_persists():
    mgr = MongoManager(uri=settings.MONGODB_URI, db_name="autoadmit_p12_test_s4")
    db = await mgr.connect()
    try:
        repo = Repository(db)
        profile_html = (FIXTURES / "profile_page.html").read_text(encoding="utf-8")
        dir_html = (FIXTURES / "directory_page.html").read_text(encoding="utf-8")

        def handler(req: httpx.Request) -> httpx.Response:
            u = str(req.url)
            if u == "https://cs.spa.edu.cn/roster":
                return httpx.Response(200, text="<html><body><div id='app'>Loading...</div></body></html>")
            if u == "https://cs.spa.edu.cn/faculty/zhangwei.html":
                return httpx.Response(
                    200,
                    text=profile_html,
                    headers={"ETag": '"v1-zw"', "Last-Modified": "Mon, 23 Nov 2026 00:00:00 GMT"},
                )
            return httpx.Response(404)

        pw_mock = AsyncMock(return_value=(200, "https://cs.spa.edu.cn/roster", dir_html))
        svc = Phase2ScraperService(
            repo,
            admin=AdminConfig(enable_playwright=True),
            transport=httpx.MockTransport(handler),
            playwright_fetcher=pw_mock,
            per_domain_delay=0.0,
        )

        crawl_res = await svc.crawl_roster_urls("https://cs.spa.edu.cn/roster", max_pages=1)
        assert crawl_res.ok is True
        assert crawl_res.data["used_playwright"] is True
        assert "https://cs.spa.edu.cn/faculty/zhangwei.html" in crawl_res.data["profile_urls"]
        pw_mock.assert_called_once()

        snap_res = await svc.fetch_and_snapshot_profile("https://cs.spa.edu.cn/faculty/zhangwei.html", "spa.edu.cn")
        assert snap_res.ok is True
        stored = await repo.get_page_snapshot("https://cs.spa.edu.cn/faculty/zhangwei.html")
        assert stored is not None
        assert stored.etag == '"v1-zw"'
        assert len(stored.sha256) == 64
        assert "[EMAIL_IMAGE_TAG]" in stored.markdown
    finally:
        await mgr.client.drop_database("autoadmit_p12_test_s4")
        await mgr.close()


@pytest.mark.asyncio
async def test_directory_pagination_and_max_professors_cap():
    mgr = MongoManager(uri=settings.MONGODB_URI, db_name="autoadmit_p12_test_s4_page")
    db = await mgr.connect()
    try:
        repo = Repository(db)
        page1 = '<html><body><a href="/p1.html">张伟</a><a href="/p2.html">李明</a><a href="/page2.html">下一页</a></body></html>'
        page2 = '<html><body><a href="/p3.html">王芳</a><a href="/p4.html">陈华</a></body></html>'

        def handler(req: httpx.Request) -> httpx.Response:
            if str(req.url).endswith("/page2.html"):
                return httpx.Response(200, text=page2)
            return httpx.Response(200, text=page1)

        svc = Phase2ScraperService(
            repo,
            admin=AdminConfig(max_professors_per_uni=3),
            transport=httpx.MockTransport(handler),
            per_domain_delay=0.0,
        )
        res = await svc.crawl_roster_urls("https://cs.u.edu.cn/page1.html", max_pages=5)
        assert res.ok is True
        assert len(res.data["profile_urls"]) == 3
        assert "https://cs.u.edu.cn/p3.html" in res.data["profile_urls"]
    finally:
        await mgr.client.drop_database("autoadmit_p12_test_s4_page")
        await mgr.close()
