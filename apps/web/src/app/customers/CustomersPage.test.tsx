import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CustomerRead } from "@/lib/api/types";
import { apiError, type FakeAnswer, renderRoute, stubApi, TEST_ME } from "@/test/renderRoute";

const TENANT_ID = "00000000-0000-4000-8000-00000000000a";
const BASE = `/api/v1/app/tenants/${TENANT_ID}`;
const LIST = `GET ${BASE}/customers`;
const CREATE = `POST ${BASE}/customers`;

function customer(id: string, name: string, fields: Partial<CustomerRead> = {}): CustomerRead {
  return {
    id,
    name,
    contact_name: null,
    contact_email: null,
    delivery_count: 0,
    created_at: "2026-10-20T10:00:00Z",
    updated_at: "2026-10-20T10:00:00Z",
    ...fields,
  };
}

function page<T>(items: T[]) {
  return { status: 200, body: { items, next_cursor: null } };
}

function stub(customers: CustomerRead[], extra: Record<string, FakeAnswer> = {}) {
  return stubApi({ [LIST]: page(customers), ...extra });
}

async function openCreateDialog() {
  fireEvent.click(await screen.findByRole("button", { name: "Kunde anlegen" }));
  return screen.findByRole("dialog", { name: "Kunde anlegen" });
}

function postedBodies(fetchMock: ReturnType<typeof stubApi>) {
  return fetchMock.mock.calls.filter(([request]) => request.method === "POST").map(([request]) => request);
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("CustomersPage", () => {
  it("lists the customers with contact and number of deliveries", async () => {
    stub([
      customer("muster", "Muster AG", {
        contact_name: "Erika Muster",
        contact_email: "erika@muster.de",
        delivery_count: 2,
      }),
      customer("zeta", "Zeta GmbH"),
    ]);
    renderRoute("/customers", TEST_ME);

    const rows = within(await screen.findByRole("table"))
      .getAllByRole("row")
      .slice(1);
    expect(
      rows.map((row) =>
        within(row)
          .getAllByRole("cell")
          .map((cell) => cell.textContent),
      ),
    ).toEqual([
      ["Muster AG", "Erika Muster", "erika@muster.de", "2"],
      ["Zeta GmbH", "—", "—", "0"],
    ]);
    expect(screen.getByRole("link", { name: "Muster AG" })).toHaveAttribute("href", "/customers/muster");
    expect(screen.getByRole("link", { name: "erika@muster.de" })).toHaveAttribute("href", "mailto:erika@muster.de");
  });

  it("offers to create the first customer", async () => {
    stub([]);
    renderRoute("/customers", TEST_ME);

    expect(await screen.findByRole("heading", { name: "Noch keine Kunden" })).toBeInTheDocument();
    expect(await openCreateDialog()).toBeInTheDocument();
  });

  it("creates a customer, leaves empty contact fields out as null and opens it", async () => {
    const fetchMock = stub([customer("zeta", "Zeta GmbH")], {
      [CREATE]: { status: 201, body: customer("neu", "Muster AG") },
    });
    const router = renderRoute("/customers", TEST_ME);
    const dialog = await openCreateDialog();

    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: " Muster AG " } });
    fireEvent.change(within(dialog).getByLabelText("Ansprechpartner (optional)"), {
      target: { value: "Erika Muster" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Anlegen" }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/customers/neu");
    });
    expect(await postedBodies(fetchMock)[0]?.json()).toEqual({
      name: "Muster AG",
      contact_name: "Erika Muster",
      contact_email: null,
    });
  });

  it("checks name and e-mail before sending anything", async () => {
    const fetchMock = stub([customer("zeta", "Zeta GmbH")]);
    renderRoute("/customers", TEST_ME);
    const dialog = await openCreateDialog();

    fireEvent.change(within(dialog).getByLabelText("E-Mail des Ansprechpartners (optional)"), {
      target: { value: "erika-at-muster" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Anlegen" }));

    expect(await within(dialog).findByText("Bitte geben Sie einen Namen ein.")).toBeInTheDocument();
    expect(within(dialog).getByText(/^Bitte geben Sie eine gültige E-Mail-Adresse ein/)).toBeInTheDocument();
    expect(postedBodies(fetchMock)).toHaveLength(0);
  });

  it("shows an address the API rejects under the e-mail field", async () => {
    stub([customer("zeta", "Zeta GmbH")], {
      [CREATE]: apiError(422, "validation_failed", {
        fields: [{ loc: ["body", "contact_email"], type: "value_error", msg: "not an e-mail address" }],
      }),
    });
    renderRoute("/customers", TEST_ME);
    const dialog = await openCreateDialog();

    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "Muster AG" } });
    fireEvent.change(within(dialog).getByLabelText("E-Mail des Ansprechpartners (optional)"), {
      target: { value: "a@b.c" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Anlegen" }));

    const email = within(dialog).getByLabelText("E-Mail des Ansprechpartners (optional)");
    await waitFor(() => {
      expect(email).toHaveAttribute("aria-invalid", "true");
    });
    expect(email).toHaveFocus();
    expect(within(dialog).queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows any other failure inside the dialog", async () => {
    stub([customer("zeta", "Zeta GmbH")], { [CREATE]: apiError(500, "internal_error") });
    renderRoute("/customers", TEST_ME);
    const dialog = await openCreateDialog();

    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "Muster AG" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Anlegen" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Ein unerwarteter Fehler ist aufgetreten.");
  });
});
