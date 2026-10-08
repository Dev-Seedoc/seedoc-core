// One function per operation_id, named camelCase(operation_id) (docs/API.md). Each returns the response body or
// throws ApiError.
import { client } from "./client";
import { toApiError } from "./errors";
import type {
  AcceptInvitationRequest,
  HealthRead,
  InvitationPreview,
  LoginRequest,
  MeRead,
  PasswordResetConfirmRequest,
  PasswordResetRequest,
  ReauthenticateRequest,
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
