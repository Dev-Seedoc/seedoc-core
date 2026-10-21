import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CustomerRead } from "@/lib/api/types";
import { apiError, type FakeAnswer, renderRoute, stubApi, TEST_ME } from "@/test/renderRoute";

const TENANT_ID = "00000000-0000-4000-8000-00000000000a";
const CUSTOMER_URL = `/api/v1/app/tenants/${TENANT_ID}/customers/muster`;

const MUSTER: CustomerRead = {
  id: "muster",
  name: "Muster AG",
  contact_name: "Erika Muster",
  contact_email: "erika@muster.de",
  delivery_count: 2,
  created_at: "2026-10-20T10:00:00Z",
  updated_at: "2026-10-20T10:00:00Z",
};

function stub(extra: Record<string, FakeAnswer> = {}) {
  return stubApi({ [`GET ${CUSTOMER_URL}`]: { status: 200, body: MUSTER }, ...extra });
}

async function contactForm() {
  const form = await screen.findByRole("region", { name: "Angaben zum Kunden" });
  await waitFor(() => {
    expect(within(form).getByLabelText("Name")).toHaveValue("Muster AG");
  });
  return form;
}

function patchBody(fetchMock: ReturnType<typeof stubApi>) {
  return fetchMock.mock.calls.find(([request]) => request.method === "PATCH")?.[0].json();
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("CustomerDetailPage", () => {
  it("shows the customer, its contact and the tabs", async () => {
    stub();
    const router = renderRoute("/customers/muster", TEST_ME);

    expect(await screen.findByRole("heading", { level: 1, name: "Muster AG" })).toBeInTheDocument();
    expect(screen.getByText("2 Lieferungen")).toBeInTheDocument();
    const form = await contactForm();
    expect(within(form).getByLabelText("Ansprechpartner (optional)")).toHaveValue("Erika Muster");
    expect(within(form).getByLabelText("E-Mail des Ansprechpartners (optional)")).toHaveValue("erika@muster.de");

    const tabs = screen.getByRole("tablist", { name: "Bereiche des Kunden" });
    expect(
      within(tabs)
        .getAllByRole("tab")
        .map((tab) => tab.textContent),
    ).toEqual(["Maschinen", "Lieferungen"]);
    expect(within(tabs).getByRole("tab", { name: "Maschinen" })).toHaveAttribute("aria-selected", "true");
    fireEvent.click(within(tabs).getByRole("tab", { name: "Lieferungen" }));
    expect(router.state.location.search).toBe("?tab=deliveries");
  });

  it("clears an emptied contact field with null and sends only what changed", async () => {
    const fetchMock = stub({
      [`PATCH ${CUSTOMER_URL}`]: { status: 200, body: { ...MUSTER, name: "Muster GmbH", contact_email: null } },
    });
    renderRoute("/customers/muster", TEST_ME);
    const form = await contactForm();

    fireEvent.change(within(form).getByLabelText("Name"), { target: { value: "Muster GmbH" } });
    fireEvent.change(within(form).getByLabelText("E-Mail des Ansprechpartners (optional)"), {
      target: { value: "" },
    });
    fireEvent.click(within(form).getByRole("button", { name: "Speichern" }));

    await waitFor(async () => {
      expect(await patchBody(fetchMock)).toEqual({ name: "Muster GmbH", contact_email: null });
    });
  });

  it("does not count a different spelling of the same address as a change", async () => {
    const fetchMock = stub();
    renderRoute("/customers/muster", TEST_ME);
    const form = await contactForm();

    fireEvent.change(within(form).getByLabelText("E-Mail des Ansprechpartners (optional)"), {
      target: { value: "Erika@Muster.de" },
    });
    fireEvent.click(within(form).getByRole("button", { name: "Speichern" }));

    await waitFor(() => {
      expect(within(form).getByRole("button", { name: "Speichern" })).toBeDisabled();
    });
    expect(fetchMock.mock.calls.some(([request]) => request.method === "PATCH")).toBe(false);
  });

  it("shows a failed save in the form", async () => {
    stub({ [`PATCH ${CUSTOMER_URL}`]: apiError(500, "internal_error") });
    renderRoute("/customers/muster", TEST_ME);
    const form = await contactForm();

    fireEvent.change(within(form).getByLabelText("Name"), { target: { value: "Muster GmbH" } });
    fireEvent.click(within(form).getByRole("button", { name: "Speichern" }));

    expect(await within(form).findByRole("alert")).toHaveTextContent("Ein unerwarteter Fehler ist aufgetreten.");
  });

  it("explains an unknown customer", async () => {
    stubApi({ [`GET ${CUSTOMER_URL}`]: apiError(404, "not_found") });
    renderRoute("/customers/muster", TEST_ME);

    expect(await screen.findByRole("heading", { name: "Kunde nicht gefunden" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Zurück zu den Kunden" })).toHaveAttribute("href", "/customers");
  });
});
