"""Request/response schemas for products, their document sets, the language matrix and product releases
(API.md §3.4)."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from seedoc.models.documents import AccessLevel, DocType
from seedoc.schemas.common import Name, RequiredLanguages

MAX_PRODUCT_DOCUMENTS = 500


class ProductCreate(BaseModel):
    name: Name
    space_id: UUID | None = None
    required_languages: RequiredLanguages = Field(default_factory=lambda: ["de"])


class ProductUpdate(BaseModel):
    """A field left out stays as it is; `null` is a 422 except for `space_id` (clears it)."""

    name: Name | None = None
    space_id: UUID | None = None
    required_languages: RequiredLanguages | None = None

    @field_validator("name", "required_languages", mode="before")
    @classmethod
    def _reject_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("cannot be null; leave the field out to keep it")
        return value


class ProductRead(BaseModel):
    id: UUID
    name: str
    space_id: UUID | None
    required_languages: list[str]
    document_count: int  # untrashed documents of the set
    latest_release_no: int | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProductDocumentsSet(BaseModel):
    """Body of `set_product_documents`: the whole new set (duplicates are ignored)."""

    document_ids: Annotated[list[UUID], Field(max_length=MAX_PRODUCT_DOCUMENTS)]


# ─────────────────────────── language matrix (also used for deliveries) ───────────────────────────

LanguageStatus = Literal["present", "missing", "waived"]


class LanguageMatrixCell(BaseModel):
    status: LanguageStatus
    document_id: UUID | None = None  # with "present"
    waiver_reason: str | None = None  # with "waived" (deliveries only)


class LanguageMatrixRow(BaseModel):
    """One language group: `title` / `doc_type` of its document in the first required language it has."""

    group_id: UUID
    title: str
    doc_type: DocType
    cells: dict[str, LanguageMatrixCell]  # one per language of `LanguageMatrixRead.languages`


class LanguageMatrixRead(BaseModel):
    languages: list[str]
    rows: list[LanguageMatrixRow]


# ─────────────────────────── product releases (read only here) ───────────────────────────


class ProductReleaseRead(BaseModel):
    id: UUID
    release_no: int
    change_note: str | None
    item_count: int
    created_at: datetime
    created_by_name: str | None  # `full_name` of `created_by`; null when the release has no creator


class ProductReleaseItemRead(BaseModel):
    id: UUID
    document_id: UUID
    version_id: UUID
    version_no: int
    title: str
    doc_type: DocType
    language: str
    access_level: AccessLevel
    folder_path: str


class ProductReleaseDetailRead(ProductReleaseRead):
    items: list[ProductReleaseItemRead]  # sorted by folder_path, title, language
