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
settings.DB_NAME = "autoadmit_test"

from src.core.database import db_manager
db_manager.db_name = "autoadmit_test"
if db_manager.client is not None:
    db_manager.db = db_manager.client["autoadmit_test"]


@pytest.fixture(scope="session", autouse=True)
def isolate_test_database():
    """Ensures test suite operates strictly in isolated test database and cleans up afterward."""
    settings.DB_NAME = "autoadmit_test"
    db_manager.db_name = "autoadmit_test"
    if db_manager.client is not None:
        db_manager.db = db_manager.client["autoadmit_test"]
    yield
    # Cleanup test database so zero mock/test data remains
    if db_manager.client is not None:
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(db_manager.client.drop_database("autoadmit_test"))
            else:
                loop.run_until_complete(db_manager.client.drop_database("autoadmit_test"))
        except Exception:
            pass


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

