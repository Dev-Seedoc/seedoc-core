import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ProductRead, SpaceRead } from "@/lib/api/types";
import { apiError, type FakeAnswer, renderRoute, stubApi, TEST_ME } from "@/test/renderRoute";

const TENANT_ID = "00000000-0000-4000-8000-00000000000a";
const BASE = `/api/v1/app/tenants/${TENANT_ID}`;
const PRODUCTS = `GET ${BASE}/products`;
const CREATE = `POST ${BASE}/products`;
const SPACES = `GET ${BASE}/spaces`;

const HANDBUECHER: SpaceRead = { id: "handbuecher", name: "Handbücher", created_at: "2026-10-13T10:00:00Z" };

function product(id: string, name: string, fields: Partial<ProductRead> = {}): ProductRead {
  return {
    id,
    name,
    space_id: null,
    required_languages: ["de"],
    document_count: 0,
    latest_release_no: null,
    archived_at: null,
    created_at: "2026-10-20T10:00:00Z",
    updated_at: "2026-10-20T10:00:00Z",
    ...fields,
  };
}

function page<T>(items: T[]) {
  return { status: 200, body: { items, next_cursor: null } };
}

function stub(products: ProductRead[], extra: Record<string, FakeAnswer> = {}) {
  return stubApi({ [PRODUCTS]: page(products), [SPACES]: page([HANDBUECHER]), ...extra });
}

async function openCreateDialog() {
  fireEvent.click(await screen.findByRole("button", { name: "Produkt anlegen" }));
  return screen.findByRole("dialog", { name: "Produkt anlegen" });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ProductsPage", () => {
  it("lists the products with space, languages, document count and latest release", async () => {
    stub([
      product("laser", "Laser 3030", {
        space_id: "handbuecher",
        required_languages: ["en", "de"],
        document_count: 4,
        latest_release_no: 2,
      }),
      product("presse", "Presse P1"),
    ]);
    renderRoute("/products", TEST_ME);

    const laser = (await screen.findByRole("link", { name: "Laser 3030" })).closest("tr");
    expect(laser).not.toBeNull();
    // Space names come from their own request.
    await within(laser as HTMLElement).findByText("Handbücher");
    const cells = within(laser as HTMLElement)
      .getAllByRole("cell")
      .map((cell) => cell.textContent);
    expect(cells).toEqual(["Laser 3030", "Handbücher", "Englisch, Deutsch", "4", "Freigabe 2"]);
    expect(screen.getByRole("link", { name: "Laser 3030" })).toHaveAttribute("href", "/products/laser");
    const presse = screen.getByRole("link", { name: "Presse P1" }).closest("tr") as HTMLElement;
    expect(within(presse).getAllByRole("cell")[1]).toHaveTextContent("—");
    expect(within(presse).getAllByRole("cell")[4]).toHaveTextContent("Noch keine");
  });

  it("shows an empty state that offers to create the first product", async () => {
    stub([]);
    renderRoute("/products", TEST_ME);

    expect(await screen.findByRole("heading", { name: "Noch keine Produkte" })).toBeInTheDocument();
    expect(await openCreateDialog()).toBeInTheDocument();
  });

  it("offers a retry when the list cannot be loaded", async () => {
    const fetchMock = stubApi({ [PRODUCTS]: apiError(500, "internal_error"), [SPACES]: page([]) });
    renderRoute("/products", TEST_ME);

    fireEvent.click(await screen.findByRole("button", { name: "Wiederholen" }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.filter(([request]) => request.method === "GET" && request.url.endsWith("/products")),
      ).toHaveLength(2);
    });
  });

  it("creates a product with space and languages in order and opens it", async () => {
    let body: unknown;
    stub([product("presse", "Presse P1")], {
      [CREATE]: (request) => {
        body = request.clone().json();
        return { status: 201, body: product("neu", "Laser 4040") };
      },
    });
    const router = renderRoute("/products", TEST_ME);
    const dialog = await openCreateDialog();

    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "  Laser 4040 " } });
    await within(dialog).findByRole("option", { name: "Handbücher" });
    fireEvent.change(within(dialog).getByLabelText("Bereich"), { target: { value: "handbuecher" } });
    const languages = within(dialog).getByRole("list", { name: "Pflichtsprachen" });
    expect(within(languages).getByRole("button", { name: "Deutsch entfernen" })).toBeDisabled(); // at least one
    fireEvent.change(within(dialog).getByLabelText("Sprache hinzufügen …"), { target: { value: "fr" } });
    fireEvent.change(within(dialog).getByLabelText("Sprache hinzufügen …"), { target: { value: "en" } });
    fireEvent.click(within(languages).getByRole("button", { name: "Französisch entfernen" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Anlegen" }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/products/neu");
    });
    expect(await body).toEqual({ name: "Laser 4040", space_id: "handbuecher", required_languages: ["de", "en"] });
  });

  it("asks for a name before sending anything", async () => {
    const fetchMock = stub([product("presse", "Presse P1")]);
    renderRoute("/products", TEST_ME);
    const dialog = await openCreateDialog();

    fireEvent.click(within(dialog).getByRole("button", { name: "Anlegen" }));

    expect(await within(dialog).findByText("Bitte geben Sie einen Namen ein.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([request]) => request.method === "POST")).toBe(false);
  });

  it("shows a failed save inside the dialog", async () => {
    stub([product("presse", "Presse P1")], { [CREATE]: apiError(404, "not_found") });
    renderRoute("/products", TEST_ME);
    const dialog = await openCreateDialog();

    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "Laser" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Anlegen" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Der angeforderte Eintrag wurde nicht gefunden.",
    );
    expect(screen.getByRole("dialog", { name: "Produkt anlegen" })).toBeInTheDocument();
  });
});
