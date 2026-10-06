from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from seedoc.models.tenants import InvitationKind, MemberRole


class LoginRequest(BaseModel):
    email: str
    password: str


class UserProfile(BaseModel):
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
    role: str


class MeRead(BaseModel):
    user: UserProfile
    memberships: list[TenantMembershipRead]
    operator_orgs: list[OperatorOrgMembershipRead]
    is_staff: bool
    mfa_verified: bool


class ReauthenticateRequest(BaseModel):
    password: str


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetConfirmRequest(BaseModel):
    token: str
    password: str


class InvitationPreview(BaseModel):
    kind: InvitationKind
    tenant_name: str | None = None
    operator_org_name: str | None = None
    email: str
    has_account: bool


class AcceptInvitationRequest(BaseModel):
    password: str | None = None
    full_name: str | None = None


class TotpSetupResponse(BaseModel):
    otpauth_uri: str


class VerifyTotpRequest(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")
