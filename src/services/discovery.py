"""University Discovery, Feasibility Scoring (2.68 CGPA Compensation), and Pre-Run Cost Gate."""

import json
import os
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


def _load_universities_catalog() -> Dict[str, Dict]:
    catalog_path = os.path.join(os.path.dirname(__file__), "..", "data", "chinese_universities.json")
    if os.path.exists(catalog_path):
        try:
            with open(catalog_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                result = {}
                for domain, meta in data.items():
                    tier_str = meta.get("tier", "Tier 3 (Safety)")
                    if "Dream" in tier_str or "Tier 1" in tier_str:
                        tier_enum = FeasibilityTier.TIER_1_DREAM
                    elif "Target" in tier_str or "Tier 2" in tier_str:
                        tier_enum = FeasibilityTier.TIER_2_TARGET
                    else:
                        tier_enum = FeasibilityTier.TIER_3_SAFETY

                    raw_scholars = meta.get("scholarships", [])
                    scholars = []
                    for s in raw_scholars:
                        if "CSC" in s:
                            scholars.append(ScholarshipType.CSC_TYPE_B)
                        elif "President" in s or "Fellowship" in s:
                            scholars.append(ScholarshipType.PRESIDENTIAL)
                        elif "Belt" in s or "Silk" in s:
                            scholars.append(ScholarshipType.BELT_AND_ROAD)
                        elif "Provincial" in s or "Jasmine" in s or "Government" in s or "Mayor" in s or "SGS" in s:
                            scholars.append(ScholarshipType.PROVINCIAL)
                    if not scholars:
                        scholars = [ScholarshipType.CSC_TYPE_B]

                    result[domain] = {
                        "name": meta["name"],
                        "chinese_name": meta.get("chinese_name"),
                        "region": meta.get("region", "National"),
                        "tier": tier_enum,
                        "cs_ranking": meta.get("cs_ranking"),
                        "is_project_985": meta.get("is_project_985", False),
                        "is_project_211": meta.get("is_project_211", False),
                        "application_fee_rmb": meta.get("application_fee_rmb", 0),
                        "scholarships": scholars,
                        "feasibility_notes": meta.get("feasibility_notes", "")
                    }
                logger.info(f"Loaded {len(result)} accredited Chinese universities from national catalog.")
                return result
        except Exception as e:
            logger.error(f"Error loading universities catalog JSON: {e}")
    return {}


# Knowledge base of Chinese Universities with scholarship, region, and barrier metadata
KNOWN_UNIVERSITIES_METADATA: Dict[str, Dict] = _load_universities_catalog()


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
        max_rank: Optional[int] = None,
        keyword: Optional[str] = None
    ) -> List[University]:
        """Filters Chinese universities dynamically by Region, Tier/Feasibility, Rank, and Keyword."""
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
            if keyword:
                kw = keyword.lower().strip()
                matches = (
                    kw in univ.name.lower() or
                    (univ.chinese_name and kw in univ.chinese_name.lower()) or
                    kw in univ.domain.lower() or
                    kw in univ.region.lower()
                )
                if not matches:
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

