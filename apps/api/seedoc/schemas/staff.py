"""Request/response schemas for `/staff` (API.md §6)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from seedoc.models.tenants import MemberRole, TenantStatus

# Lowercase words joined by single hyphens, e.g. "mueller-maschinenbau".
SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
# Deliberately simple: one "@", no spaces, a dot in the domain. Real validation is the invitation e-mail itself.
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class StaffTenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=2, max_length=63, pattern=SLUG_PATTERN)
    owner_email: str = Field(max_length=254, pattern=EMAIL_PATTERN)


class StaffTenantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    status: TenantStatus | None = None


class StaffTenantListItem(BaseModel):
    id: UUID
    name: str
    slug: str
    status: TenantStatus
    member_count: int
    created_at: datetime


class StaffTenantMemberRead(BaseModel):
    user_id: UUID
    email: str
    full_name: str | None
    role: MemberRole


class StaffTenantInvitationRead(BaseModel):
    id: UUID
    email: str
    role: MemberRole | None
    expires_at: datetime
    created_at: datetime


class StaffTenantRead(BaseModel):
    id: UUID
    name: str
    slug: str
    status: TenantStatus
    created_at: datetime
    updated_at: datetime
    members: list[StaffTenantMemberRead]
    open_invitations: list[StaffTenantInvitationRead]


class StaffUserListItem(BaseModel):
    id: UUID
    email: str
    full_name: str | None
    is_staff: bool
    has_totp: bool
    last_login_at: datetime | None
    created_at: datetime
