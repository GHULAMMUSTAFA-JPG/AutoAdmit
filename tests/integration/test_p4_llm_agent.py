"""Phase P4 Test: Gemini LLM Synthesis, Guardrails, and GPA Compensation Directives."""

import pytest
from src.services.llm_agent import GeminiSynthesisAgent, SynthesisGuardrailViolation
from src.models.professor import FacultyProfile, FacultyPublication, SupervisorQualification
from src.models.draft import DraftStatus


@pytest.mark.asyncio
async def test_p4_research_digest_and_gpa_compensation():
    """Verify drafts are <200 words, highlight AI engineering, omit GPA, and set PENDING_REVIEW."""
    agent = GeminiSynthesisAgent()

    profile = FacultyProfile(
        id="prof-p4-test",
        name="Zhang Wei",
        native_name="张伟",
        email="zhangwei@buaa.edu.cn",
        university="Beihang University",
        department="School of Computer Science",
        qualification=SupervisorQualification.PHD_SUPERVISOR_SHORT,
        research_areas=["Computer Vision", "Biometric Verification", "Deep Learning"],
        recent_publications=[
            FacultyPublication(title="Multi-Modal Face and Iris Verification with Vision Transformers", year=2024),
            FacultyPublication(title="Lightweight Convolutional Backbones for Edge Perception", year=2023)
        ],
        source_url="https://cs.buaa.edu.cn/faculty/zhangwei",
        content_hash="mock_hash_64_characters_long_sha256_placeholder_lineage_audit1234",
        worker_id="p4-worker"
    )

    # 1. Sub-Task A: Factual Research Digest (2-3 sentences)
    digest = await agent.generate_research_digest(profile)
    assert len(digest) > 50
    assert "Zhang Wei" in digest or "Beihang" in digest
    # Sentence count check (2 to 4 sentences)
    sentences = [s for s in digest.split(".") if len(s.strip()) > 5]
    assert 1 <= len(sentences) <= 4

    # 2. Sub-Task B: Contextualized Cold Outreach Generation
    draft = await agent.generate_outreach_draft(profile, digest, applicant_name="Alex Mercer")

    # Guardrail Check 1: Status locked to PENDING_REVIEW
    assert draft.status == DraftStatus.PENDING_REVIEW

    # Guardrail Check 2: Word count under 200 words
    word_count = len(draft.body_text.split())
    assert word_count <= 210, f"Word count ({word_count}) exceeded 200 words limit."

    # Guardrail Check 3: Zero mentions of 2.68 CGPA or GPA
    forbidden_terms = ["2.68", "gpa", "cgpa", "low grade", "poor academic"]
    for term in forbidden_terms:
        assert term not in draft.body_text.lower(), f"Forbidden term '{term}' found in draft body."

    # Guardrail Check 4: Must confirm independent scholarship funding (CSC / Presidential)
    lower_body = draft.body_text.lower()
    assert "csc" in lower_body or "scholarship" in lower_body
    assert "stipend" in lower_body or "funding" in lower_body or "financial" in lower_body

    # Guardrail Check 5: Highlight engineering strengths
    assert any(skill in lower_body for skill in ["pytorch", "engineering", "ai", "system", "biometric"])


def test_p4_guardrail_validator_rejection():
    """Verify guardrail exception triggers when draft contains forbidden GPA words or exceeds word count."""
    agent = GeminiSynthesisAgent()

    # Should raise for forbidden GPA reference
    with pytest.raises(SynthesisGuardrailViolation):
        agent.validate_draft_guardrails("Dear Professor, my CGPA was 2.68 but I have good coding skills.")

    # Should raise for excessive word count (>220 words)
    long_text = "word " * 250
    with pytest.raises(SynthesisGuardrailViolation):
        agent.validate_draft_guardrails(long_text)
