"""MongoDB Change Stream listener for event-driven asynchronous LLM drafting."""

import asyncio
from typing import Optional
from src.core.database import db_manager
from src.core.logger import setup_logger
from src.models.professor import FacultyProfile
from src.services.llm_agent import llm_agent

logger = setup_logger("ChangeStreamReactor")


class ChangeStreamReactor:
    """Listens for document insertions into professors collection and triggers LLM drafting."""

    def __init__(self):
        self.is_running: bool = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Starts background Change Stream listener task."""
        if self.is_running:
            return

        if not db_manager.is_connected or db_manager.db is None:
            logger.info("MongoDB not connected or offline; Change Stream reactor on standby.")
            return

        self.is_running = True
        self._task = asyncio.create_task(self._listen_loop())
        logger.info("MongoDB Change Stream reactor started.")

    async def _listen_loop(self) -> None:
        try:
            professors_col = db_manager.get_collection("professors")
            pipeline = [{"$match": {"operationType": "insert"}}]

            async with professors_col.watch(pipeline) as stream:
                async for change in stream:
                    if not self.is_running:
                        break
                    doc = change.get("fullDocument")
                    if doc:
                        await self.handle_new_professor(doc)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"Change Stream interrupted (MongoDB replica set required for streams): {e}")
            self.is_running = False

    async def handle_new_professor(self, doc: dict) -> None:
        """Processes newly inserted professor document through Gemini LLM drafting pipeline."""
        try:
            profile = FacultyProfile(**doc)
            logger.info(f"Event Reactor: Triggering LLM synthesis for newly inserted professor {profile.name}")

            # 1. Generate Factual Research Digest
            digest = await llm_agent.generate_research_digest(profile)

            # 2. Generate Contextualized Cold Outreach Draft (<200 words, GPA-compensated)
            draft = await llm_agent.generate_outreach_draft(profile, digest)

            # 3. Save draft to outreach_drafts collection (status: PENDING_REVIEW)
            if db_manager.db is not None:
                drafts_col = db_manager.get_collection("outreach_drafts")
                await drafts_col.insert_one(draft.model_dump())
                logger.info(f"Saved generated outreach draft '{draft.id}' with status PENDING_REVIEW.")
        except Exception as e:
            logger.error(f"Error handling new professor in Change Stream: {e}")

    async def stop(self) -> None:
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("MongoDB Change Stream reactor stopped.")


change_stream_reactor = ChangeStreamReactor()
