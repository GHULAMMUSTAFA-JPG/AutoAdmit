"""Slice 5 Tests: Regex email pre-check, LLM structured extraction, NFKC Grounding Gate, negation rejection, idempotency."""

import json
from unittest.mock import AsyncMock
import pytest

from app.core.config import settings
from app.core.types import ErrorCode, StepResult
from app.db.mongo import MongoManager
from app.db.repositories import Repository
from app.schemas.entities import PageSnapshotDoc
from app.services.phase2_extractor import Phase2ExtractorService, extract_email_regex


def test_regex_email_deobfuscation_and_image_detection():
    email1, st1 = extract_email_regex("Contact: zhangwei [at] tsinghua [dot] edu [dot] cn")
    assert email1 == "zhangwei@tsinghua.edu.cn"
    assert st1 == "FOUND"

    email2, st2 = extract_email_regex("邮箱：[EMAIL_IMAGE_TAG]")
    assert email2 == ""
    assert st2 == "IMAGE_EMBEDDED"

    email3, st3 = extract_email_regex("No contact info listed.")
    assert email3 == ""
    assert st3 == "MISSING"


@pytest.mark.asyncio
async def test_phase2_extractor_grounding_negation_missing_email_and_idempotency():
    mgr = MongoManager(uri=settings.MONGODB_URI, db_name="autoadmit_p12_test_s5")
    db = await mgr.connect()
    try:
        repo = Repository(db)
        router_mock = AsyncMock()
        svc = Phase2ExtractorService(repo, router=router_mock)

        # 1. Valid fixture + verbatim quote -> passes Grounding Gate & upserts with MISSING email
        snap_ok = PageSnapshotDoc(
            url="https://cs.tsinghua.edu.cn/zw.html",
            domain="tsinghua.edu.cn",
            markdown="# 张伟\n职称：教授，博士生导师\n研究方向：人工智能、计算机视觉",
            sha256="abc",
            breadcrumb="师资队伍 > 博士生导师",
        )
        router_mock.complete.return_value = StepResult.success({
            "content": json.dumps({
                "name": "张伟",
                "title": "教授",
                "email": "",
                "degree_eligibility": ["phd"],
                "research_interests": ["人工智能", "计算机视觉"],
                "name_evidence_quote": "张伟",
                "supervisor_evidence_quote": "职称：教授，博士生导师",
            }),
            "provider": "primary",
            "model": "mock",
        })
        res1 = await svc.extract_from_snapshot(snap_ok, department="Computer Science", source_roster_url="https://cs.tsinghua.edu.cn/szdw")
        assert res1.ok is True
        assert res1.data.email_status == "MISSING"
        assert res1.data.grounding_status == "VERIFIED"

        # Idempotent re-run on same URL creates no duplicate
        res1_again = await svc.extract_from_snapshot(snap_ok, department="Computer Science", source_roster_url="https://cs.tsinghua.edu.cn/szdw")
        assert res1_again.ok is True
        assert await db["professors"].count_documents({"canonical_profile_url": snap_ok.url}) == 1

        # 2. Hallucinated quote fails Grounding Gate & routes to needs_review (blocked from professors)
        snap_halluc = PageSnapshotDoc(
            url="https://cs.tsinghua.edu.cn/fake.html",
            domain="tsinghua.edu.cn",
            markdown="# 李明\n讲师",
            sha256="def",
            breadcrumb="",
        )
        router_mock.complete.return_value = StepResult.success({
            "content": json.dumps({
                "name": "李明",
                "title": "教授",
                "email": "",
                "degree_eligibility": ["phd"],
                "research_interests": [],
                "name_evidence_quote": "李明",
                "supervisor_evidence_quote": "发明的不存在的博导句子",
            }),
            "provider": "primary",
            "model": "mock",
        })
        res_bad = await svc.extract_from_snapshot(snap_halluc, department="Computer Science", source_roster_url="https://cs.tsinghua.edu.cn/szdw")
        assert res_bad.ok is False
        assert res_bad.error_code == ErrorCode.GROUNDING_FAILED.value
        assert await db["professors"].count_documents({"canonical_profile_url": snap_halluc.url}) == 0
        assert await db["needs_review"].count_documents({"url": snap_halluc.url}) == 1

        # 3. Negation (非博导) is caught and rejected for PhD eligibility
        snap_neg = PageSnapshotDoc(
            url="https://cs.tsinghua.edu.cn/neg.html",
            domain="tsinghua.edu.cn",
            markdown="# 王芳\n职称：讲师，非博导",
            sha256="ghi",
            breadcrumb="",
        )
        router_mock.complete.return_value = StepResult.success({
            "content": json.dumps({
                "name": "王芳",
                "title": "讲师",
                "email": "",
                "degree_eligibility": ["phd"],
                "research_interests": [],
                "name_evidence_quote": "王芳",
                "supervisor_evidence_quote": "非博导",
            }),
            "provider": "primary",
            "model": "mock",
        })
        res_neg = await svc.extract_from_snapshot(snap_neg, department="Computer Science", source_roster_url="https://cs.tsinghua.edu.cn/szdw")
        assert res_neg.ok is False
        assert res_neg.error_code == ErrorCode.NEGATED_SUPERVISOR.value
        assert await db["professors"].count_documents({"canonical_profile_url": snap_neg.url}) == 0

        # 4. IMAGE_EMBEDDED email + NFKC fullwidth colon + 硕导：否 negation keeps phd only
        snap_img = PageSnapshotDoc(
            url="https://cs.tsinghua.edu.cn/img_prof.html",
            domain="tsinghua.edu.cn",
            markdown="# 赵雷\n博士生导师，硕导：否\n邮箱：[EMAIL_IMAGE_TAG]",
            sha256="jkl",
            breadcrumb="",
        )
        router_mock.complete.return_value = StepResult.success({
            "content": json.dumps({
                "name": "赵雷",
                "title": "教授",
                "email": "",
                "degree_eligibility": ["masters", "phd"],
                "research_interests": ["NLP"],
                "name_evidence_quote": "赵雷",
                "supervisor_evidence_quote": "博士生导师,硕导:否",  # half-width punctuation tested via NFKC
            }),
            "provider": "primary",
            "model": "mock",
        })
        # Note: comma differs (Chinese '，' vs ASCII ','), so use exact NFKC-equivalent quote with full-width/half-width colon
        router_mock.complete.return_value = StepResult.success({
            "content": json.dumps({
                "name": "赵雷",
                "title": "教授",
                "email": "",
                "degree_eligibility": ["masters", "phd"],
                "research_interests": ["NLP"],
                "name_evidence_quote": "赵雷",
                "supervisor_evidence_quote": "硕导:否",
            }),
            "provider": "primary",
            "model": "mock",
        })
        res_img = await svc.extract_from_snapshot(snap_img, department="Computer Science", source_roster_url="https://cs.tsinghua.edu.cn/szdw")
        assert res_img.ok is True
        assert res_img.data.email_status == "IMAGE_EMBEDDED"
        assert res_img.data.degree_eligibility == ["phd"]

        # 5. AdminConfig enable_llm_extraction=False cleanly skips LLM
        from app.schemas.filters import AdminConfig
        svc_disabled = Phase2ExtractorService(repo, router=router_mock, admin=AdminConfig(enable_llm_extraction=False))
        res_dis = await svc_disabled.extract_from_snapshot(snap_img, department="Computer Science", source_roster_url="https://cs.tsinghua.edu.cn/szdw")
        assert res_dis.ok is False
        assert res_dis.error_code == ErrorCode.LLM_ERROR.value
    finally:
        await mgr.client.drop_database("autoadmit_p12_test_s5")
        await mgr.close()
