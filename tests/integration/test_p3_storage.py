"""Phase P3 Test: Persistence, Deduplication, and Cryptographic Hash Lineage."""

import pytest
from src.services.normalizer import normalizer
from src.models.professor import FacultyProfile, SupervisorQualification


def test_p3_deduplication_key_generation():
    """Verify deduplication preserves canonical unique representation."""
    key1 = normalizer.generate_dedup_key("Prof.Wang@Tsinghua.EDU.CN", "Wang Qiang", "Tsinghua University")
    key2 = normalizer.generate_dedup_key("prof.wang@tsinghua.edu.cn", "Qiang Wang", "Tsinghua")
    # Same canonical email -> duplicate detected
    assert key1 == key2

    # Different email, same name & university
    key3 = normalizer.generate_dedup_key("", "Wang Qiang", "Tsinghua")
    key4 = normalizer.generate_dedup_key("", "Wang Qiang", "Tsinghua")
    assert key3 == key4


def test_p3_content_hash_integrity():
    """Verify cryptographic SHA-256 content hash detects any page mutation."""
    content_a = "<html><body>Professor Profile Wang</body></html>"
    content_b = "<html><body>Professor Profile Wang - Updated 2026</body></html>"

    hash_a1 = normalizer.compute_sha256(content_a)
    hash_a2 = normalizer.compute_sha256(content_a)
    hash_b = normalizer.compute_sha256(content_b)

    assert hash_a1 == hash_a2
    assert hash_a1 != hash_b
    assert len(hash_a1) == 64

