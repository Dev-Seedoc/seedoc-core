import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { toast } from "sonner";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DocumentRead, DocumentVersionRead } from "@/lib/api/types";
import { putWithProgress } from "@/lib/putWithProgress";
import { startDownload } from "@/lib/startDownload";
import { apiError, type FakeAnswer, renderRoute, stubApi, TEST_ME } from "@/test/renderRoute";

vi.mock("@/lib/startDownload", () => ({ startDownload: vi.fn() }));
vi.mock("@/lib/putWithProgress", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/putWithProgress")>()),
  putWithProgress: vi.fn(() => Promise.resolve()),
}));

const BASE = "/api/v1/app/tenants/00000000-0000-4000-8000-00000000000a";
const DOC_ID = "00000000-0000-4000-8000-0000000000d1";

function documentRead(overrides: Partial<DocumentRead> = {}): DocumentRead {
  return {
    id: DOC_ID,
    title: "Betriebsanleitung Laser",
    doc_type: "operating_manual",
    language: "de",
    access_level: "customer",
    folder_id: "laser",
    folder_path: "Handbücher/Laser",
    current_version_no: 2,
    processing_status: "ready",
    group_id: "g-1",
    machine_id: null,
    trashed_at: null,
    updated_at: "2026-10-19T08:30:00Z",
    versions_count: 2,
    language_variants: [],
    released_in_count: 0,
    ...overrides,
  };
}

