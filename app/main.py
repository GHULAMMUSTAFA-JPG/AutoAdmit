"""FastAPI application factory for the clean Phase 1 & Phase 2 architecture."""

from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.api.routes_admin import router as admin_router
from app.api.routes_jobs import router as jobs_router
from app.db.mongo import MongoManager, mongo_manager
from app.db.repositories import Repository
from app.schemas.filters import AdminConfig
from app.services.diff_sync import DiffSyncService
from app.services.phase1_discovery import Phase1DiscoveryService
from app.services.phase2_extractor import Phase2ExtractorService
from app.services.phase2_scraper import Phase2ScraperService
from app.services.runner import PipelineRunner


def create_app(manager: MongoManager | None = None, admin_config: AdminConfig | None = None) -> FastAPI:
    mgr = manager or mongo_manager
    cfg = admin_config or AdminConfig()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        db = await mgr.connect()
        repo = Repository(db)
        phase1 = Phase1DiscoveryService(repo, admin=cfg)
        scraper = Phase2ScraperService(repo, admin=cfg)
        extractor = Phase2ExtractorService(repo, admin=cfg)
        diff_sync = DiffSyncService(repo, scraper, extractor)
        runner = PipelineRunner(repo, phase1, scraper, extractor)

        application.state.repo = repo
        application.state.admin_config = cfg
        application.state.phase1 = phase1
        application.state.scraper = scraper
        application.state.extractor = extractor
        application.state.diff_sync = diff_sync
        application.state.runner = runner
        yield
        await mgr.close()

    application = FastAPI(title="AutoAdmit P12 Pipeline API", version="2.0.0", lifespan=lifespan)
    application.include_router(jobs_router)
    application.include_router(admin_router)
    return application


app = create_app()
