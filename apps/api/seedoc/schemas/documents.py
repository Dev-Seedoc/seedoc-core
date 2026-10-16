"""Request/response schemas for documents and versions (API.md §3.3)."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, Field, field_validator

from seedoc.languages import SUPPORTED_LANGUAGES
from seedoc.models.documents import AccessLevel, DocType, ProcessingStatus
from seedoc.schemas.common import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, Name


def _check_language(value: str) -> str:
    if value not in SUPPORTED_LANGUAGES:
        raise ValueError("unsupported language")
    return value


def _reject_machine(value: UUID | None) -> UUID | None:
    # Machines arrive with M2 (migration 0003 adds the foreign key); until then a document cannot be machine-specific.
    if value is not None:
        raise ValueError("machine-specific documents are not available yet")
    return value


Language = Annotated[str, AfterValidator(_check_language)]
MachineId = Annotated[UUID | None, AfterValidator(_reject_machine)]
Title = Name


class DocumentCreate(BaseModel):
    """Missing `doc_type` / `language` / `access_level` come from the folder defaults (BUSINESS_RULES §3)."""

    upload_id: UUID
    folder_id: UUID
    title: Title
    doc_type: DocType | None = None
    language: Language | None = None
    access_level: AccessLevel | None = None
    machine_id: MachineId = None


class DocumentUpdate(BaseModel):
    """A field left out stays as it is; `null` is a 422 except for `machine_id`."""

    title: Title | None = None
    folder_id: UUID | None = None
    doc_type: DocType | None = None
    language: Language | None = None
    access_level: AccessLevel | None = None
    machine_id: MachineId = None

    @field_validator("title", "folder_id", "doc_type", "language", "access_level", mode="before")
    @classmethod
    def _reject_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("cannot be null; leave the field out to keep it")
        return value


class DocumentVersionCreate(BaseModel):
    upload_id: UUID


class DocumentListQuery(BaseModel):
    """Filters of `list_documents`; every filter is optional and they combine with AND."""

    space_id: UUID | None = None
    folder_id: UUID | None = None
    language: Language | None = None
    access_level: AccessLevel | None = None
    doc_type: DocType | None = None
    processing_status: ProcessingStatus | None = None
    machine_id: UUID | None = None
    q: str | None = Field(default=None, max_length=200)
    include_trashed: bool = False
    cursor: str | None = None
    limit: int = Field(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT)


class DocumentListItem(BaseModel):
    id: UUID
    title: str
    doc_type: DocType
    language: str
    access_level: AccessLevel
    folder_id: UUID
    folder_path: str  # "<space name>/<folder>/<subfolder>" (BUSINESS_RULES §6)
    current_version_no: int | None
    processing_status: ProcessingStatus | None  # of the current version
    group_id: UUID
    machine_id: UUID | None
    trashed_at: datetime | None
    updated_at: datetime


class LanguageVariantRead(BaseModel):
    document_id: UUID
    language: str
    title: str


class DocumentRead(DocumentListItem):
    versions_count: int
    language_variants: list[LanguageVariantRead]  # the other documents of the group, by language
    released_in_count: int  # releases that freeze a version of this document (0 until the release tables exist, M2)
    duplicate_of_document_id: UUID | None = None  # create only: another document of the tenant with the same file


class DocumentVersionRead(BaseModel):
    id: UUID
    document_id: UUID
    version_no: int
    file_name: str
    size_bytes: int
    sha256_hex: str
    page_count: int | None
    processing_status: ProcessingStatus
    processing_error: str | None
    processed_at: datetime | None
    is_current: bool
    created_by: UUID | None
    created_at: datetime
    duplicate_of_document_id: UUID | None = None  # create only, as in DocumentRead


class VersionFileUrlRead(BaseModel):
    url: str  # presigned GET, a credential: never log it
    expires_at: datetime
