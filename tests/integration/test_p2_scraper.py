"""Phase P2 Test: Grounded Scraper, Domain Whitelist, and Supervisor Qualification Gate."""

from pathlib import Path
import pytest
from src.services.scraper import FacultyHarvester, DomainSecurityViolation
from src.services.normalizer import normalizer
from src.models.professor import SupervisorQualification

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "sample_pages"


def test_p2_email_deobfuscation():
    """Verify de-obfuscation cleans diverse anti-spam formats."""
    raw1 = "wangqiang [at] tsinghua (dot) edu (dot) cn"
    assert normalizer.deobfuscate_email(raw1) == "wangqiang@tsinghua.edu.cn"

    raw2 = "prof_zhang (at) hit.edu.cn"
    assert normalizer.deobfuscate_email(raw2) == "prof_zhang@hit.edu.cn"

    raw3 = "chen.ai &#64; zju &#46; edu &#46; cn"
    assert normalizer.deobfuscate_email(raw3) == "chen.ai@zju.edu.cn"


def test_p2_domain_whitelist_and_anti_redirection():
    """Verify crawler rejects unverified domains and unauthorized redirects."""
    # Valid domains
    assert FacultyHarvester.is_verified_domain("http://cs.tsinghua.edu.cn/faculty") is True
    assert FacultyHarvester.is_verified_domain("https://ai.pku.edu.cn/people") is True

    # Commercial or unverified domains -> Must be rejected!
    assert FacultyHarvester.is_verified_domain("https://baidu.com") is False
    assert FacultyHarvester.is_verified_domain("https://scholarship-portal.cn") is False
    assert FacultyHarvester.is_verified_domain("https://third-party-aggregator.com/prof") is False


def test_p2_supervisor_qualification_filtering():
    """Verify supervisor filter extracts 博导/硕导 and drops unverified staff."""
    harvester = FacultyHarvester(worker_id="test-p2-worker")

    # 1. Valid Ph.D. Supervisor (博导)
    valid_file = FIXTURES_DIR / "valid_phd_supervisor.html"
    with open(valid_file, "r", encoding="utf-8") as f:
        html = f.read()

    profile = harvester.parse_profile_html(
        html=html,
        source_url="https://cs.tsinghua.edu.cn/prof/wang",
        university_name="Tsinghua University"
    )

    assert profile is not None
    assert profile.native_name == "王强"
    assert profile.email == "wangqiang@tsinghua.edu.cn"
    assert profile.qualification in [SupervisorQualification.PHD_SUPERVISOR, SupervisorQualification.PHD_SUPERVISOR_SHORT]
    assert profile.is_supervisor is True
    assert len(profile.recent_publications) >= 2
    assert len(profile.content_hash) == 64  # Valid SHA-256

    # 2. Non-supervisor lecturer -> Must be dropped!
    invalid_file = FIXTURES_DIR / "non_supervisor_lecturer.html"
    with open(invalid_file, "r", encoding="utf-8") as f:
        invalid_html = f.read()

    rejected_profile = harvester.parse_profile_html(
        html=invalid_html,
        source_url="https://cs.tsinghua.edu.cn/lecturer/li",
        university_name="Tsinghua University"
    )

    assert rejected_profile is None

    # 3. Inherited breadcrumb qualification (from Phase 1 '硕士生导师' directory) when profile omits explicit marker
    inherited_html = """
    <html><head><title>张伟 - 计算机学院</title></head>
    <body>
      <h1>张伟</h1>
      <p>邮箱：zhangwei [at] tsinghua.edu.cn</p>
      <p>研究方向：人工智能、计算机视觉</p>
    </body></html>
    """
    inherited_profile = harvester.parse_profile_html(
        html=inherited_html,
        source_url="https://cs.tsinghua.edu.cn/prof/zhangwei",
        university_name="Tsinghua University",
        inherited_qualification=SupervisorQualification.MASTERS_SUPERVISOR,
    )
    assert inherited_profile is not None
    assert inherited_profile.qualification == SupervisorQualification.MASTERS_SUPERVISOR
    assert inherited_profile.email == "zhangwei@tsinghua.edu.cn"


