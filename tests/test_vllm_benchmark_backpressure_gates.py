"""Tests for vLLM T4 proxy payloads, Stress Benchmark API, Adaptive Backpressure (5->1),
Token Ledger + Debug Bundle Export, Admin URL / Cheap-First + Agentic Roster Gate,
Phase 2A Link Audit, Obfuscated Email, and NFKC + Whitespace/Roster-Context Grounding.
"""

import json
import time
import httpx
import pytest

from app.core.config import settings
from app.core.llm_router import LLMEndpoint, LLMRouter
from app.core.types import StepResult
from app.db.mongo import MongoManager
from app.db.repositories import Repository
from app.main import create_app
from app.schemas.entities import PageSnapshotDoc
from app.schemas.filters import AdminConfig
from app.services.phase2_extractor import (
    Phase2ExtractorService,
    decode_obfuscated_email,
    extract_email_regex,
    verify_professor_grounding,
)
from app.services.phase2_scraper import extract_profile_urls_with_audit
from app.services.site_tree_builder import (
    SiteTreeBuilder,
    is_admin_or_hr_url,
    score_roster_heuristic,
)


def test_admin_url_blocking_cheap_heuristic_and_phase2a_link_audit():
    assert is_admin_or_hr_url("https://jwc.tsinghua.edu.cn/index.htm") is True
    assert is_admin_or_hr_url("https://rsc.scu.edu.cn/szdw/gk.htm") is True
    assert is_admin_or_hr_url("https://www.test.edu.cn/jyjx/list.htm") is True
    assert is_admin_or_hr_url("https://www.test.edu.cn/zzjg/cs.htm") is True
    assert is_admin_or_hr_url("https://cs.tsinghua.edu.cn/szdw.htm") is False

    # Cheap-first heuristic auto-approves high-confidence CS roster
    cs_html = """<html><head><title>计算机系师资队伍</title></head><body><ul>
      <li><a href="/info/1/zw.htm">张伟</a> 教授 博导</li>
      <li><a href="/info/2/lm.htm">李明</a> 副教授 硕导</li>
      <li><a href="/info/3/wf.htm">王芳</a> 教授 博导</li>
      <li><a href="/info/4/ch.htm">陈华</a> 副教授 硕导</li>
      <li><a href="/info/5/zl.htm">赵雷</a> 讲师 教授</li>
      <li><a href="/info/6/sq.htm">孙强</a> 教授 博导</li>
      <li><a href="/info/7/zj.htm">周杰</a> 副教授</li>
      <li><a href="/info/8/wl.htm">吴磊</a> 教授</li>
    </ul></body></html>"""
    score, tier = score_roster_heuristic(cs_html, "https://cs.tsinghua.edu.cn/szdw.htm", "Computer Science", 8)
    assert score >= 5
    assert tier == "HIGH_AUTO_APPROVE"

    # Phase 2A link audit drops nav/sidebar, /list.htm, news date paths, and admin slugs
    roster_html = """<html><body>
      <nav><a href="https://cs.test.edu.cn/nav_link.htm">张伟</a></nav>
      <aside class="sidebar"><a href="https://cs.test.edu.cn/side.htm">李明</a></aside>
      <main>
        <a href="https://cs.test.edu.cn/faculty/list.htm">张伟</a>
        <a href="https://cs.test.edu.cn/2025/0412/c100a999/page.htm">李明</a>
        <a href="https://cs.test.edu.cn/OpenPositions/hiring.htm">王芳</a>
        <a href="https://cs.test.edu.cn/info/1001/chenhua.htm">陈华</a>
      </main>
    </body></html>"""
    urls, audit = extract_profile_urls_with_audit(roster_html, "https://cs.test.edu.cn/szdw.htm", root_domain="test.edu.cn")
    assert urls == ["https://cs.test.edu.cn/info/1001/chenhua.htm"]
    assert audit["kept_count"] == 1
    assert audit["dropped_breakdown"]["nav_sidebar"] == 2
    assert audit["dropped_breakdown"]["list_index"] == 1
    assert audit["dropped_breakdown"]["news_date"] == 1
    assert audit["dropped_breakdown"]["admin_slug"] == 1


