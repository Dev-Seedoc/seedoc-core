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
export type PasswordResetConfirmRequest = Schemas["PasswordResetConfirmRequest"];
export type PasswordResetRequest = Schemas["PasswordResetRequest"];
export type ReauthenticateRequest = Schemas["ReauthenticateRequest"];
export type TenantMembershipRead = Schemas["TenantMembershipRead"];
export type TotpSetupRead = Schemas["TotpSetupRead"];
export type UserRead = Schemas["UserRead"];
export type VerifyTotpRequest = Schemas["VerifyTotpRequest"];
