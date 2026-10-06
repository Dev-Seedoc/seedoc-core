"""Request/response schemas for `/auth` (API.md §2)."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from seedoc.models.operators import OperatorRole
from seedoc.models.tenants import InvitationKind, MemberRole

# BUSINESS_RULES §2: 12 to 128 characters, no other composition rules.
NewPassword = Annotated[str, Field(min_length=12, max_length=128)]
# Existing passwords are only length-capped, so a huge body is rejected before Argon2 runs.
SubmittedPassword = Annotated[str, Field(min_length=1, max_length=128)]


class LoginRequest(BaseModel):
    email: str
    password: SubmittedPassword


class UserRead(BaseModel):
    id: UUID
    email: str
    full_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class TenantMembershipRead(BaseModel):
    tenant_id: UUID
    tenant_name: str
    role: MemberRole


class OperatorOrgMembershipRead(BaseModel):
    operator_org_id: UUID
    name: str
    role: OperatorRole


class MeRead(BaseModel):
    user: UserRead
    memberships: list[TenantMembershipRead]
    operator_orgs: list[OperatorOrgMembershipRead]
    is_staff: bool
    mfa_verified: bool


class ReauthenticateRequest(BaseModel):
    password: SubmittedPassword


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetConfirmRequest(BaseModel):
    token: str
    password: NewPassword


class InvitationPreview(BaseModel):
    kind: InvitationKind
    tenant_name: str | None = None
    operator_org_name: str | None = None
    email: str
    has_account: bool


class AcceptInvitationRequest(BaseModel):
    password: NewPassword | None = None  # required only when the invitee has no account yet
    full_name: str | None = None


class TotpSetupRead(BaseModel):
    otpauth_uri: str


class VerifyTotpRequest(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")
