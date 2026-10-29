"""Test suite configuration, fixtures, and FastAPI TestClient."""

import os
import pytest
from fastapi.testclient import TestClient
from src.config import settings
from src.main import app

# Set test environment flags
settings.SYSTEM_GATE_ACTIVE = True
settings.SANDBOX_MODE = True
settings.TEST_RECIPIENT_EMAIL = "applicant.test@example.com"
settings.BASIC_AUTH_USERNAME = "admin"
settings.BASIC_AUTH_PASSWORD = "autoadmit_secure_pass_2026"


@pytest.fixture
def client():
    """Provides authenticated TestClient for API integration tests."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers():
    """Basic auth headers for testing."""
    import base64
    creds = f"{settings.BASIC_AUTH_USERNAME}:{settings.BASIC_AUTH_PASSWORD}"
    token = base64.b64encode(creds.encode("utf-8")).decode("utf-8")
    return {"Authorization": f"Basic {token}"}