function stubDocument(answer: FakeAnswer, extra: Record<string, FakeAnswer> = {}) {
  return stubApi({
    [`GET ${BASE}/documents/${DOC_ID}`]: answer,
    [`GET ${BASE}/documents/${DOC_ID}/versions`]: { status: 200, body: { items: [], next_cursor: null } },
    ...extra,
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("DocumentDetailPage", () => {
  it("shows the document with its facts and a breadcrumb back to the documents", async () => {
    stubDocument({ status: 200, body: documentRead() });
    renderRoute(`/documents/${DOC_ID}`, TEST_ME);

    expect(await screen.findByRole("heading", { level: 1, name: "Betriebsanleitung Laser" })).toBeInTheDocument();
    expect(screen.getByText("Bereit")).toBeInTheDocument();
    expect(screen.getByText("Handbücher/Laser · V2")).toBeInTheDocument();
    const facts = within(screen.getByRole("region", { name: "Angaben zum Dokument" }));
    expect(facts.getByText("Betriebsanleitung")).toBeInTheDocument();
    expect(facts.getByText("Deutsch")).toBeInTheDocument();
    expect(facts.getByText("Nur Kunden")).toBeInTheDocument();
    const breadcrumbs = within(screen.getByRole("navigation", { name: "Seitenpfad" }));
    expect(breadcrumbs.getByRole("link", { name: "Dokumente" })).toHaveAttribute("href", "/documents");
    expect(breadcrumbs.getByText("Dokument")).toHaveAttribute("aria-current", "page");
  });

  it("explains an unknown or malformed document id", async () => {
    stubDocument(apiError(404, "not_found"));
    renderRoute(`/documents/${DOC_ID}`, TEST_ME);

    expect(await screen.findByRole("heading", { name: "Dokument nicht gefunden" })).toBeInTheDocument();
  });

  it("offers to restore a trashed document and then shows it as normal", async () => {
    let trashedAt: string | null = "2026-10-18T09:00:00Z";
    stubDocument(() => ({ status: 200, body: documentRead({ trashed_at: trashedAt }) }), {
      [`POST ${BASE}/documents/${DOC_ID}/restore`]: () => {
        trashedAt = null;
        return { status: 200, body: documentRead() };
      },
    });
    renderRoute(`/documents/${DOC_ID}`, TEST_ME);

    const banner = await screen.findByRole("status");
    expect(banner).toHaveTextContent(/liegt seit 18\.10\.2026, \d{2}:00 im Papierkorb/);
    fireEvent.click(within(banner).getByRole("button", { name: "Wiederherstellen" }));

    await waitFor(() => {
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });
    expect(screen.queryByText("Im Papierkorb")).not.toBeInTheDocument();
  });

  it("goes back to /documents when opened directly", async () => {
    stubDocument({ status: 200, body: documentRead() });
    const router = renderRoute(`/documents/${DOC_ID}`, TEST_ME);

    fireEvent.click(await screen.findByRole("link", { name: "Zurück zu den Dokumenten" }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/documents");
    });
  });
});

describe("DocumentDetailPage – details form", () => {
  const PATCH = `PATCH ${BASE}/documents/${DOC_ID}`;

  async function openForm() {
    renderRoute(`/documents/${DOC_ID}`, TEST_ME);
    return within(await screen.findByRole("region", { name: "Angaben bearbeiten" }));
  }

  it("saves only the fields that changed", async () => {
    let saved = documentRead();
    const fetchMock = stubDocument(() => ({ status: 200, body: saved }), {
      [PATCH]: () => {
        saved = documentRead({ title: "Laser – Betriebsanleitung", access_level: "internal" });
        return { status: 200, body: saved };
      },
    });
    const success = vi.spyOn(toast, "success");
    const form = await openForm();
    expect(form.getByRole("button", { name: "Speichern" })).toBeDisabled();

    fireEvent.change(form.getByLabelText("Titel"), { target: { value: "  Laser – Betriebsanleitung " } });
    fireEvent.change(form.getByLabelText("Sichtbarkeit"), { target: { value: "internal" } });
    fireEvent.click(form.getByRole("button", { name: "Speichern" }));

    await waitFor(() => {
      expect(success).toHaveBeenCalledWith("Änderungen gespeichert.");
    });
    const patch = fetchMock.mock.calls.find(([request]) => request.method === "PATCH")?.[0];
    expect(await patch?.json()).toEqual({ title: "Laser – Betriebsanleitung", access_level: "internal" });
    expect(await screen.findByRole("heading", { level: 1, name: "Laser – Betriebsanleitung" })).toBeInTheDocument();
    expect(form.getByRole("button", { name: "Speichern" })).toBeDisabled();
  });

  it("shows a language taken in the language group under the field and focuses it", async () => {
    stubDocument({ status: 200, body: documentRead() }, { [PATCH]: apiError(409, "conflict", { field: "language" }) });
    const form = await openForm();

    fireEvent.change(form.getByLabelText("Sprache"), { target: { value: "en" } });
    fireEvent.click(form.getByRole("button", { name: "Speichern" }));

    expect(
      await form.findByText("In der Sprachgruppe dieses Dokuments gibt es schon ein Dokument in dieser Sprache."),
    ).toBeInTheDocument();
    expect(form.getByLabelText("Sprache")).toHaveFocus();
    expect(form.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("discards what was changed", async () => {
    stubDocument({ status: 200, body: documentRead() });
    const form = await openForm();

    fireEvent.change(form.getByLabelText("Sprache"), { target: { value: "fr" } });
    fireEvent.change(form.getByLabelText("Titel"), { target: { value: "Etwas anderes" } });
    fireEvent.click(form.getByRole("button", { name: "Verwerfen" }));

    await waitFor(() => {
      expect(form.getByLabelText("Sprache")).toHaveValue("de");
    });
    expect(form.getByLabelText("Titel")).toHaveValue("Betriebsanleitung Laser");
    expect(form.getByRole("button", { name: "Verwerfen" })).toBeDisabled();
  });

  it("is locked while the document is in the trash", async () => {
    stubDocument({ status: 200, body: documentRead({ trashed_at: "2026-10-18T09:00:00Z" }) });
    const form = await openForm();

    expect(form.getByLabelText("Titel")).toBeDisabled();
    expect(form.getByLabelText("Sprache")).toBeDisabled();
    expect(form.getByRole("button", { name: "Speichern" })).toBeDisabled();
  });
});

describe("DocumentDetailPage – versions", () => {
  const VERSIONS = `GET ${BASE}/documents/${DOC_ID}/versions`;

  function version(no: number, overrides: Partial<DocumentVersionRead> = {}): DocumentVersionRead {
    return {
      id: `v-${String(no)}`,
      document_id: DOC_ID,
      version_no: no,
      file_name: `Anleitung_v${String(no)}.pdf`,
      size_bytes: 2048,
      sha256_hex: "ab".repeat(32),
      page_count: 12,
      processing_status: "ready",
      processing_error: null,
      processed_at: "2026-10-19T08:00:00Z",
      is_current: false,
      created_by: null,
      created_at: "2026-10-19T08:00:00Z",
      ...overrides,
    };
  }

  async function versionsSection() {
    return within(await screen.findByRole("region", { name: "Versionen" }));
  }

  it("lists the versions newest first with the current one marked and a failed one explained", async () => {
    stubDocument(
      { status: 200, body: documentRead() },
      {
        [VERSIONS]: {
          status: 200,
          body: {
            items: [
              version(2, {
                is_current: true,
                processing_status: "failed",
                processing_error: "Die PDF-Datei ist beschädigt.",
                page_count: null,
              }),
              version(1),
            ],
            next_cursor: null,
          },
        },
      },
    );
    renderRoute(`/documents/${DOC_ID}`, TEST_ME);
    const section = await versionsSection();

    const [, newest, oldest] = await section.findAllByRole("row");
    expect(within(newest ?? document.body).getByText("Aktuell")).toBeInTheDocument();
    expect(within(newest ?? document.body).getByText("Die PDF-Datei ist beschädigt.")).toBeInTheDocument();
    expect(within(newest ?? document.body).getByText("—")).toBeInTheDocument();
    expect(within(oldest ?? document.body).getByText("2 KB")).toBeInTheDocument();
    expect(within(oldest ?? document.body).queryByText("Aktuell")).not.toBeInTheDocument();
  });

  it("downloads a version through a fresh file link", async () => {
    stubDocument(
      { status: 200, body: documentRead() },
      {
        [VERSIONS]: { status: 200, body: { items: [version(1, { is_current: true })], next_cursor: null } },
        [`GET ${BASE}/documents/${DOC_ID}/versions/v-1/file`]: {
          status: 200,
          body: { url: "https://s3.test/v-1.pdf", expires_at: "" },
        },
      },
    );
    renderRoute(`/documents/${DOC_ID}`, TEST_ME);

    fireEvent.click(await (await versionsSection()).findByRole("button", { name: "Version 1 herunterladen" }));

    await waitFor(() => {
      expect(startDownload).toHaveBeenCalledWith("https://s3.test/v-1.pdf");
    });
  });

  it("uploads a new version and says it is current now", async () => {
    let versions = [version(1, { is_current: true })];
    const fetchMock = stubDocument(
      { status: 200, body: documentRead() },
      {
        [VERSIONS]: () => ({ status: 200, body: { items: versions, next_cursor: null } }),
        [`POST ${BASE}/uploads`]: {
          status: 201,
          body: { upload_id: "u-9", upload_url: "https://s3.test/u-9", expires_at: "" },
        },
        [`POST ${BASE}/documents/${DOC_ID}/versions`]: () => {
          versions = [version(2, { is_current: true, processing_status: "pending" }), version(1)];
          return { status: 201, body: { ...version(2, { is_current: true }), duplicate_of_document_id: null } };
        },
      },
    );
    const success = vi.spyOn(toast, "success");
    renderRoute(`/documents/${DOC_ID}`, TEST_ME);
    const section = await versionsSection();

    fireEvent.change(await section.findByLabelText("Neue Version hochladen"), {
      target: { files: [new File(["%PDF-1.7 v2"], "Anleitung_v2.pdf", { type: "application/pdf" })] },
    });

    await waitFor(() => {
      expect(success).toHaveBeenCalledWith("Version 2 hochgeladen. Sie ist jetzt die aktuelle Version.");
    });
    const create = fetchMock.mock.calls.find(
      ([request]) => request.url.endsWith("/versions") && request.method === "POST",
    )?.[0];
    expect(await create?.json()).toEqual({ upload_id: "u-9" });
    expect(putWithProgress).toHaveBeenCalledWith("https://s3.test/u-9", expect.any(File), expect.anything());
    expect(await section.findByText("Anleitung_v2.pdf")).toBeInTheDocument();
  });

  it("refuses a file that is not a PDF and sends nothing", async () => {
    const fetchMock = stubDocument({ status: 200, body: documentRead() });
    const error = vi.spyOn(toast, "error");
    renderRoute(`/documents/${DOC_ID}`, TEST_ME);
    const section = await versionsSection();

    fireEvent.change(await section.findByLabelText("Neue Version hochladen"), {
      target: { files: [new File(["<html>"], "notiz.pdf", { type: "application/pdf" })] },
    });

    await waitFor(() => {
      expect(error).toHaveBeenCalledWith("Keine PDF-Datei – wird nicht hochgeladen.");
    });
    expect(fetchMock.mock.calls.some(([request]) => request.method === "POST")).toBe(false);
  });

  it("offers no new version for a trashed document", async () => {
    stubDocument({ status: 200, body: documentRead({ trashed_at: "2026-10-18T09:00:00Z" }) });
    renderRoute(`/documents/${DOC_ID}`, TEST_ME);

    expect(await (await versionsSection()).findByLabelText("Neue Version hochladen")).toBeDisabled();
  });
});
