import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import i18n from "@/i18n";
import { createQueryClient } from "@/lib/api/queryClient";
import { putWithProgress, UploadFailedError } from "@/lib/putWithProgress";
import { stubApi } from "@/test/renderRoute";

import { type UploadValues, useUploadQueue } from "./useUploadQueue";

// The PUT to object storage is not the API: replaced here, so each test decides how the store answers.
vi.mock("@/lib/putWithProgress", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/putWithProgress")>()),
  putWithProgress: vi.fn(),
}));
const put = vi.mocked(putWithProgress);

const TENANT_ID = "00000000-0000-4000-8000-00000000000a";
const VALUES: UploadValues = { folderId: "f-1", docType: "datasheet", language: "de", accessLevel: "customer" };
// errors.upload_incomplete in de.json: the API's code turned into the German text, as everywhere else.
const UPLOAD_INCOMPLETE_TEXT = i18n.t("errors.upload_incomplete");
const UPLOADS = `POST /api/v1/app/tenants/${TENANT_ID}/uploads`;
const DOCUMENTS = `POST /api/v1/app/tenants/${TENANT_ID}/documents`;

let queryClient = createQueryClient();
function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

function job(name: string) {
  return {
    key: name,
    file: new File([`%PDF-1.7 ${name}`], `${name}.pdf`, { type: "application/pdf" }),
    title: ` ${name} `,
  };
}

// Every upload gets its own URL; every document echoes its title.
function stubUploadApi() {
  let uploads = 0;
  return stubApi({
    [UPLOADS]: () => {
      uploads += 1;
      return {
        status: 201,
        body: { upload_id: `u-${String(uploads)}`, upload_url: `https://s3.test/u-${String(uploads)}`, expires_at: "" },
      };
    },
    [DOCUMENTS]: () => ({ status: 201, body: { id: "d", duplicate_of_document_id: null } }),
  });
}

beforeEach(() => {
  queryClient = createQueryClient();
  put.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useUploadQueue", () => {
  it("hashes, creates the upload, PUTs the file and creates the document with the shared values", async () => {
    const fetchMock = stubUploadApi();
    put.mockResolvedValue(undefined);
    const { result } = renderHook(() => useUploadQueue(TENANT_ID), { wrapper });

    const datasheet = job("Datenblatt");
    const outcomes = await act(() => result.current.start([datasheet], VALUES));

    expect(outcomes.map((outcome) => outcome.name)).toEqual(["done"]);
    const [upload, document] = fetchMock.mock.calls.map(([request]) => request);
    expect(await upload?.json()).toEqual({
      file_name: "Datenblatt.pdf",
      size_bytes: datasheet.file.size,
      sha256_hex: expect.stringMatching(/^[0-9a-f]{64}$/) as string,
      content_type: "application/pdf",
    });
    expect(put).toHaveBeenCalledWith(
      "https://s3.test/u-1",
      expect.any(File),
      expect.objectContaining({ contentType: "application/pdf" }),
    );
    expect(await document?.json()).toEqual({
      upload_id: "u-1",
      folder_id: "f-1",
      title: "Datenblatt",
      doc_type: "datasheet",
      language: "de",
      access_level: "customer",
    });
    expect(result.current.jobs[0]?.phase.name).toBe("done");
  });

  it("uploads at most three files at a time", async () => {
    stubUploadApi();
    const pending: (() => void)[] = [];
    put.mockImplementation(() => new Promise<void>((resolve) => pending.push(resolve)));
    const { result } = renderHook(() => useUploadQueue(TENANT_ID), { wrapper });

    const running = act(() => result.current.start(["a", "b", "c", "d", "e"].map(job), VALUES));

    await waitFor(() => {
      expect(put).toHaveBeenCalledTimes(3);
    });
    expect(result.current.jobs.filter((entry) => entry.phase.name === "waiting")).toHaveLength(2);
    expect(result.current.isBusy).toBe(true);

    // Each finished upload lets the next waiting file start: release the five one after another.
    for (let released = 0; released < 5; released += 1) {
      await waitFor(() => {
        expect(pending.length).toBeGreaterThan(0);
      });
      pending.shift()?.();
    }
    await running;
    expect(put).toHaveBeenCalledTimes(5);
    expect(result.current.isBusy).toBe(false);
  });

  it("reports a store failure and uploads only the failed file again", async () => {
    stubUploadApi();
    // Both files run at the same time, so the store fails by file name, not by call order.
    put.mockImplementation((_url, file) =>
      file instanceof File && file.name === "broken.pdf"
        ? Promise.reject(new UploadFailedError(403))
        : Promise.resolve(),
    );
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useUploadQueue(TENANT_ID), { wrapper });

    const first = await act(() => result.current.start([job("ok"), job("broken")], VALUES));

    expect(first.map((outcome) => outcome.name).sort()).toEqual(["done", "failed"]);
    expect(result.current.jobs.find((entry) => entry.key === "broken")?.phase).toEqual({
      name: "failed",
      message: "Die Datei konnte nicht gespeichert werden. Bitte versuchen Sie es erneut.",
    });
    expect(invalidate).toHaveBeenCalledTimes(1);

    put.mockImplementation(() => Promise.resolve());
    const retried = await act(() => result.current.retryFailed());

    expect(retried.map((outcome) => outcome.name)).toEqual(["done"]);
    expect(put).toHaveBeenCalledTimes(3);
    expect(result.current.jobs.every((entry) => entry.phase.name === "done")).toBe(true);
  });

  it("shows the API's message when the server refuses the document", async () => {
    stubApi({
      [UPLOADS]: { status: 201, body: { upload_id: "u-1", upload_url: "https://s3.test/u-1", expires_at: "" } },
      [DOCUMENTS]: { status: 409, body: { error: { code: "upload_incomplete", message: "", details: {} } } },
    });
    put.mockResolvedValue(undefined);
    const { result } = renderHook(() => useUploadQueue(TENANT_ID), { wrapper });

    await act(() => result.current.start([job("x")], VALUES));

    expect(result.current.jobs[0]?.phase).toEqual({ name: "failed", message: UPLOAD_INCOMPLETE_TEXT });
  });
});
