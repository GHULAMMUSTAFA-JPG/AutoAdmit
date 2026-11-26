"""Prompt Studio endpoints: view, edit, version, and restore Qwen prompts stored in MongoDB `prompt_versions`."""

from typing import Literal
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.prompt_defaults import DEFAULT_PROMPTS
from app.db.repositories import Repository

router = APIRouter(prefix="/api/v1/prompts", tags=["Prompts"])

PromptKey = Literal["phase2_extractor", "phase2_inline_table", "tree_branch_select", "roster_agent_verify"]


class SavePromptRequest(BaseModel):
    system_prompt: str = Field(default="")
    user_prompt_template: str = Field(..., min_length=10)
    note: str = Field(default="")


async def _ensure_seeded(repo: Repository) -> None:
    """Auto-seeds v1 default prompt versions into MongoDB `prompt_versions` if missing."""
    for key, meta in DEFAULT_PROMPTS.items():
        existing = await repo.list_prompt_versions(prompt_key=key, limit=1)
        if not existing:
            await repo.save_prompt_version(
                prompt_key=key,
                system_prompt=meta["system_prompt"],
                user_prompt_template=meta["user_prompt_template"],
                note="Initial built-in default (v1)",
            )


@router.get("")
async def list_prompts(request: Request):
    """Returns all Qwen prompt keys with active prompt + full previous/new version history."""
    repo: Repository = request.app.state.repo
    await _ensure_seeded(repo)
    all_versions = await repo.list_prompt_versions(limit=200)
    by_key: dict[str, list[dict]] = {k: [] for k in DEFAULT_PROMPTS}
    for v in all_versions:
        if v.prompt_key in by_key:
            by_key[v.prompt_key].append(v.model_dump(mode="json"))

    items = []
    for key, meta in DEFAULT_PROMPTS.items():
        vers = by_key.get(key) or []
        active = next((v for v in vers if v.get("is_active")), vers[0] if vers else None)
        items.append({
            "prompt_key": key,
            "label": meta["label"],
            "placeholders": meta["placeholders"],
            "active": active,
            "versions": vers,
        })
    return {"prompts": items}


@router.post("/{prompt_key}")
async def save_prompt_version_endpoint(prompt_key: PromptKey, body: SavePromptRequest, request: Request):
    """Saves a newly edited/pasted prompt as the next active version while preserving all previous versions in DB."""
    repo: Repository = request.app.state.repo
    await _ensure_seeded(repo)
    saved = await repo.save_prompt_version(
        prompt_key=prompt_key,
        system_prompt=body.system_prompt,
        user_prompt_template=body.user_prompt_template,
        note=body.note.strip() or "Edited via Prompt Studio UI",
    )
    versions = await repo.list_prompt_versions(prompt_key=prompt_key, limit=50)
    return {
        "saved": saved.model_dump(mode="json"),
        "versions": [v.model_dump(mode="json") for v in versions],
    }


@router.post("/{prompt_key}/activate/{version_id}")
async def activate_prompt_version_endpoint(prompt_key: PromptKey, version_id: str, request: Request):
    """Restores/activates any previous saved prompt version."""
    repo: Repository = request.app.state.repo
    activated = await repo.activate_prompt_version(prompt_key, version_id)
    if not activated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Prompt version '{version_id}' not found.")
    versions = await repo.list_prompt_versions(prompt_key=prompt_key, limit=50)
    return {
        "activated": activated.model_dump(mode="json"),
        "versions": [v.model_dump(mode="json") for v in versions],
    }
