// Re-exports of the generated API types under their OpenAPI names (NAMING §6). Never hand-write API types.
import type { components, operations } from "./schema";

type Schemas = components["schemas"];

export type AcceptInvitationRequest = Schemas["AcceptInvitationRequest"];
export type AccessLevel = Schemas["AccessLevel"];
export type DocType = Schemas["DocType"];
export type DocumentCreate = Schemas["DocumentCreate"];
export type DocumentListItem = Schemas["DocumentListItem"];
export type DocumentRead = Schemas["DocumentRead"];
export type FolderCreate = Schemas["FolderCreate"];
export type FolderRead = Schemas["FolderRead"];
export type FolderUpdate = Schemas["FolderUpdate"];
export type HealthRead = Schemas["HealthRead"];
export type InvitationKind = Schemas["InvitationKind"];
export type InvitationPreview = Schemas["InvitationPreview"];
export type LoginRequest = Schemas["LoginRequest"];
export type MemberRole = Schemas["MemberRole"];
export type MeRead = Schemas["MeRead"];
export type OperatorOrgMembershipRead = Schemas["OperatorOrgMembershipRead"];
export type OperatorRole = Schemas["OperatorRole"];
// Page[...] (NAMING §4) under the names FastAPI generates for them.
export type Page_DocumentListItem_ = Schemas["Page_DocumentListItem_"];
export type Page_FolderRead_ = Schemas["Page_FolderRead_"];
export type Page_SpaceRead_ = Schemas["Page_SpaceRead_"];
export type Page_StaffTenantListItem_ = Schemas["Page_StaffTenantListItem_"];
export type PasswordResetConfirmRequest = Schemas["PasswordResetConfirmRequest"];
export type PasswordResetRequest = Schemas["PasswordResetRequest"];
export type ProcessingStatus = Schemas["ProcessingStatus"];
export type ReauthenticateRequest = Schemas["ReauthenticateRequest"];
export type SpaceCreate = Schemas["SpaceCreate"];
export type SpaceRead = Schemas["SpaceRead"];
export type SpaceUpdate = Schemas["SpaceUpdate"];
export type StaffTenantCreate = Schemas["StaffTenantCreate"];
export type StaffTenantInvitationRead = Schemas["StaffTenantInvitationRead"];
export type StaffTenantListItem = Schemas["StaffTenantListItem"];
export type StaffTenantMemberRead = Schemas["StaffTenantMemberRead"];
export type StaffTenantRead = Schemas["StaffTenantRead"];
export type StaffTenantUpdate = Schemas["StaffTenantUpdate"];
export type TenantMembershipRead = Schemas["TenantMembershipRead"];
export type TenantStatus = Schemas["TenantStatus"];
export type TotpSetupRead = Schemas["TotpSetupRead"];
export type UploadCreate = Schemas["UploadCreate"];
export type UploadRead = Schemas["UploadRead"];
export type UserRead = Schemas["UserRead"];
export type VerifyTotpRequest = Schemas["VerifyTotpRequest"];

// Query parameters of list_documents (API.md §3.3), taken from the generated operation; not a schema of its own.
export type ListDocumentsQuery = NonNullable<operations["list_documents"]["parameters"]["query"]>;
