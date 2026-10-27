import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DocumentListItem, ProductRead, ProductReleaseRead } from "@/lib/api/types";
import { apiError, type FakeAnswer, renderRoute, stubApi, TEST_ME } from "@/test/renderRoute";

const TENANT_ID = "00000000-0000-4000-8000-00000000000a";
const PRODUCT_URL = `/api/v1/app/tenants/${TENANT_ID}/products/laser`;
const RELEASES = `${PRODUCT_URL}/releases`;

const LASER: ProductRead = {
  id: "laser",
  name: "Laser 3030",
  space_id: null,
  required_languages: ["de"],
  document_count: 2,
  latest_release_no: 2,
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
    folder_id: "f",
    folder_path: "Handbücher/Laser",
    current_version_no: 1,
    processing_status: "ready",
    group_id: `g-${id}`,
    machine_id: null,
    trashed_at: null,
    updated_at: "2026-10-20T10:00:00Z",
    ...fields,
  };
}

const RELEASE_3: ProductReleaseRead = {
  id: "r-3",
  release_no: 3,
  change_note: "Neue Wartung",
  item_count: 2,
  created_at: "2026-10-27T09:00:00Z",
  created_by_name: "Olga Owner",
};

function page<T>(items: T[]) {
  return { status: 200, body: { items, next_cursor: null } };
}

function stub(extra: Record<string, FakeAnswer>) {
  return stubApi({
    [`GET ${PRODUCT_URL}`]: { status: 200, body: LASER },
    [`GET /api/v1/app/tenants/${TENANT_ID}/spaces`]: page([]),
    [`GET ${RELEASES}`]: page([]),
    [`GET ${PRODUCT_URL}/documents`]: page([
      document("anleitung", "Betriebsanleitung", { processing_status: "processing" }),
      document("wartung", "Wartungsplan", { processing_status: "failed" }),
    ]),
    ...extra,
  });
}

async function openDialog() {
  fireEvent.click(await screen.findByRole("button", { name: "Freigeben" }));
  return screen.findByRole("dialog", { name: "„Laser 3030“ freigeben" });
}

function posts(fetchMock: ReturnType<typeof stubApi>) {
  return fetchMock.mock.calls.filter(([request]) => request.method === "POST").map(([request]) => request);
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("CreateReleaseDialog", () => {
  it("creates a release with the trimmed change note and reloads the list and the product", async () => {
    const fetchMock = stub({ [`POST ${RELEASES}`]: { status: 201, body: RELEASE_3 } });
    renderRoute("/products/laser?tab=releases", TEST_ME);
    const dialog = await openDialog();

    expect(dialog).toHaveTextContent("Die aktuellen Versionen der 2 Dokumente werden eingefroren.");
    fireEvent.change(within(dialog).getByLabelText("Änderungshinweis (optional)"), {
      target: { value: "  Neue Wartung " },
    });
    expect(within(dialog).getByText("12 / 2000 Zeichen")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Freigeben" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(await posts(fetchMock)[0]?.json()).toEqual({ change_note: "Neue Wartung" });
    const reloaded = (path: string) =>
      fetchMock.mock.calls.filter(([request]) => request.method === "GET" && new URL(request.url).pathname === path);
    await waitFor(() => {
      expect(reloaded(RELEASES)).toHaveLength(2);
    });
    expect(reloaded(PRODUCT_URL)).toHaveLength(2);
  });

  it("sends no change note when it is left blank", async () => {
    const fetchMock = stub({ [`POST ${RELEASES}`]: { status: 201, body: RELEASE_3 } });
    renderRoute("/products/laser?tab=releases", TEST_ME);
    const dialog = await openDialog();

    fireEvent.change(within(dialog).getByLabelText("Änderungshinweis (optional)"), { target: { value: "   " } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Freigeben" }));

    await waitFor(() => {
      expect(posts(fetchMock)).toHaveLength(1);
    });
    expect(await posts(fetchMock)[0]?.json()).toEqual({});
  });

  it("blocks a change note over 2,000 characters", async () => {
    stub({});
    renderRoute("/products/laser?tab=releases", TEST_ME);
    const dialog = await openDialog();

    fireEvent.change(within(dialog).getByLabelText("Änderungshinweis (optional)"), {
      target: { value: "x".repeat(2001) },
    });

    expect(within(dialog).getByLabelText("Änderungshinweis (optional)")).toHaveAttribute("aria-invalid", "true");
    expect(within(dialog).getByRole("button", { name: "Freigeben" })).toBeDisabled();
  });

  it("lists the documents that are not ready, by title with a link and their state", async () => {
    stub({
      [`POST ${RELEASES}`]: apiError(409, "publish_blocked", {
        problems: [
          { code: "version_not_ready", document_id: "anleitung" },
          { code: "version_not_ready", document_id: "wartung" },
        ],
      }),
    });
    renderRoute("/products/laser?tab=releases", TEST_ME);
    const dialog = await openDialog();

    fireEvent.click(within(dialog).getByRole("button", { name: "Freigeben" }));

    const alert = await within(dialog).findByRole("alert");
    expect(alert).toHaveTextContent("Die Freigabe ist nicht möglich.");
    expect(alert).toHaveTextContent("Diese Dokumente sind noch nicht bereit");
    const items = within(alert).getAllByRole("listitem");
    expect(items.map((item) => item.textContent)).toEqual([
      "BetriebsanleitungIn Bearbeitung",
      "WartungsplanFehlgeschlagen",
    ]);
    expect(within(alert).getByRole("link", { name: "Wartungsplan" })).toHaveAttribute("href", "/documents/wartung");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("explains a product without documents", async () => {
    stub({ [`POST ${RELEASES}`]: apiError(409, "publish_blocked", { problems: [{ code: "no_items" }] }) });
    renderRoute("/products/laser?tab=releases", TEST_ME);
    const dialog = await openDialog();

    fireEvent.click(within(dialog).getByRole("button", { name: "Freigeben" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Das Produkt hat noch keine Dokumente.");
  });

  it("shows any other failure as a general message", async () => {
    stub({ [`POST ${RELEASES}`]: apiError(500, "internal_error") });
    renderRoute("/products/laser?tab=releases", TEST_ME);
    const dialog = await openDialog();

    fireEvent.click(within(dialog).getByRole("button", { name: "Freigeben" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Ein unerwarteter Fehler ist aufgetreten.");
  });
});
