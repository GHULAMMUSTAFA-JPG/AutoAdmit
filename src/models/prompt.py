"""Prompt Management Model for Dynamic UI Configuration and MongoDB Persistence."""

from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field


class PromptRecord(BaseModel):
    id: str = Field(..., description="Unique prompt identifier (slug)")
    title: str = Field(..., description="Human-readable title")
    stage: str = Field("outreach_synthesis", description="Target engine stage (e.g., outreach_synthesis, faculty_extraction, research_digest)")
    system_prompt: str = Field(..., description="System instructions and persona")
    template_text: str = Field(..., description="User prompt template with interpolation variables")
    variables: List[str] = Field(default_factory=list, description="Available interpolation variables, e.g. ['professor_name', 'university']")
    is_active: bool = Field(default=True, description="Whether this prompt is the currently active version for its stage")
    version: int = Field(default=1, description="Version number")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PromptUpdateRequest(BaseModel):
    title: Optional[str] = None
    system_prompt: Optional[str] = None
    template_text: Optional[str] = None
    variables: Optional[List[str]] = None
    is_active: Optional[bool] = None

