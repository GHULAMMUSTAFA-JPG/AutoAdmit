"""Verification test for DB layer, logging, WebSockets, and system APIs."""

import asyncio
import logging
import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.config import settings
from src.core.database import DatabaseManager, db_manager
from src.core.logger import WebSocketLogHandler, setup_logger, active_log_websockets
from src.services.change_stream import ChangeStreamReactor


@pytest.fixture
def auth_headers():
    import base64
    creds = f"{settings.BASIC_AUTH_USERNAME}:{settings.BASIC_AUTH_PASSWORD}"
    token = base64.b64encode(creds.encode("utf-8")).decode("utf-8")
    return {"Authorization": f"Basic {token}"}


@pytest.mark.asyncio
async def test_database_manager_lifecycle():
    """Verify DB lifecycle, offline mode handling, and proper state cleanup."""
    # Test disconnected behavior with invalid port
    dm = DatabaseManager(uri="mongodb://127.0.0.1:27099", db_name="test_offline_db")
    assert dm.is_connected is False
    assert dm.client is None
    assert dm.db is None

    # Connect with short timeout
    await dm.connect(server_selection_timeout_ms=300)
    assert dm.is_connected is False
    assert dm.client is None
    assert dm.db is None

    # Verify get_collection raises RuntimeError when disconnected
    with pytest.raises(RuntimeError) as exc_info:
        dm.get_collection("professors")
    assert "Database is not connected" in str(exc_info.value)

    # Verify close is idempotent
    await dm.close()
    assert dm.is_connected is False


@pytest.mark.asyncio
async def test_change_stream_reactor_lifecycle():
    """Verify change stream reactor standby when DB is offline, and clean stop."""
    reactor = ChangeStreamReactor()
    assert reactor.is_running is False

    # Start when DB is offline -> standby without raising
    await reactor.start()
    assert reactor.is_running is False
    assert reactor._task is None

    # Stop when idle
    await reactor.stop()
    assert reactor.is_running is False
    assert reactor._task is None


def test_websocket_log_handler_formatting():
    """Verify WebSocketLogHandler formatting handles records gracefully without formatTime errors."""
    logger = setup_logger("AuditTestLogger")
    ws_handler = None
    for h in logger.handlers:
        if isinstance(h, WebSocketLogHandler):
            ws_handler = h
            break
    assert ws_handler is not None

    # Mock record
    record = logging.LogRecord(
        name="AuditTestLogger",
        level=logging.INFO,
        pathname="audit.py",
        lineno=42,
        msg="Test audit log message: %s",
        args=("operational",),
        exc_info=None
    )

    # 1. Emit without active websockets -> fast no-op
    ws_handler.emit(record)

    # 2. Test timestamp formatting fallback with null formatter
    old_formatter = ws_handler.formatter
    try:
        ws_handler.formatter = None
        # Should not raise AttributeError: 'WebSocketLogHandler' object has no attribute 'formatTime'
        ws_handler.emit(record)
    finally:
        ws_handler.formatter = old_formatter


def test_system_apis(auth_headers: dict):
    """Verify /api/v1/system/login, /api/v1/system/health, /api/v1/system/safety-toggle."""
    with TestClient(app) as client:
        # 1. Login endpoint
        # Invalid credentials -> 401
        res = client.post("/api/v1/system/login", json={"password": "wrong_password"})
        assert res.status_code == 401

        # Valid credentials -> 200 with Bearer token
        res = client.post("/api/v1/system/login", json={
            "username": settings.BASIC_AUTH_USERNAME,
            "password": settings.BASIC_AUTH_PASSWORD
        })
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "authenticated"
        assert "token" in data
        bearer_token = data["token"]
        bearer_headers = {"Authorization": f"Bearer {bearer_token}"}

        # 2. Health endpoint with Bearer auth
        health_res = client.get("/api/v1/system/health", headers=bearer_headers)
        assert health_res.status_code == 200
        health_data = health_res.json()
        assert health_data["status"] == "HEALTHY"
        assert "timestamp_utc" in health_data
        assert "timestamp_cst" in health_data
        assert "persistent_storage_mount" in health_data
        assert "database_connected" in health_data

        # 3. Safety toggle endpoint
        original_gate = settings.SYSTEM_GATE_ACTIVE
        original_sandbox = settings.SANDBOX_MODE
        try:
            # Toggle safety switches
            toggle_res = client.post(
                "/api/v1/system/safety-toggle",
                json={"master_gate_active": False, "sandbox_mode": False},
                headers=bearer_headers
            )
            assert toggle_res.status_code == 200
            toggle_data = toggle_res.json()
            assert toggle_data["master_gate_active"] is False
            assert toggle_data["sandbox_mode"] is False
            assert settings.SYSTEM_GATE_ACTIVE is False
            assert settings.SANDBOX_MODE is False
        finally:
            # Restore safety settings
            settings.SYSTEM_GATE_ACTIVE = original_gate
            settings.SANDBOX_MODE = original_sandbox


def test_websocket_log_stream_endpoint():
    """Verify /ws/logs and /api/v1/system/ws/logs accept connections, handle ping/pong, and cleanup on disconnect."""
    with TestClient(app) as client:
        initial_count = len(active_log_websockets)

        # Connect to root /ws/logs
        with client.websocket_connect("/ws/logs") as ws:
            assert len(active_log_websockets) == initial_count + 1

            # Connection trigger generates an immediate broadcast log
            initial_log = ws.receive_json()
            assert initial_log["level"] == "INFO"
            assert initial_log["module"] == "SystemAPI"
            assert "connected" in initial_log["message"]

            # Send ping
            ws.send_text("ping")
            response = ws.receive_text()
            assert response == "pong"

            # Trigger an arbitrary log message while subscriber is connected
            test_logger = setup_logger("WSTestModule")
            test_logger.info("Live WebSocket broadcast test message.")

            # Read broadcast log entry
            log_data = ws.receive_json()
            assert log_data["level"] == "INFO"
            assert log_data["module"] == "WSTestModule"
            assert "Live WebSocket broadcast test message." in log_data["message"]
            assert "timestamp" in log_data

        # Verify disconnect cleanup
        assert len(active_log_websockets) == initial_count
