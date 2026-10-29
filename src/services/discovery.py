"""University Discovery, Feasibility Scoring (2.68 CGPA Compensation), and Pre-Run Cost Gate."""

from datetime import datetime, timezone
from typing import Dict, List, Optional
from src.core.logger import setup_logger
from src.models.university import (
    DepartmentEndpoint,
    FeasibilityTier,
    PreRunCostEstimate,
    ScholarshipType,
    University,
)

logger = setup_logger("DiscoveryService")


# Knowledge base of Chinese Universities with scholarship, region, and barrier metadata
KNOWN_UNIVERSITIES_METADATA: Dict[str, Dict] = {
    "tsinghua.edu.cn": {
        "name": "Tsinghua University",
        "chinese_name": "清华大学",
        "region": "Beijing",
        "tier": FeasibilityTier.TIER_1_DREAM,
        "cs_ranking": 1,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 800,
        "scholarships": [ScholarshipType.CSC_TYPE_B, ScholarshipType.PRESIDENTIAL],
        "feasibility_notes": "Tier 1 Dream. Strict academic cutoffs. Focus outreach toward early-career faculty / Associate Professors and new engineering labs requiring hands-on output."
    },
    "pku.edu.cn": {
        "name": "Peking University",
        "chinese_name": "北京大学",
        "region": "Beijing",
        "tier": FeasibilityTier.TIER_1_DREAM,
        "cs_ranking": 2,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 800,
        "scholarships": [ScholarshipType.CSC_TYPE_B, ScholarshipType.PRESIDENTIAL],
        "feasibility_notes": "Tier 1 Dream. Focus on Key State Labs in AI and software engineering."
    },
    "zju.edu.cn": {
        "name": "Zhejiang University",
        "chinese_name": "浙江大学",
        "region": "Zhejiang",
        "tier": FeasibilityTier.TIER_1_DREAM,
        "cs_ranking": 3,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 800,
        "scholarships": [ScholarshipType.CSC_TYPE_B, ScholarshipType.PROVINCIAL, ScholarshipType.PRESIDENTIAL],
        "feasibility_notes": "Tier 1 Dream. College of Computer Science & Technology labs working on vision and robotics."
    },
    "sjtu.edu.cn": {
        "name": "Shanghai Jiao Tong University",
        "chinese_name": "上海交通大学",
        "region": "Shanghai",
        "tier": FeasibilityTier.TIER_1_DREAM,
        "cs_ranking": 4,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 800,
        "scholarships": [ScholarshipType.CSC_TYPE_B, ScholarshipType.PROVINCIAL],
        "feasibility_notes": "Tier 1 Dream. Direct outreach to AI Institute engineering labs."
    },
    "fudan.edu.cn": {
        "name": "Fudan University",
        "chinese_name": "复旦大学",
        "region": "Shanghai",
        "tier": FeasibilityTier.TIER_1_DREAM,
        "cs_ranking": 5,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 800,
        "scholarships": [ScholarshipType.CSC_TYPE_B, ScholarshipType.PROVINCIAL, ScholarshipType.PRESIDENTIAL],
        "feasibility_notes": "Tier 1 Dream. School of Computer Science research groups in NLP and systems."
    },
    "buaa.edu.cn": {
        "name": "Beihang University",
        "chinese_name": "北京航空航天大学",
        "region": "Beijing",
        "tier": FeasibilityTier.TIER_2_TARGET,
        "cs_ranking": 8,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 400,
        "scholarships": [ScholarshipType.CSC_TYPE_B, ScholarshipType.PRESIDENTIAL],
        "feasibility_notes": "Tier 2 Target. Project 985/211 engineering powerhouse. Receptive to biometric systems and applied ML pipelines."
    },
    "hit.edu.cn": {
        "name": "Harbin Institute of Technology",
        "chinese_name": "哈尔滨工业大学",
        "region": "Heilongjiang",
        "tier": FeasibilityTier.TIER_2_TARGET,
        "cs_ranking": 9,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 400,
        "scholarships": [ScholarshipType.CSC_TYPE_B, ScholarshipType.PRESIDENTIAL],
        "feasibility_notes": "Tier 2 Target. Outstanding CS faculty with high quota for research scholars in NLP and automation."
    },
    "xidian.edu.cn": {
        "name": "Xidian University",
        "chinese_name": "西安电子科技大学",
        "region": "Shaanxi",
        "tier": FeasibilityTier.TIER_2_TARGET,
        "cs_ranking": 12,
        "is_project_985": False,
        "is_project_211": True,
        "application_fee_rmb": 0,
        "scholarships": [ScholarshipType.CSC_TYPE_B, ScholarshipType.BELT_AND_ROAD],
        "feasibility_notes": "Tier 2 Target. Project 211 National Key. Zero application fee barrier. Strong alignment with AI & signals."
    },
    "xjtu.edu.cn": {
        "name": "Xi'an Jiaotong University",
        "chinese_name": "西安交通大学",
        "region": "Shaanxi",
        "tier": FeasibilityTier.TIER_2_TARGET,
        "cs_ranking": 10,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 800,
        "scholarships": [ScholarshipType.CSC_TYPE_B, ScholarshipType.PRESIDENTIAL],
        "feasibility_notes": "Tier 2 Target. C9 League institution with large AI research institute."
    },
    "hust.edu.cn": {
        "name": "Huazhong Univ. of Science and Technology",
        "chinese_name": "华中科技大学",
        "region": "Hubei",
        "tier": FeasibilityTier.TIER_2_TARGET,
        "cs_ranking": 7,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 600,
        "scholarships": [ScholarshipType.CSC_TYPE_B, ScholarshipType.PRESIDENTIAL],
        "feasibility_notes": "Tier 2 Target. Project 985 top engineering hub in central China."
    },
    "uestc.edu.cn": {
        "name": "Univ. of Electronic Science & Tech of China",
        "chinese_name": "电子科技大学",
        "region": "Sichuan",
        "tier": FeasibilityTier.TIER_2_TARGET,
        "cs_ranking": 11,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 420,
        "scholarships": [ScholarshipType.CSC_TYPE_B, ScholarshipType.PRESIDENTIAL],
        "feasibility_notes": "Tier 2 Target. Outstanding CS/AI research facilities and high quota for international researchers."
    },
    "sysu.edu.cn": {
        "name": "Sun Yat-sen University",
        "chinese_name": "中山大学",
        "region": "Guangdong",
        "tier": FeasibilityTier.TIER_2_TARGET,
        "cs_ranking": 13,
        "is_project_985": True,
        "is_project_211": True,
        "application_fee_rmb": 800,
        "scholarships": [ScholarshipType.CSC_TYPE_B, ScholarshipType.PROVINCIAL, ScholarshipType.PRESIDENTIAL],
        "feasibility_notes": "Tier 2 Target. Top southern comprehensive university with major AI School in Shenzhen campus."
    },
    "bjtu.edu.cn": {
        "name": "Beijing Jiaotong University",
        "chinese_name": "北京交通大学",
        "region": "Beijing",
        "tier": FeasibilityTier.TIER_2_TARGET,
        "cs_ranking": 15,
        "is_project_985": False,
        "is_project_211": True,
        "application_fee_rmb": 500,
        "scholarships": [ScholarshipType.CSC_TYPE_B, ScholarshipType.PRESIDENTIAL],
        "feasibility_notes": "Tier 2 Target. Project 211 engineering hub. Evaluates candidates on technical portfolio."
    },
    "nuist.edu.cn": {
        "name": "Nanjing Univ. of Information Science & Tech",
        "chinese_name": "南京信息工程大学",
        "region": "Jiangsu",
        "tier": FeasibilityTier.TIER_3_SAFETY,
        "cs_ranking": 35,
        "is_project_985": False,
        "is_project_211": False,
        "application_fee_rmb": 0,
        "scholarships": [ScholarshipType.CSC_TYPE_B, ScholarshipType.PROVINCIAL, ScholarshipType.PRESIDENTIAL],
        "feasibility_notes": "Tier 3 Safety. High international graduate quotas and full scholarship grants (Jasmine / CSC). High admission probability."
    },
    "jiangnan.edu.cn": {
        "name": "Jiangnan University",
        "chinese_name": "江南大学",
        "region": "Jiangsu",
        "tier": FeasibilityTier.TIER_3_SAFETY,
        "cs_ranking": 42,
        "is_project_985": False,
        "is_project_211": True,
        "application_fee_rmb": 0,
        "scholarships": [ScholarshipType.CSC_TYPE_B, ScholarshipType.PROVINCIAL, ScholarshipType.PRESIDENTIAL],
        "feasibility_notes": "Tier 3 Safety. Project 211 with accessible admission minimums, 0 application fee, and high acceptance of external CSC candidates."
    }
}


