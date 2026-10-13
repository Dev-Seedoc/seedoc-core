// One function per operation_id, named camelCase(operation_id) (docs/API.md). Each returns the response body or
// throws ApiError.
import { client } from "./client";
import { toApiError } from "./errors";
import type {
  AcceptInvitationRequest,
  FolderCreate,
  FolderRead,
  FolderUpdate,
  HealthRead,
  InvitationPreview,
  LoginRequest,
  MeRead,
  Page_FolderRead_,
  Page_SpaceRead_,
  Page_StaffTenantListItem_,
  PasswordResetConfirmRequest,
  PasswordResetRequest,
  ReauthenticateRequest,
  SpaceCreate,
  SpaceRead,
  SpaceUpdate,
  StaffTenantCreate,
  StaffTenantRead,
  StaffTenantUpdate,
  TotpSetupRead,
  VerifyTotpRequest,
} from "./types";

interface ApiResult<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

async function unwrap<T>(request: Promise<ApiResult<T>>): Promise<T> {
  const { data, error, response } = await request;
  if (!response.ok || data === undefined) {
    throw toApiError(response.status, error);
  }
  return data;
}

// For 202/204 endpoints, which have no body.
async function unwrapEmpty(request: Promise<ApiResult<unknown>>): Promise<void> {
  const { error, response } = await request;
  if (!response.ok) {
    throw toApiError(response.status, error);
  }
}

// Health

export function getHealth(): Promise<HealthRead> {
  return unwrap(client.GET("/api/v1/health"));
}

// Auth

export function login(body: LoginRequest): Promise<MeRead> {
  return unwrap(client.POST("/api/v1/auth/login", { body }));
}

export function logout(): Promise<void> {
  return unwrapEmpty(client.POST("/api/v1/auth/logout"));
}

export function getMe(): Promise<MeRead> {
  return unwrap(client.GET("/api/v1/auth/me"));
}

export function reauthenticate(body: ReauthenticateRequest): Promise<void> {
  return unwrapEmpty(client.POST("/api/v1/auth/reauth", { body }));
}

export function requestPasswordReset(body: PasswordResetRequest): Promise<void> {
  return unwrapEmpty(client.POST("/api/v1/auth/password-reset", { body }));
}

export function confirmPasswordReset(body: PasswordResetConfirmRequest): Promise<void> {
  return unwrapEmpty(client.POST("/api/v1/auth/password-reset/confirm", { body }));
}

export function getInvitation(token: string): Promise<InvitationPreview> {
  return unwrap(client.GET("/api/v1/auth/invitations/{token}", { params: { path: { token } } }));
}

export function acceptInvitation(token: string, body: AcceptInvitationRequest): Promise<MeRead> {
  return unwrap(client.POST("/api/v1/auth/invitations/{token}/accept", { params: { path: { token } }, body }));
}

export function setupTotp(): Promise<TotpSetupRead> {
  return unwrap(client.POST("/api/v1/auth/totp/setup"));
}

export function verifyTotp(body: VerifyTotpRequest): Promise<void> {
  return unwrapEmpty(client.POST("/api/v1/auth/totp/verify", { body }));
}

// Staff

export function staffListTenants(cursor?: string): Promise<Page_StaffTenantListItem_> {
  return unwrap(client.GET("/api/v1/staff/tenants", { params: { query: { cursor } } }));
}

export function staffCreateTenant(body: StaffTenantCreate): Promise<StaffTenantRead> {
  return unwrap(client.POST("/api/v1/staff/tenants", { body }));
}

export function staffGetTenant(tenantId: string): Promise<StaffTenantRead> {
  return unwrap(client.GET("/api/v1/staff/tenants/{tenant_id}", { params: { path: { tenant_id: tenantId } } }));
}

export function staffUpdateTenant(tenantId: string, body: StaffTenantUpdate): Promise<StaffTenantRead> {
  return unwrap(client.PATCH("/api/v1/staff/tenants/{tenant_id}", { params: { path: { tenant_id: tenantId } }, body }));
}

// Manufacturer app: spaces and folders (API.md §3.2)

function tenantPath(tenantId: string) {
  return { tenant_id: tenantId };
}

export function listSpaces(tenantId: string): Promise<Page_SpaceRead_> {
  return unwrap(client.GET("/api/v1/app/tenants/{tenant_id}/spaces", { params: { path: tenantPath(tenantId) } }));
}

export function createSpace(tenantId: string, body: SpaceCreate): Promise<SpaceRead> {
  return unwrap(
    client.POST("/api/v1/app/tenants/{tenant_id}/spaces", { params: { path: tenantPath(tenantId) }, body }),
  );
}

export function updateSpace(tenantId: string, spaceId: string, body: SpaceUpdate): Promise<SpaceRead> {
  return unwrap(
    client.PATCH("/api/v1/app/tenants/{tenant_id}/spaces/{space_id}", {
      params: { path: { ...tenantPath(tenantId), space_id: spaceId } },
      body,
    }),
  );
}

export function listFolders(tenantId: string, spaceId: string): Promise<Page_FolderRead_> {
  return unwrap(
    client.GET("/api/v1/app/tenants/{tenant_id}/folders", {
      params: { path: tenantPath(tenantId), query: { space_id: spaceId } },
    }),
  );
}

export function createFolder(tenantId: string, body: FolderCreate): Promise<FolderRead> {
  return unwrap(
    client.POST("/api/v1/app/tenants/{tenant_id}/folders", { params: { path: tenantPath(tenantId) }, body }),
  );
}

export function updateFolder(tenantId: string, folderId: string, body: FolderUpdate): Promise<FolderRead> {
  return unwrap(
    client.PATCH("/api/v1/app/tenants/{tenant_id}/folders/{folder_id}", {
      params: { path: { ...tenantPath(tenantId), folder_id: folderId } },
      body,
    }),
  );
}

export function deleteFolder(tenantId: string, folderId: string): Promise<void> {
  return unwrapEmpty(
    client.DELETE("/api/v1/app/tenants/{tenant_id}/folders/{folder_id}", {
      params: { path: { ...tenantPath(tenantId), folder_id: folderId } },
    }),
  );
}
