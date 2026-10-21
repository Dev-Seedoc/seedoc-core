import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CustomerRead, DeliveryListItem, DeliveryRead } from "@/lib/api/types";
import { apiError, type FakeAnswer, renderRoute, stubApi, TEST_ME } from "@/test/renderRoute";

const TENANT_ID = "00000000-0000-4000-8000-00000000000a";
const BASE = `/api/v1/app/tenants/${TENANT_ID}`;
const DELIVERIES = `GET ${BASE}/deliveries`;
const CREATE = `POST ${BASE}/deliveries`;

const MUSTER: CustomerRead = {
  id: "muster",
  name: "Muster AG",
  contact_name: null,
  contact_email: null,
  delivery_count: 2,
  created_at: "2026-10-20T10:00:00Z",
  updated_at: "2026-10-20T10:00:00Z",
};

function delivery(id: string, name: string, fields: Partial<DeliveryListItem> = {}): DeliveryListItem {
  return {
    id,
    customer_id: "muster",
    customer_name: "Muster AG",
    kind: "system",
    name,
    order_no: null,
    status: "draft",
    machine_count: 0,
    current_release_no: null,
    updated_at: "2026-10-20T10:00:00Z",
    ...fields,
  };
}

const CREATED: DeliveryRead = {
  id: "neu",
  customer_id: "muster",
  customer_name: "Muster AG",
  kind: "machine",
  name: "Laser Halle 3",
  order_no: null,
  status: "draft",
  required_languages: [],
  public_token: "token",
  portal_url: "https://localhost/s/token",
  current_release_no: null,
  has_open_draft: false,
  machines: [],
};

function page<T>(items: T[]) {
  return { status: 200, body: { items, next_cursor: null } };
}

function stub(deliveries: DeliveryListItem[], extra: Record<string, FakeAnswer> = {}) {
  return stubApi({
    [`GET ${BASE}/customers/muster`]: { status: 200, body: MUSTER },
    [DELIVERIES]: page(deliveries),
    ...extra,
  });
}

async function openCreateDialog() {
  fireEvent.click(await screen.findByRole("button", { name: "Lieferung anlegen" }));
  return screen.findByRole("dialog", { name: "Lieferung für „Muster AG“ anlegen" });
}

function postBody(fetchMock: ReturnType<typeof stubApi>) {
  return fetchMock.mock.calls.find(([request]) => request.method === "POST")?.[0].json();
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("CustomerDeliveries", () => {
  it("lists only this customer's deliveries", async () => {
    const fetchMock = stub([
      delivery("nord", "Anlage Nord", { order_no: "A-4711", machine_count: 3, status: "published" }),
      delivery("laser", "Laser Halle 3", { kind: "machine" }),
    ]);
    renderRoute("/customers/muster?tab=deliveries", TEST_ME);

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
      ["Anlage Nord", "Anlage", "A-4711", "Veröffentlicht", "3", "—"],
      ["Laser Halle 3", "Maschine", "—", "Entwurf", "0", "—"],
    ]);
    expect(screen.getByRole("link", { name: "Anlage Nord" })).toHaveAttribute("href", "/deliveries/nord");
    const listCall = fetchMock.mock.calls.find(([request]) => new URL(request.url).pathname === `${BASE}/deliveries`);
    expect(new URL(listCall?.[0].url ?? "").searchParams.get("customer_id")).toBe("muster");
  });

  it("creates a machine delivery whose languages come from its products", async () => {
    const fetchMock = stub([], { [CREATE]: { status: 201, body: CREATED } });
    renderRoute("/customers/muster?tab=deliveries", TEST_ME);
    const dialog = await openCreateDialog();

    expect(within(dialog).getByRole("radio", { name: /^Maschine/ })).toBeChecked();
    expect(within(dialog).getByRole("radio", { name: "Aus den Produkten der Maschinen übernehmen" })).toBeChecked();
    expect(within(dialog).queryByRole("list", { name: "Pflichtsprachen" })).not.toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: " Laser Halle 3 " } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Anlegen" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(await postBody(fetchMock)).toEqual({
      customer_id: "muster",
      kind: "machine",
      name: "Laser Halle 3",
      order_no: null,
    });
  });

  it("creates a system delivery with an order number and languages set now", async () => {
    const fetchMock = stub([], { [CREATE]: { status: 201, body: { ...CREATED, kind: "system" } } });
    renderRoute("/customers/muster?tab=deliveries", TEST_ME);
    const dialog = await openCreateDialog();

    fireEvent.click(within(dialog).getByRole("radio", { name: /^Anlage/ }));
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "Anlage Süd" } });
    fireEvent.change(within(dialog).getByLabelText("Auftragsnummer (optional)"), { target: { value: "A-9" } });
    fireEvent.click(within(dialog).getByRole("radio", { name: "Jetzt festlegen" }));
    fireEvent.change(await within(dialog).findByLabelText("Sprache hinzufügen …"), { target: { value: "pl" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Anlegen" }));

    await waitFor(async () => {
      expect(await postBody(fetchMock)).toEqual({
        customer_id: "muster",
        kind: "system",
        name: "Anlage Süd",
        order_no: "A-9",
        required_languages: ["de", "pl"],
      });
    });
  });

  it("asks for a name and shows a failed save inside the dialog", async () => {
    stub([], { [CREATE]: apiError(404, "not_found") });
    renderRoute("/customers/muster?tab=deliveries", TEST_ME);
    const dialog = await openCreateDialog();

    fireEvent.click(within(dialog).getByRole("button", { name: "Anlegen" }));
    expect(await within(dialog).findByText("Bitte geben Sie einen Namen ein.")).toBeInTheDocument();

    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "Anlage" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Anlegen" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Der angeforderte Eintrag wurde nicht gefunden.",
    );
  });
});
