// Re-exports of the generated API types under their OpenAPI names (NAMING §6). Never hand-write API types.
import type { components } from "./schema";

type Schemas = components["schemas"];

export type AcceptInvitationRequest = Schemas["AcceptInvitationRequest"];
export type HealthRead = Schemas["HealthRead"];
export type InvitationKind = Schemas["InvitationKind"];
export type InvitationPreview = Schemas["InvitationPreview"];
export type LoginRequest = Schemas["LoginRequest"];
export type MemberRole = Schemas["MemberRole"];
export type MeRead = Schemas["MeRead"];
export type OperatorOrgMembershipRead = Schemas["OperatorOrgMembershipRead"];
export type OperatorRole = Schemas["OperatorRole"];
// Page[StaffTenantListItem] (NAMING §4) under the name FastAPI generates for it.
export type Page_StaffTenantListItem_ = Schemas["Page_StaffTenantListItem_"];
export type PasswordResetConfirmRequest = Schemas["PasswordResetConfirmRequest"];
export type PasswordResetRequest = Schemas["PasswordResetRequest"];
export type ReauthenticateRequest = Schemas["ReauthenticateRequest"];
export type StaffTenantCreate = Schemas["StaffTenantCreate"];
export type StaffTenantInvitationRead = Schemas["StaffTenantInvitationRead"];
export type StaffTenantListItem = Schemas["StaffTenantListItem"];
export type StaffTenantMemberRead = Schemas["StaffTenantMemberRead"];
export type StaffTenantRead = Schemas["StaffTenantRead"];
export type StaffTenantUpdate = Schemas["StaffTenantUpdate"];
export type TenantMembershipRead = Schemas["TenantMembershipRead"];
export type TenantStatus = Schemas["TenantStatus"];
export type TotpSetupRead = Schemas["TotpSetupRead"];
export type UserRead = Schemas["UserRead"];
export type VerifyTotpRequest = Schemas["VerifyTotpRequest"];