class DiscoveryEngine:
    """Handles intake parsing, feasibility categorization, and pre-run cost estimation."""

    def __init__(self):
        self.pending_approval_runs: Dict[str, PreRunCostEstimate] = {}

    def assess_university(self, domain: str, name: Optional[str] = None) -> University:
        """Determines institutional feasibility tier and scholarship matrix for a given university domain."""
        domain_clean = domain.lower().strip().replace("http://", "").replace("https://", "").split("/")[0]
        # Match root educational domain
        matched_meta = None
        for key, meta in KNOWN_UNIVERSITIES_METADATA.items():
            if domain_clean.endswith(key) or key in domain_clean:
                matched_meta = meta
                domain_clean = key
                break

        if matched_meta:
            return University(
                id=domain_clean.replace(".", "-"),
                name=matched_meta["name"],
                chinese_name=matched_meta.get("chinese_name"),
                domain=domain_clean,
                region=matched_meta.get("region", "National"),
                tier=matched_meta["tier"],
                cs_ranking=matched_meta.get("cs_ranking"),
                is_project_985=matched_meta.get("is_project_985", False),
                is_project_211=matched_meta.get("is_project_211", False),
                scholarships_available=matched_meta.get("scholarships", [ScholarshipType.CSC_TYPE_B]),
                application_fee_rmb=matched_meta.get("application_fee_rmb", 0),
                feasibility_notes=matched_meta.get("feasibility_notes", ""),
                created_at=datetime.now(timezone.utc)
            )

        # Default fallback for unlisted accredited .edu.cn domain
        return University(
            id=domain_clean.replace(".", "-"),
            name=name or domain_clean.split(".")[0].upper() + " University",
            domain=domain_clean,
            region="National",
            tier=FeasibilityTier.TIER_3_SAFETY,
            cs_ranking=None,
            is_project_985=False,
            is_project_211=False,
            scholarships_available=[ScholarshipType.CSC_TYPE_B, ScholarshipType.PRESIDENTIAL],
            application_fee_rmb=0,
            feasibility_notes="Accredited institution evaluated as Tier 3 Safety. High flexibility on GPA with strong engineering credentials.",
            created_at=datetime.now(timezone.utc)
        )

    def filter_universities(
        self,
        regions: Optional[List[str]] = None,
        tiers: Optional[List[str]] = None,
        max_rank: Optional[int] = None
    ) -> List[University]:
        """Filters Chinese universities dynamically by Region, Tier/Feasibility, and Rank."""
        results = []
        for domain, meta in KNOWN_UNIVERSITIES_METADATA.items():
            univ = self.assess_university(domain)
            if regions and len(regions) > 0 and "All" not in regions:
                if univ.region not in regions:
                    continue
            if tiers and len(tiers) > 0:
                if univ.tier.value not in tiers and univ.tier not in tiers:
                    continue
            if max_rank and univ.cs_ranking and univ.cs_ranking > max_rank:
                continue
            results.append(univ)
        return results

    def discover_department_endpoints(
        self,
        university: University,
        discipline: str = "Computer Science"
    ) -> List[DepartmentEndpoint]:
        """Automatically resolves the relevant faculty directory URLs for CS/AI/SE."""
        d = university.domain
        return [
            DepartmentEndpoint(
                name=f"{university.name} - School of Computer Science",
                url=f"http://cs.{d}/faculty"
            ),
            DepartmentEndpoint(
                name=f"{university.name} - School of Artificial Intelligence",
                url=f"http://ai.{d}/supervisors"
            )
        ]

    def calculate_cost_estimate(self, department_endpoints: List[DepartmentEndpoint]) -> PreRunCostEstimate:
        """
        Calculates estimated pages to crawl, faculty count, Gemini tokens, and runtime.
        Halts execution in a locked pending state until approved.
        """
        num_endpoints = len(department_endpoints)
        # Empirical estimates per department endpoint
        pages_per_dept = 3
        professors_per_dept = 12
        tokens_per_professor = 650  # ~200 tokens prompt digest + ~450 tokens draft outreach
        seconds_per_profile = 2

        est_pages = num_endpoints * pages_per_dept
        est_faculty = num_endpoints * professors_per_dept
        est_tokens = est_faculty * tokens_per_professor
        est_runtime = (num_endpoints * 3) + (est_faculty * seconds_per_profile)

        estimate = PreRunCostEstimate(
            total_target_departments=num_endpoints,
            estimated_pages_to_crawl=est_pages,
            estimated_faculty_count=est_faculty,
            estimated_gemini_tokens=est_tokens,
            estimated_runtime_seconds=est_runtime,
            is_approved=False
        )

        logger.info(
            f"Pre-run cost estimate computed: {num_endpoints} departments, {est_pages} pages, "
            f"~{est_faculty} faculty, ~{est_tokens} tokens. Status: PENDING_APPROVAL"
        )
        return estimate

    def approve_estimate(self, estimate: PreRunCostEstimate) -> PreRunCostEstimate:
        """Unlocks the hard confirmation gate."""
        estimate.is_approved = True
        estimate.approved_at = datetime.now(timezone.utc)
        logger.info("Pre-run cost estimate APPROVED by user. Execution gate unlocked.")
        return estimate


discovery_engine = DiscoveryEngine()

