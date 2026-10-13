"""Request/response schemas for uploads (API.md §3.3)."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

# Lowercase in the stored row; the browser may send either case.
Sha256Hex = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, pattern=r"^[0-9a-fA-F]{64}$")]
FileName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class UploadCreate(BaseModel):
    file_name: FileName
    size_bytes: int = Field(gt=0)  # the 100 MB limit is a 413 `file_too_large`, checked by the service
    sha256_hex: Sha256Hex
    content_type: str = Field(max_length=255)  # only application/pdf; anything else is a 415


class UploadRead(BaseModel):
    upload_id: UUID
    upload_url: str  # presigned PUT, a credential: never log it
    expires_at: datetime  # when `upload_url` stops working (15 min)
