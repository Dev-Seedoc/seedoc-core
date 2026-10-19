import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { stubApi } from "@/test/renderRoute";

import { createQueryClient } from "../queryClient";
import type { DocumentListItem, FolderRead } from "../types";
import {
  getProcessingRefetchInterval,
  PROCESSING_REFETCH_MS,
  useDeleteFolder,
  useDocuments,
  useFolders,
  useTrashDocument,
} from "./documents";

const TENANT_ID = "00000000-0000-4000-8000-00000000000a";
const SPACE_ID = "00000000-0000-4000-8000-0000000000b1";
const FOLDERS = `GET /api/v1/app/tenants/${TENANT_ID}/folders`;
const DOCUMENTS = `GET /api/v1/app/tenants/${TENANT_ID}/documents`;

function documentItem(id: string): DocumentListItem {
  return {
    id,
    title: `Dokument ${id}`,
    doc_type: "datasheet",
    language: "de",
    access_level: "public",
    folder_id: "f-1",
    folder_path: "Wartung",
    current_version_no: 1,
    processing_status: "ready",
    group_id: id,
    machine_id: null,
    trashed_at: null,
    updated_at: "2026-10-16T10:00:00Z",
  };
}

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

  it("loads the next document page with the cursor and keeps the filters", async () => {
    const fetchMock = stubApi({
      [DOCUMENTS]: (request) =>
        new URL(request.url).searchParams.get("cursor") === "c-2"
          ? { status: 200, body: { items: [documentItem("d-2")], next_cursor: null } }
          : { status: 200, body: { items: [documentItem("d-1")], next_cursor: "c-2" } },
    });
    const { result } = renderHook(() => useDocuments(TENANT_ID, { folder_id: "f-1" }), { wrapper });
    await waitFor(() => {
      expect(result.current.hasNextPage).toBe(true);
    });

    await act(() => result.current.fetchNextPage());

    await waitFor(() => {
      expect(result.current.data?.pages.flatMap((page) => page.items).map((item) => item.id)).toEqual(["d-1", "d-2"]);
    });
    const second = new URL(fetchMock.mock.calls[1]?.[0].url ?? "");
    expect([second.searchParams.get("folder_id"), second.searchParams.get("cursor")]).toEqual(["f-1", "c-2"]);
    expect(result.current.hasNextPage).toBe(false);
  });

  it("trashes several documents, reports failures and reloads the list once", async () => {
    const fetchMock = stubApi({
      [DOCUMENTS]: { status: 200, body: { items: [documentItem("d-1")], next_cursor: null } },
      [`POST /api/v1/app/tenants/${TENANT_ID}/documents/d-1/trash`]: { status: 200, body: {} },
      [`POST /api/v1/app/tenants/${TENANT_ID}/documents/d-2/trash`]: { status: 200, body: {} },
      // d-3: no answer stubbed → 404 not_found
    });
    const { result } = renderHook(
      () => ({ documents: useDocuments(TENANT_ID, {}), trash: useTrashDocument(TENANT_ID) }),
      { wrapper },
    );
    await waitFor(() => {
      expect(result.current.documents.isSuccess).toBe(true);
    });

    const outcome = await act(() => result.current.trash.mutateAsync(["d-1", "d-2", "d-3"]));

    expect(outcome).toEqual({ succeeded: ["d-1", "d-2"], failed: ["d-3"] });
    await waitFor(() => {
      expect(fetchMock.mock.calls.filter(([request]) => request.method === "GET")).toHaveLength(2);
    });
    expect(fetchMock.mock.calls.filter(([request]) => request.method === "POST")).toHaveLength(3);
  });

  it("asks again while a listed document is still processed, and stops when all are done", () => {
    const pages = (statuses: DocumentListItem["processing_status"][]) => ({
      pages: [
        {
          items: statuses.map((status, index) => ({
            ...documentItem(`d-${String(index)}`),
            processing_status: status,
          })),
          next_cursor: null,
        },
      ],
      pageParams: [undefined],
    });

    expect(getProcessingRefetchInterval(pages(["ready", "processing"]))).toBe(PROCESSING_REFETCH_MS);
    expect(getProcessingRefetchInterval(pages(["pending"]))).toBe(PROCESSING_REFETCH_MS);
    expect(getProcessingRefetchInterval(pages(["ready", "failed", null]))).toBe(false);
    expect(getProcessingRefetchInterval(undefined)).toBe(false);
  });

  it("polls the list while a document is processed and stops when it is ready", { timeout: 15_000 }, async () => {
    let status: DocumentListItem["processing_status"] = "processing";
    const fetchMock = stubApi({
      [DOCUMENTS]: () => ({
        status: 200,
        body: { items: [{ ...documentItem("d-1"), processing_status: status }], next_cursor: null },
      }),
    });
    const { result } = renderHook(() => useDocuments(TENANT_ID, {}), { wrapper });
    const listCalls = () => fetchMock.mock.calls.filter(([request]) => request.method === "GET").length;

    // The worker finishes while the list is polled: the next poll shows "ready".
    await waitFor(() => {
      expect(listCalls()).toBe(1);
    });
    status = "ready";
    await waitFor(
      () => {
        expect(result.current.data?.pages[0]?.items[0]?.processing_status).toBe("ready");
      },
      { timeout: PROCESSING_REFETCH_MS + 2000 },
    );
    const callsWhenReady = listCalls();

    // Nothing left to wait for: no further requests.
    await new Promise((resolve) => setTimeout(resolve, PROCESSING_REFETCH_MS + 500));
    expect(listCalls()).toBe(callsWhenReady);
  });
});
