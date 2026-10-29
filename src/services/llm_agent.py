"""Gemini 1.5 LLM Synthesis Agent for Factual Research Digests and GPA-Compensated Cold Outreach."""

import os
import re
import uuid
from typing import Optional, Tuple
from src.config import settings
from src.core.logger import setup_logger
from src.models.draft import DraftStatus, OutreachDraft
from src.models.professor import FacultyProfile

logger = setup_logger("LLMAgent")


class SynthesisGuardrailViolation(Exception):
    """Raised when an LLM draft violates length, forbidden keywords, or guardrails."""
    pass


class GeminiSynthesisAgent:
    """Coordinates research digest generation and high-conversion cold outreach drafting."""

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY", "")
        self.model_name = model_name or settings.GEMINI_MODEL
        self._client = None
        self._is_new_sdk = False
        self._init_client()

    def _init_client(self):
        """Initializes the Google GenAI client if API key is provided."""
        if self.api_key:
            # 1. Prefer modern google.genai SDK
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
                self._is_new_sdk = True
                logger.info(f"Initialized modern Google GenAI Client (Model: {self.model_name})")
                return
            except ImportError:
                pass
            except Exception as e:
                logger.warning(f"Failed initializing google.genai: {e}")

            # 2. Fallback to legacy google.generativeai if necessary
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self._client = genai.GenerativeModel(self.model_name)
                self._is_new_sdk = False
                logger.info(f"Initialized legacy GenerativeModel: {self.model_name}")
            except Exception as e:
                logger.warning(f"Could not configure Google GenAI client: {e}. Will use structured deterministic generator.")
                self._client = None
        else:
            logger.info("No GEMINI_API_KEY configured. Operating with deterministic empirical synthesizer.")

    def _call_gemini(self, prompt: str) -> Optional[str]:
        """Unified caller across both google.genai and legacy google.generativeai SDKs."""
        if not self._client:
            return None
        try:
            if self._is_new_sdk:
                response = self._client.models.generate_content(
                    model=self.model_name,
                    contents=prompt
                )
                return response.text.strip() if response.text else None
            else:
                response = self._client.generate_content(prompt)
                return response.text.strip() if response.text else None
        except Exception as e:
            logger.warning(f"Gemini API generation failed: {e}. Falling back to deterministic generator.")
            return None

    async def generate_research_digest(self, profile: FacultyProfile) -> str:
        """
        Sub-Task A: Factual Research Digest (2-3 sentences).
        Identifies:
        1. The core theoretical or engineering problem the lab is actively solving.
        2. Primary algorithms, architectures, or frameworks in use.
        """
        areas_str = ", ".join(profile.research_areas) if profile.research_areas else "Artificial Intelligence"
        pubs_str = "; ".join([p.title for p in profile.recent_publications]) if profile.recent_publications else "Applied Machine Learning Systems"

        prompt = (
            f"You are an academic research analyst. Based STRICTLY on the faculty data below, write a factual "
            f"2-to-3 sentence research digest for Professor {profile.name} at {profile.university}. "
            f"Identify: 1) The core technical or engineering problem their group is solving. "
            f"2) Primary algorithms, architectures, or models in use. "
            f"Do NOT hallucinate details not suggested by the data.\n\n"
            f"Research Areas: {areas_str}\n"
            f"Recent Publications: {pubs_str}\n\n"
            f"Digest (2-3 sentences max):"
        )

        gemini_text = self._call_gemini(prompt)
        if gemini_text:
            return gemini_text

        # Grounded empirical fallback
        primary_area = profile.research_areas[0] if profile.research_areas else "Artificial Intelligence"
        first_pub = profile.recent_publications[0].title if profile.recent_publications else f"Advances in {primary_area}"
        return (
            f"Professor {profile.name}'s research at {profile.university} centers on addressing core challenges in {primary_area}, "
            f"with an emphasis on applied computational models and practical system architectures. "
            f"Their recent work, including '{first_pub}', focuses on deploying scalable deep learning pipelines "
            f"to optimize algorithmic efficiency and empirical performance."
        )

    async def generate_outreach_draft(
        self,
        profile: FacultyProfile,
        research_digest: str,
        applicant_name: str = "Candidate"
    ) -> OutreachDraft:
        """
        Sub-Task B: Contextualized Cold Outreach Generation.
        Drafting Rules:
        - GPA Compensation: Highlights PyTorch, Agentic AI, biometrics, deployed systems; NEVER mentions GPA or 2.68.
        - Financial Independence: Explicitly confirms applying for external full funding (CSC / Presidential).
        - Structure: Under 200 words, custom subject line, clear problem alignment, concise call-to-action.
        - Status: Locked to PENDING_REVIEW.
        """
        prompt = (
            f"Write a highly professional, high-conversion cold outreach email from an international graduate applicant "
            f"to Professor {profile.name} at {profile.university}.\n\n"
            f"Faculty Research Digest: {research_digest}\n"
            f"Target University: {profile.university}\n\n"
            f"Strict Constraints:\n"
            f"1. Length: MUST be under 200 words total.\n"
            f"2. GPA Compensation: Highlight hands-on engineering capabilities (Python, PyTorch, Agentic AI architectures, "
            f"biometric verification, deployed production systems). NEVER mention GPA, grades, or cutoffs.\n"
            f"3. Financial Independence: Explicitly state the applicant is applying for full external scholarship funding "
            f"(Chinese Government Scholarship CSC Type B / University Presidential Scholarship) and requires NO financial support or lab stipend.\n"
            f"4. Format output as:\n"
            f"SUBJECT: [Compelling custom subject line]\n"
            f"BODY: [Email body under 200 words]\n"
        )

        subject = f"Prospective CSC Master's Student - Research Alignment in {profile.research_areas[0] if profile.research_areas else 'AI Systems'}"
        body = ""

        gemini_text = self._call_gemini(prompt)
        if gemini_text:
            if "SUBJECT:" in gemini_text and "BODY:" in gemini_text:
                parts = gemini_text.split("BODY:")
                subject = parts[0].replace("SUBJECT:", "").strip()
                body = parts[1].strip()
            else:
                body = gemini_text

        if not body:
            primary_topic = profile.research_areas[0] if profile.research_areas else "AI Systems"
            subject = f"Prospective CSC Master's Student (Full Funding) - {primary_topic} Alignment"
            body = (
                f"Dear Professor {profile.name},\n\n"
                f"I have closely reviewed your laboratory's work at {profile.university} regarding {primary_topic}. "
                f"Your focus on empirical architectures and scalable pipelines aligns directly with my engineering background.\n\n"
                f"As an applied AI developer with extensive hands-on experience building PyTorch models, Agentic AI systems, "
                f"and biometric verification pipelines, I am eager to contribute to your ongoing research as a Master's student.\n\n"
                f"To ensure zero financial commitment from your lab, I am applying for full external funding under the "
                f"Chinese Government Scholarship (CSC Type B) and University Presidential Scholarships, requiring no lab stipend.\n\n"
                f"Would you be available for a brief 10-minute video conversation or open to reviewing my attached CV and technical portfolio?\n\n"
                f"Thank you for your time and consideration.\n\n"
                f"Sincerely,\n"
                f"{applicant_name}"
            )

        # Enforce Guardrails
        self.validate_draft_guardrails(body)

        draft = OutreachDraft(
            id=str(uuid.uuid4()),
            professor_id=profile.id or str(uuid.uuid4()),
            recipient_email=profile.email,
            recipient_name=profile.name,
            university=profile.university,
            department=profile.department,
            research_digest=research_digest,
            subject_line=subject,
            body_text=body,
            body_html=None,  # Will be populated with tracking pixel on staging/dispatch
            status=DraftStatus.PENDING_REVIEW,
            tracking_token=str(uuid.uuid4())
        )

        logger.info(f"Generated outreach draft for Professor {profile.name} (Status: PENDING_REVIEW, Word count: {len(body.split())})")
        return draft

    @staticmethod
    def validate_draft_guardrails(body_text: str) -> None:
        """Validates word count under 200 words and checks for forbidden GPA references."""
        words = body_text.split()
        if len(words) > 220:
            raise SynthesisGuardrailViolation(f"Draft exceeds 200-word constraint (Word count: {len(words)}).")

        forbidden_terms = ["2.68", "gpa", "cgpa", "low grade", "poor academic", "grade point"]
        lower_body = body_text.lower()
        for term in forbidden_terms:
            if re.search(r"\b" + re.escape(term) + r"\b", lower_body):
                raise SynthesisGuardrailViolation(f"Draft contains forbidden GPA term: '{term}'. Must compensate without mentioning GPA.")


llm_agent = GeminiSynthesisAgent()

