import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ProductRead, SpaceRead } from "@/lib/api/types";
import { apiError, type FakeAnswer, renderRoute, stubApi, TEST_ME } from "@/test/renderRoute";

const TENANT_ID = "00000000-0000-4000-8000-00000000000a";
const BASE = `/api/v1/app/tenants/${TENANT_ID}`;
const PRODUCT_URL = `${BASE}/products/laser`;

const SPACES: SpaceRead[] = [
  { id: "handbuecher", name: "Handbücher", created_at: "2026-10-13T10:00:00Z" },
  { id: "zertifikate", name: "Zertifikate", created_at: "2026-10-13T10:00:00Z" },
];

const LASER: ProductRead = {
  id: "laser",
  name: "Laser 3030",
  space_id: "handbuecher",
  required_languages: ["de", "en"],
  document_count: 3,
  latest_release_no: 2,
  archived_at: null,
  created_at: "2026-10-20T10:00:00Z",
  updated_at: "2026-10-20T10:00:00Z",
};

function page<T>(items: T[]) {
  return { status: 200, body: { items, next_cursor: null } };
}

function stub(extra: Record<string, FakeAnswer> = {}) {
  return stubApi({
    [`GET ${PRODUCT_URL}`]: { status: 200, body: LASER },
    [`GET ${BASE}/spaces`]: page(SPACES),
    ...extra,
  });
}

async function detailsForm() {
  const section = await screen.findByRole("region", { name: "Angaben zum Produkt" });
  await within(section).findByRole("option", { name: "Zertifikate" });
  return section;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ProductDetailPage", () => {
  it("shows the product, its details and the tabs from the URL", async () => {
    stub();
    const router = renderRoute("/products/laser?tab=languages", TEST_ME);

    expect(await screen.findByRole("heading", { level: 1, name: "Laser 3030" })).toBeInTheDocument();
    expect(screen.getByText("3 Dokumente · Freigabe 2")).toBeInTheDocument();
    const form = await detailsForm();
    expect(within(form).getByLabelText("Name")).toHaveValue("Laser 3030");
    expect(within(form).getByLabelText("Bereich")).toHaveValue("handbuecher");
    const languages = within(form).getByRole("list", { name: "Pflichtsprachen" });
    expect(
      within(languages)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual(["Deutsch", "Englisch"]);
    expect(within(form).getByRole("button", { name: "Speichern" })).toBeDisabled();

    const tabs = screen.getByRole("tablist", { name: "Bereiche des Produkts" });
    expect(within(tabs).getByRole("tab", { name: "Sprachen" })).toHaveAttribute("aria-selected", "true");
    fireEvent.click(within(tabs).getByRole("tab", { name: "Freigaben" }));
    expect(router.state.location.search).toBe("?tab=releases");
    fireEvent.keyDown(within(tabs).getByRole("tab", { name: "Freigaben" }), { key: "ArrowRight" });
    expect(within(tabs).getByRole("tab", { name: "Dokumente" })).toHaveAttribute("aria-selected", "true");
    expect(within(tabs).getByRole("tab", { name: "Dokumente" })).toHaveFocus();
  });

  it("opens the documents tab for an unknown tab value", async () => {
    stub();
    renderRoute("/products/laser?tab=unknown", TEST_ME);

    expect(await screen.findByRole("tab", { name: "Dokumente" })).toHaveAttribute("aria-selected", "true");
  });

  it("saves only the changed fields and clears the space with null", async () => {
    let body: unknown;
    stub({
      [`PATCH ${PRODUCT_URL}`]: (request) => {
        body = request.clone().json();
        return { status: 200, body: { ...LASER, name: "Laser 4040", space_id: null } };
      },
    });
    renderRoute("/products/laser", TEST_ME);
    const form = await detailsForm();

    fireEvent.change(within(form).getByLabelText("Name"), { target: { value: "Laser 4040" } });
    fireEvent.change(within(form).getByLabelText("Bereich"), { target: { value: "" } });
    fireEvent.click(within(form).getByRole("button", { name: "Speichern" }));

    await waitFor(async () => {
      expect(await body).toEqual({ name: "Laser 4040", space_id: null });
    });
  });

  it("sends the languages in their new order", async () => {
    let body: unknown;
    stub({
      [`PATCH ${PRODUCT_URL}`]: (request) => {
        body = request.clone().json();
        return { status: 200, body: { ...LASER, required_languages: ["en", "fr"] } };
      },
    });
    renderRoute("/products/laser", TEST_ME);
    const form = await detailsForm();

    fireEvent.click(within(form).getByRole("button", { name: "Deutsch entfernen" }));
    fireEvent.change(within(form).getByLabelText("Sprache hinzufügen …"), { target: { value: "fr" } });
    fireEvent.click(within(form).getByRole("button", { name: "Speichern" }));

    await waitFor(async () => {
      expect(await body).toEqual({ required_languages: ["en", "fr"] });
    });
  });

  it("discards what was typed", async () => {
    stub();
    renderRoute("/products/laser", TEST_ME);
    const form = await detailsForm();

    fireEvent.change(within(form).getByLabelText("Name"), { target: { value: "Etwas anderes" } });
    fireEvent.click(within(form).getByRole("button", { name: "Verwerfen" }));

    await waitFor(() => {
      expect(within(form).getByLabelText("Name")).toHaveValue("Laser 3030");
    });
    expect(within(form).getByRole("button", { name: "Speichern" })).toBeDisabled();
  });

  it("shows a failed save in the form", async () => {
    stub({ [`PATCH ${PRODUCT_URL}`]: apiError(404, "not_found") });
    renderRoute("/products/laser", TEST_ME);
    const form = await detailsForm();

    fireEvent.change(within(form).getByLabelText("Bereich"), { target: { value: "zertifikate" } });
    fireEvent.click(within(form).getByRole("button", { name: "Speichern" }));

    expect(await within(form).findByRole("alert")).toHaveTextContent("Der angeforderte Eintrag wurde nicht gefunden.");
  });

  it("explains an unknown product", async () => {
    stubApi({ [`GET ${PRODUCT_URL}`]: apiError(404, "not_found"), [`GET ${BASE}/spaces`]: page(SPACES) });
    renderRoute("/products/laser", TEST_ME);

    expect(await screen.findByRole("heading", { name: "Produkt nicht gefunden" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Zurück zu den Produkten" })).toHaveAttribute("href", "/products");
  });
});
