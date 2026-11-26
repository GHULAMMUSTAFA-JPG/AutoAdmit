"""FastAPI application factory for the clean Phase 1 & Phase 2 architecture with ported UI in app/static/."""

from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes_admin import router as admin_router
from app.api.routes_analytics import router as analytics_router
from app.api.routes_jobs import router as jobs_router
from app.api.routes_prompts import router as prompts_router
from app.api.routes_trees import router as trees_router
from app.core.llm_router import llm_router
from app.db.mongo import MongoManager, mongo_manager
from app.db.repositories import Repository
from app.schemas.filters import AdminConfig
from app.services.diff_sync import DiffSyncService
from app.services.phase1_discovery import Phase1DiscoveryService
from app.services.phase2_extractor import Phase2ExtractorService
from app.services.phase2_scraper import Phase2ScraperService
from app.services.runner import PipelineRunner
from app.services.site_tree_builder import SiteTreeBuilder

STATIC_DIR = Path(__file__).parent / "static"


def create_app(manager: MongoManager | None = None, admin_config: AdminConfig | None = None) -> FastAPI:
    mgr = manager or mongo_manager
    cfg = admin_config or AdminConfig()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        db = await mgr.connect()
        repo = Repository(db)
        llm_router.set_trace_repo(repo)
        # Restore last auto-synced Colab URL from MongoDB system_state if present
        persisted_colab = await repo.get_system_state("colab_base_url")
        if persisted_colab and isinstance(persisted_colab, str) and persisted_colab.startswith(("http://", "https://")):
            from app.services.colab_client import colab_client
            clean_u = persisted_colab.rstrip("/")
            llm_router.colab.base_url = f"{clean_u}/v1"
            colab_client.base_url = clean_u
            from app.core.config import settings
            settings.COLAB_BASE_URL = clean_u
        phase1 = Phase1DiscoveryService(repo, admin=cfg)
        scraper = Phase2ScraperService(repo, admin=cfg)
        extractor = Phase2ExtractorService(repo, admin=cfg)
        diff_sync = DiffSyncService(repo, scraper, extractor)
        runner = PipelineRunner(repo, phase1, scraper, extractor, admin=cfg)
        tree_builder = SiteTreeBuilder(repo, admin=cfg)

        application.state.repo = repo
        application.state.admin_config = cfg
        application.state.phase1 = phase1
        application.state.scraper = scraper
        application.state.extractor = extractor
        application.state.diff_sync = diff_sync
        application.state.runner = runner
        application.state.tree_builder = tree_builder
        yield
        await mgr.close()

    application = FastAPI(title="AutoAdmit P12 Pipeline API", version="2.0.0", lifespan=lifespan)
    application.include_router(jobs_router)
    application.include_router(admin_router)
    application.include_router(trees_router)
    application.include_router(analytics_router)
    application.include_router(prompts_router)

    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    application.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @application.get("/", include_in_schema=False)
    async def serve_dashboard():
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"message": "AutoAdmit P12 API running. Visit /docs."}

    return application


app = create_app()
