import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { stubApi } from "@/test/renderRoute";

import { createQueryClient } from "../queryClient";
import type { FolderRead } from "../types";
import { useDeleteFolder, useFolders } from "./documents";

const TENANT_ID = "00000000-0000-4000-8000-00000000000a";
const SPACE_ID = "00000000-0000-4000-8000-0000000000b1";
const FOLDERS = `GET /api/v1/app/tenants/${TENANT_ID}/folders`;

const FOLDER: FolderRead = {
  id: "00000000-0000-4000-8000-0000000000f1",
  space_id: SPACE_ID,
  parent_id: null,
  name: "Wartung",
  path: "Wartung",
  sort_order: 0,
  default_access_level: "public",
  default_doc_type: null,
  default_language: null,
  created_at: "2026-10-13T10:00:00Z",
  updated_at: "2026-10-13T10:00:00Z",
};

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

let queryClient = createQueryClient();

afterEach(() => {
  vi.unstubAllGlobals();
  queryClient = createQueryClient();
});

describe("document hooks", () => {
  it("loads no folders until a space is chosen", () => {
    const fetchMock = stubApi({});

    const { result } = renderHook(() => useFolders(TENANT_ID, undefined), { wrapper });

    expect(result.current.fetchStatus).toBe("idle");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("returns the folder items of the space", async () => {
    stubApi({ [FOLDERS]: { status: 200, body: { items: [FOLDER], next_cursor: null } } });

    const { result } = renderHook(() => useFolders(TENANT_ID, SPACE_ID), { wrapper });

    await waitFor(() => {
      expect(result.current.data).toEqual([FOLDER]);
    });
  });

  it("reloads the folder list after deleting a folder", async () => {
    let listed = [FOLDER];
    const fetchMock = stubApi({
      [FOLDERS]: () => ({ status: 200, body: { items: listed, next_cursor: null } }),
      [`DELETE /api/v1/app/tenants/${TENANT_ID}/folders/${FOLDER.id}`]: () => {
        listed = [];
        return { status: 204 };
      },
    });
    const { result } = renderHook(
      () => ({ folders: useFolders(TENANT_ID, SPACE_ID), remove: useDeleteFolder(TENANT_ID) }),
      { wrapper },
    );
    await waitFor(() => {
      expect(result.current.folders.data).toHaveLength(1);
    });

    await act(() => result.current.remove.mutateAsync(FOLDER.id));

    await waitFor(() => {
      expect(result.current.folders.data).toEqual([]);
    });
    expect(fetchMock.mock.calls.filter(([request]) => request.method === "GET")).toHaveLength(2);
  });
});
