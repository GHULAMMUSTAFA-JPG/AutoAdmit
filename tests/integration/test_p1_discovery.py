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

