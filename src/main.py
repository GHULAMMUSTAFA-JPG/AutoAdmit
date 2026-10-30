"""FastAPI Application entrypoint for AutoAdmit Engine."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.routes_discovery import router as discovery_router
from src.api.routes_professors import router as professors_router
from src.api.routes_drafts import router as drafts_router
from src.api.routes_dispatch import router as dispatch_router
from src.api.routes_tracking import router as tracking_router
from src.api.routes_prompts import router as prompts_router
from src.api.routes_system import router as system_router, websocket_log_stream
from src.config import settings
from src.core.database import db_manager
from src.core.logger import setup_logger, WebSocketLogHandler
from src.services.change_stream import change_stream_reactor

logger = setup_logger("AutoAdmitGateway")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle event handler for database initialization and change stream reactor."""
    logger.info("Initializing AutoAdmit Engine subsystems...")
    WebSocketLogHandler.set_loop(asyncio.get_running_loop())
    settings.ensure_storage_paths()

    # Attempt MongoDB connection
    await db_manager.connect(server_selection_timeout_ms=1500)

    # Start Change Stream reactor in background if DB is live
    if db_manager.is_connected:
        await change_stream_reactor.start()

    yield

    # Teardown
    logger.info("Shutting down AutoAdmit Engine...")
    await change_stream_reactor.stop()
    await db_manager.close()


app = FastAPI(
    title="AutoAdmit Engine",
    description="Intelligent Multi-Tier Academic Discovery, Feasibility Analysis, & High-Conversion Outreach Platform",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware for secure edge reverse proxies
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(discovery_router)
app.include_router(professors_router)
app.include_router(drafts_router)
app.include_router(dispatch_router)
app.include_router(tracking_router)
app.include_router(prompts_router)
app.include_router(system_router)


@app.websocket("/ws/logs")
async def root_websocket_endpoint(websocket: WebSocket):
    """Direct root WebSocket log streaming endpoint for live UI streaming."""
    await websocket_log_stream(websocket)

# Mount static asset directory
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", include_in_schema=False)
async def serve_dashboard():
    """Serves the Single-Page Application (SPA) dashboard."""
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "AutoAdmit Engine API running. Dashboard UI files initializing."}

