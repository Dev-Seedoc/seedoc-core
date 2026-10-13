"""Request/response schemas for folders (API.md §3.2)."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, Field, field_validator

from seedoc.languages import SUPPORTED_LANGUAGES
from seedoc.models.documents import AccessLevel, DocType
from seedoc.schemas.common import Name

# `folders.sort_order` is a Postgres `int`; a larger number is a 422 here instead of a database error.
INT4_MIN, INT4_MAX = -(2**31), 2**31 - 1


def _check_language(value: str) -> str:
    """Exactly one of `SUPPORTED_LANGUAGES` (lowercase ISO 639-1): "DE" is rejected, not lowercased."""
    if value not in SUPPORTED_LANGUAGES:
        raise ValueError("unsupported language")
    return value


Language = Annotated[str, AfterValidator(_check_language)]
SortOrder = Annotated[int, Field(ge=INT4_MIN, le=INT4_MAX)]


class FolderCreate(BaseModel):
    space_id: UUID
    parent_id: UUID | None = None
    name: Name
    default_access_level: AccessLevel
    default_doc_type: DocType | None = None
    default_language: Language | None = None


class FolderUpdate(BaseModel):
    """A field left out stays as it is. `null` clears `default_doc_type` / `default_language`; for the other fields
    `null` is a 422. Moving a folder (`parent_id`) is Later (API.md §3.2)."""

    name: Name | None = None
    sort_order: SortOrder | None = None
    default_access_level: AccessLevel | None = None
    default_doc_type: DocType | None = None
    default_language: Language | None = None

    @field_validator("name", "sort_order", "default_access_level", mode="before")
    @classmethod
    def _reject_null(cls, value: object) -> object:
        # Runs only for fields present in the body, so leaving one out is still allowed.
        if value is None:
            raise ValueError("cannot be null; leave the field out to keep it")
        return value


class FolderRead(BaseModel):
    id: UUID
    space_id: UUID
    parent_id: UUID | None
    name: str
    path: str  # folder names from the root, joined by "/", without the space name
    sort_order: int
    default_access_level: AccessLevel
    default_doc_type: DocType | None
    default_language: str | None
    created_at: datetime
    updated_at: datetime