def test_obfuscated_email_nfkc_whitespace_and_roster_context_grounding():
    assert decode_obfuscated_email("shinningliu at 163 dot com") == "shinningliu@163.com"
    assert decode_obfuscated_email("prof.li#tsinghua.edu.cn") == "prof.li@tsinghua.edu.cn"
    email, st = extract_email_regex("Contact: shinningliu at 163 dot com")
    assert email == "shinningliu@163.com"
    assert st == "FOUND"

    # Full-width space \u3000, NBSP \xa0, zero-width \u200b, and multi-line breaks pass grounding
    md = "张\u3000伟\u200b\n\n教授，\xa0博士生\n导师"
    ok, reason = verify_professor_grounding(md, "", "张伟", "博士生导师")
    assert ok is True, reason

    # Parent verified roster_context passes when roster URL explicitly indicates Master's/PhD supervisors
    ok_ctx, _ = verify_professor_grounding("# Wei Zhang\nAssociate Professor", "", "Wei Zhang", "roster_context", source_roster_url="https://cs.test.edu.cn/ssyjsds/list.htm")
    assert ok_ctx is True


@pytest.mark.asyncio
async def test_adaptive_backpressure_5_to_1_recovery_tier1_thinking_off_and_tier2_pacing():
    mgr = MongoManager(uri=settings.MONGODB_URI, db_name="autoadmit_p12_test_bp")
    db = await mgr.connect()
    try:
        repo = Repository(db)
        captured_t1_payloads: list[dict] = []
        t1_mode = {"fail": True}

        def handler(req: httpx.Request) -> httpx.Response:
            body = json.loads(req.content.decode())
            if "colab.test" in str(req.url):
                captured_t1_payloads.append(body)
                if t1_mode["fail"]:
                    return httpx.Response(502, text="no tunnel")
                return httpx.Response(
                    200,
                    json={
                        "choices": [{"message": {"content": '{"ok": true}'}}],
                        "usage": {"prompt_tokens": 120, "completion_tokens": 20, "total_tokens": 140},
                    },
                )
            if "deepseek.test" in str(req.url):
                return httpx.Response(
                    200,
                    json={
                        "choices": [{"message": {"content": '{"ok": "deepseek"}'}}],
                        "usage": {"prompt_tokens": 100, "completion_tokens": 15, "total_tokens": 115},
                    },
                )
            return httpx.Response(404)

        router = LLMRouter(
            colab=LLMEndpoint("colab_qwen", "https://colab.test/v1", "ck", "Qwen/Qwen3-8B-AWQ", tier=1, auth_header="X-API-Key"),
            primary=LLMEndpoint("primary", "https://deepseek.test/v1", "pk", "deepseek-v4-1-flash-1017", tier=2),
            backup=LLMEndpoint("backup", "", "", "", tier=3),
            tier2_min_interval_sec=0.15,
            colab_cooldown_sec=60.0,
            trace_repo=repo,
        )

        # 1. Tier 1 returns 502 -> trips circuit, throttles 5 -> 1, fails over to Tier 2
        r1 = await router.complete([{"role": "user", "content": "hi"}], json_mode=True, transport=httpx.MockTransport(handler))
        assert r1.ok is True
        assert r1.data["tier"] == 2
        assert router.queue_mode == "THROTTLED_1X_8_5RPM"
        assert router.active_concurrency == 1
        assert captured_t1_payloads[0]["chat_template_kwargs"] == {"enable_thinking": False}

        # 2. Second Tier 2 call respects pacing interval (>= 0.15s)
        t0 = time.perf_counter()
        r2 = await router.complete([{"role": "user", "content": "hi2"}], transport=httpx.MockTransport(handler))
        elapsed = time.perf_counter() - t0
        assert r2.ok is True
        assert elapsed >= 0.12

        # 3. Tier 1 recovers -> 2 consecutive healthy T1 calls < 12s restore PARALLEL_5X (5x)
        t1_mode["fail"] = False
        router.reset_colab_circuit()
        r3 = await router.complete([{"role": "user", "content": "ok1"}], transport=httpx.MockTransport(handler))
        r4 = await router.complete([{"role": "user", "content": "ok2"}], transport=httpx.MockTransport(handler))
        assert r3.ok and r3.data["tier"] == 1
        assert r4.ok and r4.data["tier"] == 1
        assert router.queue_mode == "PARALLEL_5X"
        assert router.active_concurrency == 5
    finally:
        await mgr.client.drop_database("autoadmit_p12_test_bp")
        await mgr.close()


