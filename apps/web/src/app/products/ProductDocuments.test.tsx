import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DocumentListItem, ProductRead } from "@/lib/api/types";
import { apiError, type FakeAnswer, renderRoute, stubApi, TEST_ME } from "@/test/renderRoute";

const TENANT_ID = "00000000-0000-4000-8000-00000000000a";
const BASE = `/api/v1/app/tenants/${TENANT_ID}`;
const SET_URL = `${BASE}/products/laser/documents`;
const LIBRARY = `GET ${BASE}/documents`;

const LASER: ProductRead = {
  id: "laser",
  name: "Laser 3030",
  space_id: "handbuecher",
  required_languages: ["de"],
  document_count: 2,
  latest_release_no: null,
  archived_at: null,
  created_at: "2026-10-20T10:00:00Z",
  updated_at: "2026-10-20T10:00:00Z",
};

function document(id: string, title: string, fields: Partial<DocumentListItem> = {}): DocumentListItem {
  return {
    id,
    title,
    doc_type: "operating_manual",
    language: "de",
    access_level: "customer",
    folder_id: "laser-folder",
    folder_path: "Handbücher/Laser",
    current_version_no: 1,
    processing_status: "ready",
    group_id: `group-${id}`,
    machine_id: null,
    trashed_at: null,
    updated_at: "2026-10-20T10:00:00Z",
    ...fields,
  };
}

const ANLEITUNG = document("anleitung", "Betriebsanleitung");
const WARTUNG = document("wartung", "Wartungsplan", { doc_type: "maintenance_manual", language: "en" });
const SCHALTPLAN = document("schaltplan", "Schaltplan", { folder_path: "Zertifikate/CE" });
const PRUEFPROTOKOLL = document("pruef", "Prüfprotokoll", { machine_id: "machine-1" });

function page<T>(items: T[]) {
  return { status: 200, body: { items, next_cursor: null } };
}

function stub(set: DocumentListItem[], extra: Record<string, FakeAnswer> = {}) {
  return stubApi({
    [`GET ${BASE}/products/laser`]: { status: 200, body: LASER },
    [`GET ${BASE}/spaces`]: page([]),
    [`GET ${SET_URL}`]: page(set),
    [LIBRARY]: page([ANLEITUNG, PRUEFPROTOKOLL, SCHALTPLAN, WARTUNG]),
    ...extra,
  });
}

async function openPicker() {
  fireEvent.click(await screen.findByRole("button", { name: "Dokumente auswählen" }));
  const dialog = await screen.findByRole("dialog", { name: "Dokumente für „Laser 3030“" });
  await within(dialog).findByRole("list", { name: "Dokumente der Bibliothek" });
  return dialog;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ProductDocuments", () => {
  it("lists the set with links to the documents", async () => {
    stub([ANLEITUNG, WARTUNG]);
    renderRoute("/products/laser", TEST_ME);

    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(
      rows.map((row) =>
        within(row)
          .getAllByRole("cell")
          .slice(0, 4)
          .map((cell) => cell.textContent),
      ),
    ).toEqual([
      ["Betriebsanleitung", "Betriebsanleitung", "Deutsch", "Handbücher/Laser"],
      ["Wartungsplan", "Wartungsanleitung", "Englisch", "Handbücher/Laser"],
    ]);
    expect(within(table).getByRole("link", { name: "Wartungsplan" })).toHaveAttribute("href", "/documents/wartung");
  });

  it("removes one document by sending the rest of the set", async () => {
    const fetchMock = stub([ANLEITUNG, WARTUNG], { [`PUT ${SET_URL}`]: page([WARTUNG]) });
    renderRoute("/products/laser", TEST_ME);

    fireEvent.click(await screen.findByRole("button", { name: "„Betriebsanleitung“ aus dem Produkt entfernen" }));

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([request]) => request.method === "PUT")).toBe(true);
    });
    const put = fetchMock.mock.calls.find(([request]) => request.method === "PUT")?.[0];
    expect(await put?.json()).toEqual({ document_ids: ["wartung"] });
  });

  it("chooses documents: the set is preselected, machine-specific ones are locked, saving sends the whole set", async () => {
    const fetchMock = stub([ANLEITUNG, WARTUNG], { [`PUT ${SET_URL}`]: page([ANLEITUNG, SCHALTPLAN]) });
    renderRoute("/products/laser", TEST_ME);
    const dialog = await openPicker();

    expect(within(dialog).getByLabelText(/^Betriebsanleitung/)).toBeChecked();
    expect(within(dialog).getByLabelText(/^Wartungsplan/)).toBeChecked();
    expect(within(dialog).getByLabelText(/^Prüfprotokoll/)).toBeDisabled();
    expect(within(dialog).getByText("2 Dokumente ausgewählt")).toBeInTheDocument();

    fireEvent.click(within(dialog).getByLabelText(/^Wartungsplan/));
    fireEvent.click(within(dialog).getByLabelText(/^Schaltplan/));
    fireEvent.click(within(dialog).getByRole("button", { name: "Speichern" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    const put = fetchMock.mock.calls.find(([request]) => request.method === "PUT")?.[0];
    expect(await put?.json()).toEqual({ document_ids: ["anleitung", "schaltplan"] });
  });

  it("searches in the product's space first and can widen to every space", async () => {
    const fetchMock = stub([ANLEITUNG]);
    renderRoute("/products/laser", TEST_ME);
    const dialog = await openPicker();
    const libraryQueries = () =>
      fetchMock.mock.calls
        .map(([request]) => new URL(request.url))
        .filter((url) => url.pathname === `${BASE}/documents`)
        .map((url) => url.searchParams);

    expect(libraryQueries()[0]?.get("space_id")).toBe("handbuecher");

    fireEvent.click(within(dialog).getByLabelText("Nur Dokumente aus dem Bereich des Produkts"));
    fireEvent.change(within(dialog).getByLabelText("Titel suchen"), { target: { value: "Plan" } });

    await waitFor(() => {
      const last = libraryQueries().at(-1);
      expect([last?.get("space_id"), last?.get("q")]).toEqual([null, "Plan"]);
    });
  });

  it("explains a refused set inside the picker", async () => {
    stub([ANLEITUNG], { [`PUT ${SET_URL}`]: apiError(409, "conflict") });
    renderRoute("/products/laser", TEST_ME);
    const dialog = await openPicker();

    fireEvent.click(within(dialog).getByLabelText(/^Schaltplan/));
    fireEvent.click(within(dialog).getByRole("button", { name: "Speichern" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Ein ausgewähltes Dokument liegt inzwischen im Papierkorb.",
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("offers the picker from the empty state", async () => {
    stub([]);
    renderRoute("/products/laser", TEST_ME);

    expect(await screen.findByRole("heading", { name: "Noch keine Dokumente" })).toBeInTheDocument();
    expect(await openPicker()).toBeInTheDocument();
  });
});
