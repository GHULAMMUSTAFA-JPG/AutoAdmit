"""Logging infrastructure with rotating file handlers and WebSocket real-time log streaming."""

import asyncio
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Set, Optional
from fastapi import WebSocket
from src.config import settings

# Global set of active WebSocket clients for live log streaming
active_log_websockets: Set[WebSocket] = set()


class WebSocketLogHandler(logging.Handler):
    """Custom logging handler that broadcasts formatted log records to active WebSocket clients."""
    _main_loop: Optional[asyncio.AbstractEventLoop] = None

    @classmethod
    def set_loop(cls, loop: asyncio.AbstractEventLoop) -> None:
        cls._main_loop = loop

    def emit(self, record: logging.LogRecord) -> None:
        if not active_log_websockets:
            return

        try:
            if self.formatter and hasattr(self.formatter, "formatTime"):
                try:
                    timestamp = self.formatter.formatTime(record)
                except Exception:
                    timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
            else:
                timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")

            log_entry = {
                "timestamp": timestamp,
                "level": record.levelname,
                "module": record.name,
                "message": record.getMessage()
            }
            # Schedule broadcast in the running asyncio loop or thread-safe fallback
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    loop.create_task(self.broadcast(log_entry))
            except RuntimeError:
                if self._main_loop and self._main_loop.is_running():
                    asyncio.run_coroutine_threadsafe(self.broadcast(log_entry), self._main_loop)
        except Exception:
            self.handleError(record)

    async def broadcast(self, log_entry: dict) -> None:
        if not active_log_websockets:
            return
        disconnected = set()
        for ws in list(active_log_websockets):
            try:
                await ws.send_json(log_entry)
            except Exception:
                disconnected.add(ws)
        if disconnected:
            active_log_websockets.difference_update(disconnected)


def setup_logger(module_name: str) -> logging.Logger:
    """Configures and returns a logger instance with rotating disk storage and WebSocket streaming."""
    logger = logging.getLogger(module_name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        Path(settings.LOG_DIR).mkdir(parents=True, exist_ok=True)
        log_file = Path(settings.LOG_DIR) / "autoadmit.log"

        # 1. Rotating File Handler (10MB max, 5 backup files)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )
        file_formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] [%(process)d]: %(message)s"
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        # 2. Console Handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(file_formatter)
        logger.addHandler(console_handler)

        # 3. WebSocket Handler
        ws_handler = WebSocketLogHandler()
        ws_handler.setFormatter(file_formatter)
        logger.addHandler(ws_handler)

    return logger