@pytest.mark.asyncio
async def test_benchmark_api_grounding_audit_faculty_rank_and_debug_bundle():
    mgr = MongoManager(uri=settings.MONGODB_URI, db_name="autoadmit_p12_test_bench")
    db = await mgr.connect()
    try:
        repo = Repository(db)

        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": '{"name":"张伟","name_en":"Wei Zhang"}'}}],
                    "usage": {"prompt_tokens": 450, "completion_tokens": 30, "total_tokens": 480},
                },
            )

        bench_router = LLMRouter(
            colab=LLMEndpoint("colab_qwen", "https://colab.test/v1", "ck", "Qwen/Qwen3-8B-AWQ", tier=1, auth_header="X-API-Key"),
            primary=LLMEndpoint("primary", "", "", "", tier=2),
            backup=LLMEndpoint("backup", "", "", "", tier=3),
            trace_repo=repo,
        )

        # Wrap transport for benchmark_router
        orig_complete = bench_router.complete
        async def _patched_complete(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            return await orig_complete(*args, **kwargs)
        bench_router.complete = _patched_complete  # type: ignore[method-assign]

        # Test Phase 2B: raw=[] + Associate Professor (no explicit negation) passes instead of false NEGATED_SUPERVISOR
        class StubExtRouter:
            async def complete(self, messages, **kwargs):
                return StepResult.success({
                    "content": json.dumps({
                        "name": "Kuan Yang",
                        "name_en": "Kuan Yang",
                        "title": "Associate Professor",
                        "title_en": "Associate Professor",
                        "email": "kyang at sjtu dot edu dot cn",
                        "degree_eligibility": [],
                        "research_interests": ["Security"],
                        "research_areas_en": ["Security"],
                        "name_evidence_quote": "Kuan Yang",
                        "supervisor_evidence_quote": "Associate Professor",
                    }),
                    "tier": 1,
                    "provider": "colab_qwen",
                    "model": "Qwen/Qwen3-8B-AWQ",
                    "latency_ms": 90,
                })

        ext = Phase2ExtractorService(repo, router=StubExtRouter(), admin=AdminConfig())
        snap = PageSnapshotDoc(
            url="https://cs.sjtu.edu.cn/people/kuan-yang.html",
            domain="sjtu.edu.cn",
            markdown="# Kuan Yang\nAssociate Professor\nEmail: kyang at sjtu dot edu dot cn",
            sha256="s1",
            breadcrumb="Faculty",
        )
        res_ok = await ext.extract_from_snapshot(snap, department="Computer Science", source_roster_url="https://cs.sjtu.edu.cn/faculty")
        assert res_ok.ok is True
        assert res_ok.data.email == "kyang@sjtu.edu.cn"
        assert "masters" in res_ok.data.degree_eligibility

        # Explicit negation still rejects and saves grounding_audit
        snap_ret = PageSnapshotDoc(
            url="https://cs.sjtu.edu.cn/people/retired.html",
            domain="sjtu.edu.cn",
            markdown="# Kuan Yang\nAssociate Professor (Retired, not recruiting)",
            sha256="s2",
            breadcrumb="Faculty",
        )
        res_rej = await ext.extract_from_snapshot(snap_ret, department="Computer Science", source_roster_url="https://cs.sjtu.edu.cn/faculty")
        assert res_rej.ok is False
        revs = await repo.list_needs_review(domain="sjtu.edu.cn")
        assert len(revs) == 1
        assert "raw_llm_output" in revs[0].grounding_audit
        assert "markdown_excerpt" in revs[0].grounding_audit

        # Test Benchmark API + Debug Bundle API
        app = create_app(manager=mgr)
        app.state.repo = repo
        app.state.benchmark_router = bench_router

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            r_b = await client.post(
                "/api/v1/analytics/benchmark",
                json={"provider": "colab_qwen", "concurrency": 2, "payload_size": "nav_500", "batch_size": 5},
            )
            assert r_b.status_code == 200
            bdata = r_b.json()
            assert bdata["ok_count"] == 5
            assert bdata["avg_input_tokens"] == 450.0
            assert bdata["requests_per_min"] > 0

            r_list = await client.get("/api/v1/analytics/benchmarks")
            assert r_list.status_code == 200
            assert len(r_list.json()) == 1

            r_dbg = await client.get("/api/v1/export/debug-bundle")
            assert r_dbg.status_code == 200
            bundle = r_dbg.json()
            assert "api_call_traces" in bundle
            assert "http_fetch_traces" in bundle
            assert "phase2_link_audits" in bundle
            assert len(bundle["needs_review"]) == 1
            assert "grounding_audit" in bundle["needs_review"][0]
    finally:
        await mgr.client.drop_database("autoadmit_p12_test_bench")
        await mgr.close()
