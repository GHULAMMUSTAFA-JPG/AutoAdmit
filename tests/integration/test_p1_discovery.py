"""Phase P1 Test: Discovery, Feasibility Scoring, and Pre-Run Cost Gate Verification."""

import pytest
from fastapi.testclient import TestClient
from src.services.discovery import discovery_engine
from src.models.university import FeasibilityTier, DepartmentEndpoint


def test_p1_feasibility_scoring_tiers():
    """Verify feasibility matrix compensates 2.68 CGPA and categorizes into Dream/Target/Safety."""
    # Tsinghua -> Tier 1 (Dream)
    tsinghua = discovery_engine.assess_university("tsinghua.edu.cn")
    assert tsinghua.tier == FeasibilityTier.TIER_1_DREAM
    assert tsinghua.is_project_985 is True
    assert "Dream" in tsinghua.feasibility_notes
    assert "Project 985" in tsinghua.feasibility_notes

    # Beihang -> Tier 2 (Target)
    buaa = discovery_engine.assess_university("buaa.edu.cn")
    assert buaa.tier == FeasibilityTier.TIER_2_TARGET
    assert buaa.is_project_211 is True

    # NUIST -> Tier 3 (Safety)
    nuist = discovery_engine.assess_university("nuist.edu.cn")
    assert nuist.tier == FeasibilityTier.TIER_3_SAFETY
    assert nuist.application_fee_rmb == 0


def test_p1_pre_run_cost_gate_locking(client: TestClient, auth_headers: dict):
    """Verify execution sequence remains locked until Pre-Run Cost Gate is approved."""
    endpoints = [
        {"name": "School of Computer Science", "url": "https://cs.tsinghua.edu.cn/faculty"},
        {"name": "School of Artificial Intelligence", "url": "https://ai.pku.edu.cn/supervisors"}
    ]

    # 1. Request Cost Estimate
    est_res = client.post("/api/v1/discovery/estimate", json=endpoints, headers=auth_headers)
    assert est_res.status_code == 200
    estimate = est_res.json()
    assert estimate["total_target_departments"] == 2
    assert estimate["estimated_faculty_count"] > 0
    assert estimate["estimated_gemini_tokens"] > 0
    assert estimate["is_approved"] is False

    # 2. Attempt to harvest without approving gate -> Must return 403 Forbidden!
    harvest_res = client.post(
        "/api/v1/professors/harvest",
        json={
            "department_urls": ["https://cs.tsinghua.edu.cn/faculty"],
            "university_name": "Tsinghua University"
        },
        headers=auth_headers
    )
    assert harvest_res.status_code == 403
    assert "Pre-Run Cost Gate is LOCKED" in harvest_res.json()["detail"]

    # 3. Explicitly approve gate
    appr_res = client.post("/api/v1/discovery/approve", headers=auth_headers)
    assert appr_res.status_code == 200
    assert appr_res.json()["is_approved"] is True


def test_p1_subject_rankings_and_telemetry_scorecard():
    """Verify static subject rankings, structured JSONL telemetry emission, and self-measuring JobScorecard."""
    from src.core.telemetry import ErrorCode, JobScorecard, TerminalStatus, phase1_logger

    tsinghua = discovery_engine.assess_university("tsinghua.edu.cn")
    assert tsinghua.cs_ranking == 1
    assert tsinghua.subject_rankings.get("ai") == 1

    event = phase1_logger.emit(
        trace_id="test_trace_01",
        university_domain="uestc.edu.cn",
        discipline="computer_science",
        layer="L2_NAV_PARSE",
        action="FALLBACK_TRIGGERED",
        next_layer="L3_SEARCH_API",
        level="WARNING",
        http_status=200,
        latency_ms=1200,
        error_code=ErrorCode.DEPT_LINK_NOT_FOUND,
        error_detail="0 matched anchors",
    )
    assert event["error_code"] == "DEPT_LINK_NOT_FOUND"
    assert phase1_logger.jsonl_path.exists()

    sc = JobScorecard(job_id="job_test_01", target_universities=2)
    sc.record_outcome(
        status=TerminalStatus.COMPLETE,
        resolved_by_layer="L2_HTTP_NAV",
        latency_ms=900,
        homepage_ok=True,
        dept_ok=True,
        roster_ok=True,
        from_cache=False,
    )
    sc.record_outcome(
        status=TerminalStatus.NEEDS_REVIEW,
        resolved_by_layer=None,
        latency_ms=3100,
        homepage_ok=False,
        dept_ok=False,
        roster_ok=False,
        from_cache=False,
        error_code=ErrorCode.WAF_CHALLENGE_BLOCKED,
        search_calls=1,
        cost_usd=0.001,
    )
    report = sc.to_dict()
    assert report["funnel"]["4_department_resolved"] == 1
    assert report["terminal_statuses"]["COMPLETE"] == 1
    assert report["terminal_statuses"]["NEEDS_REVIEW"] == 1
    assert report["error_breakdown"]["WAF_CHALLENGE_BLOCKED"] == 1
    assert report["cost_economics"]["search_api_calls"] == 1


