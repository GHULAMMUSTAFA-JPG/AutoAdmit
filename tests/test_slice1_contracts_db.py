"""Slice 1 Tests: Contracts, Admin Guardrails, Permanent MongoDB Indexes (NO TTL), and Seed Loader."""

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.db.mongo import MongoManager
from app.schemas.filters import AdminConfig, DiscoveryRequest, validate_discovery_request
from scripts.seed_universities import filter_university_seeds, seed_universities


def test_discovery_request_validation_and_guardrails():
    admin = AdminConfig(max_departments_per_request=1, max_universities_per_job=20, allowed_countries=["China"])

    # Valid request passes
    valid_req = DiscoveryRequest(
        country="China",
        regions=[],
        departments=["Computer Science"],
        degree="masters",
        tier="top_10",
    )
    assert validate_discovery_request(valid_req, admin) == 10

    # 2 departments with max_departments_per_request=1 raises 400
    too_many = DiscoveryRequest(
        country="China",
        regions=["Beijing"],
        departments=["Computer Science", "Artificial Intelligence"],
        degree="phd",
        tier="top_10",
    )
    with pytest.raises(HTTPException) as exc:
        validate_discovery_request(too_many, admin)
    assert exc.value.status_code == 400
    assert "Too many departments" in exc.value.detail

    # Disallowed country raises 400
    bad_country = DiscoveryRequest(
        country="Mars",
        departments=["Computer Science"],
        degree="both",
    )
    with pytest.raises(HTTPException) as exc2:
        validate_discovery_request(bad_country, admin)
    assert exc2.value.status_code == 400

    # Limit exceeding max_universities_per_job is capped cleanly
    capped_req = DiscoveryRequest(
        country="China",
        departments=["Computer Science"],
        degree="masters",
        tier="top_50",
    )
    assert validate_discovery_request(capped_req, admin) == 20

    # Invalid tier string raises 400
    bad_tier = DiscoveryRequest(
        country="China",
        departments=["Computer Science"],
        degree="masters",
        tier="invalid_tier",
    )
    with pytest.raises(HTTPException) as exc3:
        validate_discovery_request(bad_tier, admin)
    assert exc3.value.status_code == 400


@pytest.mark.asyncio
async def test_permanent_mongo_indexes_and_seed_filtering():
    manager = MongoManager(uri=settings.MONGODB_URI, db_name="autoadmit_p12_test_s1")
    db = await manager.connect()
    try:
        # 1. Verify permanent indexes exist and NO TTL index exists on page_snapshots
        snap_indexes = await db["page_snapshots"].index_information()
        assert "uniq_snapshot_url" in snap_indexes
        assert snap_indexes["uniq_snapshot_url"].get("unique") is True
        for idx_name, idx_meta in snap_indexes.items():
            assert "expireAfterSeconds" not in idx_meta, f"Unexpected TTL index {idx_name} on page_snapshots"

        dept_indexes = await db["university_departments"].index_information()
        assert "uniq_dept_domain_dept_degree" in dept_indexes
        prof_indexes = await db["professors"].index_information()
        assert "uniq_prof_canonical_url" in prof_indexes

        # 2. Seed and verify region/tier filtering
        seeded = await seed_universities(db)
        assert seeded >= 15

        all_regions = await filter_university_seeds(db, country="China", regions=[], tier="all")
        assert len(all_regions) == seeded

        beijing_only = await filter_university_seeds(db, country="China", regions=["Beijing"], tier="all")
        assert len(beijing_only) >= 3
        assert all(u.region == "Beijing" for u in beijing_only)

        top_5 = await filter_university_seeds(db, country="China", regions=[], tier="top_5")
        assert len(top_5) == 5
        assert [u.rank for u in top_5] == [1, 2, 3, 4, 5]
    finally:
        await manager.client.drop_database("autoadmit_p12_test_s1")
        await manager.close()
