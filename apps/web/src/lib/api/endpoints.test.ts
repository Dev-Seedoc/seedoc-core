import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createDocument,
  createUpload,
  deleteFolder,
  getMe,
  getProductRelease,
  getVersionFileUrl,
  listDocuments,
  listFolders,
  login,
  logout,
  setProductDocuments,
  trashDocument,
  unlinkLanguageVariant,
  updateFolder,
} from "./endpoints";
import { ApiError } from "./errors";

const ME = {
  user: { id: "8a7e1c1e-0000-4000-8000-000000000001", email: "owner@example.com", full_name: "Olga Owner" },
  memberships: [],
  operator_orgs: [],
  is_staff: false,
  has_totp: false,
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

  it("puts the tenant into the /app path and space_id into the query", async () => {
    const fetchMock = mockFetch(jsonResponse(200, { items: [], next_cursor: null }));

    await listFolders("t-1", "s-1");

    const url = new URL(fetchMock.mock.calls[0]?.[0].url ?? "");
    expect(url.pathname).toBe("/api/v1/app/tenants/t-1/folders");
    expect(url.searchParams.get("space_id")).toBe("s-1");
  });

  it("patches and deletes a folder by id", async () => {
    const fetchMock = mockFetch(jsonResponse(200, {}));
    await updateFolder("t-1", "f-1", { default_language: null });
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    await deleteFolder("t-1", "f-1");

    const [patch, remove] = fetchMock.mock.calls.map(([request]) => request);
    expect([patch?.method, new URL(patch?.url ?? "").pathname]).toEqual([
      "PATCH",
      "/api/v1/app/tenants/t-1/folders/f-1",
    ]);
    expect(await patch?.json()).toEqual({ default_language: null });
    expect([remove?.method, new URL(remove?.url ?? "").pathname]).toEqual([
      "DELETE",
      "/api/v1/app/tenants/t-1/folders/f-1",
    ]);
  });

  it("sends the document filters as query parameters and leaves out empty ones", async () => {
    const fetchMock = mockFetch(jsonResponse(200, { items: [], next_cursor: null }));

    await listDocuments("t-1", { space_id: "s-1", doc_type: "datasheet", q: "Pumpe", cursor: "c-2" });

    const url = new URL(fetchMock.mock.calls[0]?.[0].url ?? "");
    expect(url.pathname).toBe("/api/v1/app/tenants/t-1/documents");
    expect(Object.fromEntries(url.searchParams)).toEqual({
      space_id: "s-1",
      doc_type: "datasheet",
      q: "Pumpe",
      cursor: "c-2",
    });
  });

  it("trashes a document with POST …/trash", async () => {
    const fetchMock = mockFetch(jsonResponse(200, {}));

    await trashDocument("t-1", "d-1");

    const request = fetchMock.mock.calls[0]?.[0];
    expect([request?.method, new URL(request?.url ?? "").pathname]).toEqual([
      "POST",
      "/api/v1/app/tenants/t-1/documents/d-1/trash",
    ]);
  });

  it("creates an upload and then the document from it", async () => {
    const fetchMock = mockFetch(jsonResponse(201, {}));
    await createUpload("t-1", {
      file_name: "a.pdf",
      size_bytes: 5,
      sha256_hex: "ab".repeat(32),
      content_type: "application/pdf",
    });
    fetchMock.mockResolvedValueOnce(jsonResponse(201, {}));
    await createDocument("t-1", { upload_id: "u-1", folder_id: "f-1", title: "Anleitung" });

    const [upload, document] = fetchMock.mock.calls.map(([request]) => request);
    expect([upload?.method, new URL(upload?.url ?? "").pathname]).toEqual(["POST", "/api/v1/app/tenants/t-1/uploads"]);
    expect([document?.method, new URL(document?.url ?? "").pathname]).toEqual([
      "POST",
      "/api/v1/app/tenants/t-1/documents",
    ]);
    expect(await document?.json()).toEqual({ upload_id: "u-1", folder_id: "f-1", title: "Anleitung" });
  });

  it("builds the version file and language variant URLs from all ids", async () => {
    const fetchMock = mockFetch(jsonResponse(200, { url: "https://s3.test/x", expires_at: "" }));
    await getVersionFileUrl("t-1", "d-1", "v-1");
    fetchMock.mockResolvedValueOnce(jsonResponse(200, {}));
    await unlinkLanguageVariant("t-1", "d-1", "d-2");

    const [file, unlink] = fetchMock.mock.calls.map(([request]) => request);
    expect([file?.method, new URL(file?.url ?? "").pathname]).toEqual([
      "GET",
      "/api/v1/app/tenants/t-1/documents/d-1/versions/v-1/file",
    ]);
    expect([unlink?.method, new URL(unlink?.url ?? "").pathname]).toEqual([
      "DELETE",
      "/api/v1/app/tenants/t-1/documents/d-1/language-variants/d-2",
    ]);
  });

  it("setProductDocuments puts the whole set and getProductRelease puts the release number in the path", async () => {
    const fetchMock = vi
      .fn<(request: Request) => Promise<Response>>()
      .mockResolvedValueOnce(jsonResponse(200, { items: [], next_cursor: null }))
      .mockResolvedValueOnce(jsonResponse(200, { id: "r-2", release_no: 2, items: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await setProductDocuments("t-1", "p-1", { document_ids: ["d-1", "d-2"] });
    await getProductRelease("t-1", "p-1", 2);

    const [set, release] = fetchMock.mock.calls.map(([request]) => request);
    expect([set?.method, new URL(set?.url ?? "").pathname]).toEqual([
      "PUT",
      "/api/v1/app/tenants/t-1/products/p-1/documents",
    ]);
    expect(await set?.json()).toEqual({ document_ids: ["d-1", "d-2"] });
    expect([release?.method, new URL(release?.url ?? "").pathname]).toEqual([
      "GET",
      "/api/v1/app/tenants/t-1/products/p-1/releases/2",
    ]);
  });
});
