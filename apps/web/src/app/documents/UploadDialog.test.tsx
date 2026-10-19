import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { toast } from "sonner";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { FolderRead } from "@/lib/api/types";
import { putWithProgress } from "@/lib/putWithProgress";
import { renderRoute, stubApi, TEST_ME } from "@/test/renderRoute";

vi.mock("@/lib/putWithProgress", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/putWithProgress")>()),
  putWithProgress: vi.fn(),
}));
const put = vi.mocked(putWithProgress);

const BASE = "/api/v1/app/tenants/00000000-0000-4000-8000-00000000000a";

function folder(overrides: Partial<FolderRead> = {}): FolderRead {
  return {
    id: "laser",
    space_id: "handbuecher",
    parent_id: null,
    name: "Laser",
    path: "Laser",
    sort_order: 0,
    default_access_level: "customer",
    default_doc_type: "operating_manual",
    default_language: "de",
    created_at: "2026-10-19T10:00:00Z",
    updated_at: "2026-10-19T10:00:00Z",
    ...overrides,
  };
}

// Waiting for a chain of async work (file check, upload steps, list reload, closing): generous under a busy CI.
const SLOW = { timeout: 5000 };

const pdf = (name: string) => new File([`%PDF-1.7 ${name}`], name, { type: "application/pdf" });

// The library with one folder, plus upload and create answers; `duplicateOf` marks every new document as a duplicate.
function stubUploadPage(laser: FolderRead, duplicateOf: string | null = null) {
  return stubApi({
    [`GET ${BASE}/spaces`]: {
      status: 200,
      body: { items: [{ id: "handbuecher", name: "Handbücher", created_at: "" }], next_cursor: null },
    },
    [`GET ${BASE}/folders`]: { status: 200, body: { items: [laser], next_cursor: null } },
    [`GET ${BASE}/documents`]: { status: 200, body: { items: [], next_cursor: null } },
    [`POST ${BASE}/uploads`]: {
      status: 201,
      body: { upload_id: "u-1", upload_url: "https://s3.test/u-1", expires_at: "" },
    },
    [`POST ${BASE}/documents`]: { status: 201, body: { id: "new", duplicate_of_document_id: duplicateOf } },
  });
}

async function openUpload(files: File[]) {
  renderRoute("/documents?space_id=handbuecher&folder_id=laser", TEST_ME);
  // The button appears once spaces, folders and the selected folder are loaded.
  fireEvent.click(await screen.findByRole("button", { name: "Hochladen" }, SLOW));
  const dialog = await screen.findByRole("dialog", { name: "Dokumente hochladen in „Laser“" }, SLOW);
  fireEvent.change(within(dialog).getByLabelText("Dateien auswählen"), { target: { files } });
  return dialog;
}

function documentRequests(fetchMock: ReturnType<typeof stubApi>, method: string) {
  return fetchMock.mock.calls.filter(([request]) => request.method === method && request.url.includes("/documents"));
}

beforeEach(() => {
  put.mockReset();
  put.mockResolvedValue(undefined);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// Each test runs a whole page plus an upload chain; under a busy CI that can take longer than Vitest's 5 s default.
describe("UploadDialog", { timeout: 15_000 }, () => {
  it("starts from the folder's defaults and lists rejected files with the reason", async () => {
    stubUploadPage(folder());

    const dialog = await openUpload([pdf("Betriebsanleitung_Laser.pdf"), new File(["Hallo"], "notiz.txt")]);

    expect(await within(dialog).findByLabelText("Titel für Betriebsanleitung_Laser.pdf", {}, SLOW)).toHaveValue(
      "Betriebsanleitung Laser",
    );
    expect(within(dialog).getByText("Keine PDF-Datei – wird nicht hochgeladen.")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Dokumenttyp")).toHaveValue("operating_manual");
    expect(within(dialog).getByLabelText("Sprache")).toHaveValue("de");
    expect(within(dialog).getByLabelText("Sichtbarkeit")).toHaveValue("customer");
    expect(within(dialog).getByRole("button", { name: "1 Dokument hochladen" })).toBeEnabled();
  });

  it("asks for a type and a language when the folder has none, and sends nothing", async () => {
    const fetchMock = stubUploadPage(folder({ default_doc_type: null, default_language: null }));
    const dialog = await openUpload([pdf("Anleitung.pdf")]);

    fireEvent.click(await within(dialog).findByRole("button", { name: "1 Dokument hochladen" }, SLOW));

    expect(within(dialog).getByText("Bitte wählen Sie einen Dokumenttyp.")).toBeInTheDocument();
    expect(within(dialog).getByText("Bitte wählen Sie eine Sprache.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([request]) => request.method === "POST")).toBe(false);
  });

  it("uploads, closes and reports when everything worked", async () => {
    const fetchMock = stubUploadPage(folder());
    const success = vi.spyOn(toast, "success");
    const dialog = await openUpload([pdf("A.pdf"), pdf("B.pdf")]);

    fireEvent.click(await within(dialog).findByRole("button", { name: "2 Dokumente hochladen" }, SLOW));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    }, SLOW);
    expect(success).toHaveBeenCalledWith("2 Dokumente hochgeladen.");
    expect(documentRequests(fetchMock, "POST")).toHaveLength(2);
    // The list is loaded again once the upload is done.
    expect(documentRequests(fetchMock, "GET").length).toBeGreaterThan(1);
  });

  it("stays open and links the existing document for a duplicate", async () => {
    stubUploadPage(folder(), "existing-doc");
    const dialog = await openUpload([pdf("A.pdf")]);

    fireEvent.click(await within(dialog).findByRole("button", { name: "1 Dokument hochladen" }, SLOW));

    expect(await within(dialog).findByText("Die gleiche Datei gibt es schon.", {}, SLOW)).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: "Vorhandenes Dokument öffnen" })).toHaveAttribute(
      "href",
      "/documents/existing-doc",
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("cannot be closed while files are on their way", async () => {
    stubUploadPage(folder());
    let finishPut: () => void = () => undefined;
    put.mockImplementation(() => new Promise<void>((resolve) => (finishPut = resolve)));
    const dialog = await openUpload([pdf("A.pdf")]);

    fireEvent.click(await within(dialog).findByRole("button", { name: "1 Dokument hochladen" }, SLOW));
    expect(
      await within(dialog).findByText("Bitte warten Sie, bis alle Dateien hochgeladen sind.", {}, SLOW),
    ).toBeInTheDocument();
    fireEvent.keyDown(dialog, { key: "Escape" });

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(
      within(dialog)
        .getAllByRole("button", { name: "Schließen" })
        .some((button) => button.hasAttribute("disabled")),
    ).toBe(true);
    // Let the PUT finish only once it has really started: the hint shows already while the file is checked.
    await waitFor(() => {
      expect(put).toHaveBeenCalled();
    }, SLOW);
    finishPut();
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    }, SLOW);
  });
});
