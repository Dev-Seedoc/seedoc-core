import { afterEach, describe, expect, it, vi } from "vitest";

import { getMe, login, logout } from "./endpoints";
import { ApiError } from "./errors";

const ME = {
  user: { id: "8a7e1c1e-0000-4000-8000-000000000001", email: "owner@example.com", full_name: "Olga Owner" },
  memberships: [],
  operator_orgs: [],
  is_staff: false,
  mfa_verified: false,
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function mockFetch(response: Response) {
  const fetchMock = vi.fn<(request: Request) => Promise<Response>>().mockResolvedValue(response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("endpoints", () => {
  it("login posts the body with credentials and returns MeRead", async () => {
    const fetchMock = mockFetch(jsonResponse(200, ME));

    const me = await login({ email: "owner@example.com", password: "correct-horse-battery" });

    expect(me).toEqual(ME);
    const request = fetchMock.mock.calls[0]?.[0];
    expect(request?.method).toBe("POST");
    expect(new URL(request?.url ?? "").pathname).toBe("/api/v1/auth/login");
    expect(request?.credentials).toBe("include");
    expect(await request?.json()).toEqual({ email: "owner@example.com", password: "correct-horse-battery" });
  });

  it("logout resolves on 204", async () => {
    mockFetch(new Response(null, { status: 204 }));

    await expect(logout()).resolves.toBeUndefined();
  });

  it("throws ApiError with the code from the error body", async () => {
    mockFetch(jsonResponse(401, { error: { code: "unauthenticated", message: "unauthenticated", details: {} } }));

    const error: unknown = await getMe().catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(401);
    expect((error as ApiError).code).toBe("unauthenticated");
  });
});