@pytest.mark.asyncio
async def test_p1_policies_search_provider_and_content_gate():
    """Verify ToolPolicyManager budget caps, SearchFirstProvider query/filtering, and Content Gate SSO rejection."""
    from src.core.policies import policy_manager
    from src.core.telemetry import ErrorCode
    from src.services.search_provider import search_provider

    # 1. Verify search query expansion
    q = search_provider.build_site_query("tsinghua.edu.cn", "Artificial Intelligence")
    assert "site:tsinghua.edu.cn" in q
    assert "人工智能" in q

    # 2. Verify domain & SSO filtering
    filtered = search_provider._classify_and_filter_items(
        [
            {"url": "https://login.tsinghua.edu.cn/cas", "title": "统一身份认证", "snippet": ""},
            {"url": "https://other.edu.cn/faculty", "title": "师资队伍", "snippet": ""},
            {"url": "https://ai.tsinghua.edu.cn/szdw/ssds.htm", "title": "人工智能学院 - 硕士生导师", "snippet": "硕导名录"},
        ],
        domain="tsinghua.edu.cn",
        provider_name="serper",
    )
    assert len(filtered) == 1
    assert filtered[0].is_faculty_roster is True
    assert filtered[0].inherited_degree == "master"

    # 3. Verify monthly budget cap enforcement
    policy_manager.update_policies(enable_search_api=True, monthly_search_cap=1, reset_search_counter=True)
    ok1, code1, _ = await policy_manager.reserve_search_call()
    assert ok1 is True and code1 == ErrorCode.NONE
    ok2, code2, _ = await policy_manager.reserve_search_call()
    assert ok2 is False and code2 == ErrorCode.BUDGET_CAP_EXCEEDED
    policy_manager.update_policies(enable_search_api=True, monthly_search_cap=1000, reset_search_counter=True)

    # 4. Verify Content Gate rejects SSO login portals
    sso_gate = discovery_engine.verify_content_gate(
        "<html><head><title>统一身份认证 - 用户登录</title></head><body>Please login to WebVPN</body></html>",
        "https://webvpn.tsinghua.edu.cn/login",
    )
    assert sso_gate.ok is False
    assert sso_gate.error_code == ErrorCode.FALSE_POSITIVE_PAGE


def test_p1_async_jobs_cache_and_review_queue_endpoints(client: TestClient, auth_headers: dict):
    """Verify Phase 1 async job endpoints, TTL cache hit, scorecard endpoint, review queue, and policy endpoints."""
    from datetime import datetime, timedelta, timezone
    from src.models.university import FacultyRosterEndpoint, UniversityDepartmentCache

    now = datetime.now(timezone.utc)
    # Pre-seed 1 COMPLETE cached record and 1 NEEDS_REVIEW record
    discovery_engine._dept_cache_memory[("tsinghua.edu.cn", "computer_science")] = UniversityDepartmentCache(
        domain="tsinghua.edu.cn",
        university_name="Tsinghua University",
        discipline_key="computer_science",
        department_name_zh="计算机科学与技术系",
        department_name_en="Computer Science",
        department_url="https://www.cs.tsinghua.edu.cn/",
        homepage_url="https://www.tsinghua.edu.cn/",
        faculty_roster_urls=[
            FacultyRosterEndpoint(
                url="https://www.cs.tsinghua.edu.cn/szdw.htm",
                label_zh="计算机系 > 硕士生导师",
                inherited_degree="master",
            )
        ],
        status="COMPLETE",
        confidence="HIGH",
        discovery_path=["CACHE_SEED"],
        last_error_code="NONE",
        resolved_by_layer="L2_HTTP_NAV",
        fetched_at=now,
        expires_at=now + timedelta(days=90),
    )
    discovery_engine._dept_cache_memory[("blocked.edu.cn", "computer_science")] = UniversityDepartmentCache(
        domain="blocked.edu.cn",
        university_name="Blocked University",
        discipline_key="computer_science",
        status="NEEDS_REVIEW",
        confidence="LOW",
        discovery_path=["CACHE_MISS", "L1_FAIL:WAF_CHALLENGE_BLOCKED"],
        last_error_code="WAF_CHALLENGE_BLOCKED",
        error_detail="HTTP 412 WAF block",
        fetched_at=now,
        expires_at=now + timedelta(days=7),
    )

    # 1. Create Phase 1 Discovery Job (run_sync=True hits the warm cache for tsinghua.edu.cn)
    job_res = client.post(
        "/api/v1/discovery/jobs",
        json={
            "disciplines": ["Computer Science"],
            "domains": ["tsinghua.edu.cn"],
            "force_refresh": False,
            "run_sync": True,
        },
        headers=auth_headers,
    )
    assert job_res.status_code == 202
    job_id = job_res.json()["job_id"]

    # 2. Fetch Scorecard
    sc_res = client.get(f"/api/v1/discovery/jobs/{job_id}/scorecard", headers=auth_headers)
    assert sc_res.status_code == 200
    sc_data = sc_res.json()
    assert sc_data["funnel"]["1_cache_hits"] == 1
    assert sc_data["terminal_statuses"]["COMPLETE"] == 1

    # 3. Fetch Review Queue
    rq_res = client.get("/api/v1/discovery/review-queue", headers=auth_headers)
    assert rq_res.status_code == 200
    rq_domains = [r["domain"] for r in rq_res.json()]
    assert "blocked.edu.cn" in rq_domains

    # 4. Inspect & update policies
    pol_res = client.post(
        "/api/v1/discovery/policies",
        json={"monthly_search_cap": 500},
        headers=auth_headers,
    )
    assert pol_res.status_code == 200
    assert pol_res.json()["monthly_search_cap"] == 500


