import { fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { LanguageMatrixRead, ProductRead, ProductReleaseDetailRead, ProductReleaseRead } from "@/lib/api/types";
import { type FakeAnswer, renderRoute, stubApi, TEST_ME } from "@/test/renderRoute";

const TENANT_ID = "00000000-0000-4000-8000-00000000000a";
const PRODUCT_URL = `/api/v1/app/tenants/${TENANT_ID}/products/laser`;

const LASER: ProductRead = {
  id: "laser",
  name: "Laser 3030",
  space_id: null,
  required_languages: ["de", "en", "fr"],
  document_count: 3,
  latest_release_no: 2,
  archived_at: null,
  created_at: "2026-10-20T10:00:00Z",
  updated_at: "2026-10-20T10:00:00Z",
};

const MATRIX: LanguageMatrixRead = {
  languages: ["de", "en", "fr"],
  rows: [
    {
      group_id: "g-anleitung",
      title: "Betriebsanleitung",
      doc_type: "operating_manual",
      cells: {
        de: { status: "present", document_id: "anleitung-de", waiver_reason: null },
        en: { status: "present", document_id: "anleitung-en", waiver_reason: null },
        fr: { status: "missing", document_id: null, waiver_reason: null },
      },
    },
    {
      group_id: "g-wartung",
      title: "Wartungsplan",
      doc_type: "maintenance_manual",
      cells: {
        de: { status: "present", document_id: "wartung-de", waiver_reason: null },
        en: { status: "missing", document_id: null, waiver_reason: null },
        fr: { status: "missing", document_id: null, waiver_reason: null },
      },
    },
  ],
};

function release(no: number, fields: Partial<ProductReleaseRead> = {}): ProductReleaseRead {
  return {
    id: `r-${String(no)}`,
    release_no: no,
    change_note: `Ausgabe ${String(no)}`,
    item_count: no,
    created_at: "2026-10-21T08:30:00Z",
    created_by_name: "Erika Editor",
    ...fields,
  };
}

const RELEASE_2: ProductReleaseDetailRead = {
  ...release(2),
  items: [
    {
      id: "i-1",
      document_id: "anleitung-de",
      version_id: "v-1",
      version_no: 3,
      title: "Betriebsanleitung",
      doc_type: "operating_manual",
      language: "de",
      access_level: "customer",
      folder_path: "Handbücher/Laser",
    },
  ],
};

function page<T>(items: T[]) {
  return { status: 200, body: { items, next_cursor: null } };
}

function stub(extra: Record<string, FakeAnswer>) {
  return stubApi({
    [`GET ${PRODUCT_URL}`]: { status: 200, body: LASER },
    [`GET /api/v1/app/tenants/${TENANT_ID}/spaces`]: page([]),
    ...extra,
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ProductLanguages", () => {
  it("shows which language of which document is present or missing", async () => {
    stub({ [`GET ${PRODUCT_URL}/languages`]: { status: 200, body: MATRIX } });
    renderRoute("/products/laser?tab=languages", TEST_ME);

    expect(await screen.findByRole("status")).toHaveTextContent("3 Sprachfassungen fehlen.");
    const table = screen.getByRole("table");
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((header) => header.textContent),
    ).toEqual(["Dokument", "Deutsch", "Englisch", "Französisch"]);
    expect(within(table).getByRole("link", { name: "„Betriebsanleitung“ auf Englisch öffnen" })).toHaveAttribute(
      "href",
      "/documents/anleitung-en",
    );
    expect(within(table).getByRole("img", { name: "„Betriebsanleitung“ fehlt auf Französisch" })).toBeInTheDocument();
    expect(within(table).getAllByRole("img", { name: /^„Wartungsplan“ fehlt/ })).toHaveLength(2);
  });

  it("says so when every language is there", async () => {
    const complete: LanguageMatrixRead = { languages: ["de"], rows: MATRIX.rows.map((row) => ({ ...row })) };
    stub({ [`GET ${PRODUCT_URL}/languages`]: { status: 200, body: complete } });
    renderRoute("/products/laser?tab=languages", TEST_ME);

    expect(await screen.findByRole("status")).toHaveTextContent("Alle Dokumente liegen in allen Pflichtsprachen vor.");
  });
});

describe("ProductReleases", () => {
  it("lists the releases newest first and opens the frozen versions of one", async () => {
    stub({
      [`GET ${PRODUCT_URL}/releases`]: page([release(2), release(1, { change_note: null, created_by_name: null })]),
      [`GET ${PRODUCT_URL}/releases/2`]: { status: 200, body: RELEASE_2 },
    });
    renderRoute("/products/laser?tab=releases", TEST_ME);

    const opener = await screen.findByRole("button", { name: "Freigabe 2" });
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(
      rows.map((row) =>
        within(row)
          .getAllByRole("cell")
          .map((cell) => cell.textContent),
      ),
    ).toEqual([
      ["Freigabe 2", "Ausgabe 2", "2", "21.10.2026, 10:30", "Erika Editor"],
      ["Freigabe 1", "—", "1", "21.10.2026, 10:30", "—"],
    ]);

    fireEvent.click(opener);

    expect(opener).toHaveAttribute("aria-expanded", "true");
    const items = await screen.findByRole("list", { name: "Dokumente der Freigabe 2" });
    expect(within(items).getByRole("listitem")).toHaveTextContent("BetriebsanleitungDeutsch · V3 · Handbücher/Laser");
  });
});
