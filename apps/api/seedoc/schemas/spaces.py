"""Request/response schemas for spaces (API.md §3.2)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from seedoc.schemas.common import Name


class SpaceCreate(BaseModel):
    name: Name


class SpaceUpdate(BaseModel):
    name: Name | None = None


class SpaceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: datetime
