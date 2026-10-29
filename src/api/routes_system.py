"""System health, safety gate toggles, and real-time WebSocket log streaming."""

import secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel

from src.api.deps import get_current_user
from src.config import settings
from src.core.database import db_manager
from src.core.logger import active_log_websockets, setup_logger

router = APIRouter(prefix="/api/v1/system", tags=["System"])
logger = setup_logger("SystemAPI")


class LoginRequest(BaseModel):
    password: str
    username: Optional[str] = None


@router.post("/login")
def login(request: LoginRequest):
    """Password-based authentication endpoint for the web dashboard."""
    username = request.username or settings.BASIC_AUTH_USERNAME
    correct_user = secrets.compare_digest(username, settings.BASIC_AUTH_USERNAME)
    correct_pass = secrets.compare_digest(request.password, settings.BASIC_AUTH_PASSWORD)

    if correct_user and correct_pass:
        return {
            "status": "authenticated",
            "username": username,
            "token": settings.JWT_SECRET_KEY,
            "message": "Access granted."
        }
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid password. Access denied."
    )


class SafetyToggleRequest(BaseModel):
    master_gate_active: Optional[bool] = None
    sandbox_mode: Optional[bool] = None


@router.get("/health")
def get_system_health(user: str = Depends(get_current_user)):
    """Returns system status, persistent disk mounts, and CST operational status."""
    utc_now = datetime.now(timezone.utc)
    cst_now = utc_now + timedelta(hours=8)

    db_path_exists = Path(settings.DB_STORAGE_PATH).exists()
    log_path_exists = Path(settings.LOG_DIR).exists()

    return {
        "status": "HEALTHY",
        "timestamp_utc": utc_now.isoformat(),
        "timestamp_cst": cst_now.strftime("%Y-%m-%d %H:%M:%S CST"),
        "master_gate_active": settings.SYSTEM_GATE_ACTIVE,
        "sandbox_mode": settings.SANDBOX_MODE,
        "test_recipient_email": settings.TEST_RECIPIENT_EMAIL,
        "database_connected": db_manager.is_connected,
        "persistent_storage_mount": {
            "db_path": settings.DB_STORAGE_PATH,
            "db_path_valid": db_path_exists,
            "log_path": settings.LOG_DIR,
            "log_path_valid": log_path_exists
        }
    }


@router.post("/safety-toggle")
def toggle_safety_controls(request: SafetyToggleRequest, user: str = Depends(get_current_user)):
    """Dynamically updates the Master Kill-Switch or Sandbox Mode toggles."""
    if request.master_gate_active is not None:
        settings.SYSTEM_GATE_ACTIVE = request.master_gate_active
        logger.warning(f"SAFETY TOGGLE CHANGED: SYSTEM_GATE_ACTIVE = {settings.SYSTEM_GATE_ACTIVE}")

    if request.sandbox_mode is not None:
        settings.SANDBOX_MODE = request.sandbox_mode
        logger.warning(f"SAFETY TOGGLE CHANGED: SANDBOX_MODE = {settings.SANDBOX_MODE}")

    return {
        "master_gate_active": settings.SYSTEM_GATE_ACTIVE,
        "sandbox_mode": settings.SANDBOX_MODE
    }


@router.websocket("/ws/logs")
async def websocket_log_stream(websocket: WebSocket):
    """
    Real-time WebSocket terminal displaying log feeds filtered by module
    (Scraper, Normalizer, LLMAgent, SMTPEngine, IMAPHarvester).
    """
    await websocket.accept()
    active_log_websockets.add(websocket)
    logger.info("New WebSocket log subscriber connected.")

    try:
        while True:
            # Keep connection alive and accept filter messages
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        active_log_websockets.discard(websocket)
        logger.info("WebSocket log subscriber disconnected.")
    except Exception:
        active_log_websockets.discard(websocket)

