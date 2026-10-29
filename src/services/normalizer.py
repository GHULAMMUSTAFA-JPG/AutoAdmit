"""Data normalizer, email de-obfuscator, and cryptographic SHA-256 audit hasher."""

import hashlib
import re
from typing import Optional


class DataNormalizer:
    """Normalizes scraped data, de-obfuscates contact details, and computes audit hashes."""

    @staticmethod
    def deobfuscate_email(raw_email: str) -> Optional[str]:
        """
        Cleans anti-spam and obfuscated emails (e.g. 'prof [at] univ (dot) edu (dot) cn').
        Returns canonical email string or None if unparseable.
        """
        if not raw_email or not isinstance(raw_email, str):
            return None

        clean = raw_email.strip()

        # Replace common 'at' symbols and HTML entities
        at_patterns = [
            r"\[at\]", r"\(at\)", r"\{at\}", r"\s+at\s+", r"_at_", r"&#64;", r"&commat;", r"＠"
        ]
        for pattern in at_patterns:
            clean = re.sub(pattern, "@", clean, flags=re.IGNORECASE)

        # Replace common 'dot' symbols and HTML entities
        dot_patterns = [
            r"\[dot\]", r"\(dot\)", r"\{dot\}", r"\s+dot\s+", r"_dot_", r"&#46;", r"。"
        ]
        for pattern in dot_patterns:
            clean = re.sub(pattern, ".", clean, flags=re.IGNORECASE)

        # Remove inner whitespace
        clean = re.sub(r"\s+", "", clean)

        # Extract standard email pattern
        email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", clean)
        if email_match:
            return email_match.group(0).lower().rstrip(".")
        return None

    @staticmethod
    def compute_sha256(content: str) -> str:
        """Computes cryptographic SHA-256 hash of raw page content for Level 1 audit lineage."""
        if not content:
            return hashlib.sha256(b"").hexdigest()
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def standardize_department(department_name: str) -> str:
        """Standardizes diverse departmental naming variations into uniform tags."""
        dept = department_name.lower()
        if any(term in dept for term in ["computer", "ai", "artificial intelligence", "software", "cs", "计算", "人工智能", "软件"]):
            return "CS_AI_SE"
        return department_name.strip()

    @staticmethod
    def generate_dedup_key(email: str, name: str, university: str) -> str:
        """Generates canonical deduplication key."""
        clean_email = email.lower().strip() if email else ""
        if clean_email:
            return f"email:{clean_email}"
        return f"name_univ:{name.lower().strip()}_{university.lower().strip()}"


normalizer = DataNormalizer()

