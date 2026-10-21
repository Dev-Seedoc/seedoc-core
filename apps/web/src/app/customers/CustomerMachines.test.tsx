import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CustomerRead, DeliveryListItem, DeliveryRead, MachineListItem } from "@/lib/api/types";
import { apiError, type FakeAnswer, renderRoute, stubApi, TEST_ME } from "@/test/renderRoute";

const TENANT_ID = "00000000-0000-4000-8000-00000000000a";
const BASE = `/api/v1/app/tenants/${TENANT_ID}`;

const MUSTER: CustomerRead = {
  id: "muster",
  name: "Muster AG",
  contact_name: null,
  contact_email: null,
  delivery_count: 2,
  created_at: "2026-10-20T10:00:00Z",
  updated_at: "2026-10-20T10:00:00Z",
};

function listItem(id: string, name: string): DeliveryListItem {
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
  };
}

function machine(id: string, name: string, fields: Partial<MachineListItem> = {}): MachineListItem {
  return {
    id,
    product_id: "laser",
    product_name: "Laser 3030",
    name,
    serial_no: `SN-${id}`,
    public_token: `token-${id}`,
    portal_url: `https://localhost/m/token-${id}`,
    first_published_at: null,
    archived_at: null,
    ...fields,
  };
}

function detail(item: DeliveryListItem, machines: MachineListItem[]): DeliveryRead {
  return {
    ...item,
    required_languages: ["de"],
    public_token: `token-${item.id}`,
    portal_url: `https://localhost/s/token-${item.id}`,
    has_open_draft: false,
    machines,
  };
}

const NORD = listItem("nord", "Anlage Nord");
const SUED = listItem("sued", "Anlage Süd");

function page<T>(items: T[]) {
  return { status: 200, body: { items, next_cursor: null } };
}

function stub(deliveries: DeliveryListItem[], details: Record<string, FakeAnswer>) {
  return stubApi({
    [`GET ${BASE}/customers/muster`]: { status: 200, body: MUSTER },
    [`GET ${BASE}/deliveries`]: page(deliveries),
    ...Object.fromEntries(Object.entries(details).map(([id, answer]) => [`GET ${BASE}/deliveries/${id}`, answer])),
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("CustomerMachines", () => {
  it("gathers the machines of every delivery of the customer", async () => {
    stub([NORD, SUED], {
      nord: {
        status: 200,
        body: detail(NORD, [
          machine("1", "Laser links"),
          machine("2", "Presse", {
            product_id: "presse",
            product_name: "Presse P1",
            archived_at: "2026-10-21T08:00:00Z",
          }),
        ]),
      },
      sued: { status: 200, body: detail(SUED, [machine("3", "Laser rechts")]) },
    });
    renderRoute("/customers/muster", TEST_ME);

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
      ["Laser links", "SN-1", "Laser 3030", "Anlage Nord", "Aktiv"],
      ["Presse", "SN-2", "Presse P1", "Anlage Nord", "Archiviert"],
      ["Laser rechts", "SN-3", "Laser 3030", "Anlage Süd", "Aktiv"],
    ]);
    expect(within(rows[1] as HTMLElement).getByRole("link", { name: "Presse P1" })).toHaveAttribute(
      "href",
      "/products/presse",
    );
    expect(within(rows[2] as HTMLElement).getByRole("link", { name: "Anlage Süd" })).toHaveAttribute(
      "href",
      "/deliveries/sued",
    );
  });

  it("keeps the other machines when one delivery cannot be loaded and retries it", async () => {
    let suedCalls = 0;
    stub([NORD, SUED], {
      nord: { status: 200, body: detail(NORD, [machine("1", "Laser links")]) },
      sued: () => {
        suedCalls += 1;
        return suedCalls === 1
          ? apiError(500, "internal_error")
          : { status: 200, body: detail(SUED, [machine("3", "Laser rechts")]) };
      },
    });
    renderRoute("/customers/muster", TEST_ME);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Die Maschinen der Lieferung „Anlage Süd“ konnten nicht geladen werden.");
    expect(screen.getByRole("cell", { name: "Laser links" })).toBeInTheDocument();

    fireEvent.click(within(alert).getByRole("button", { name: "Wiederholen" }));

    expect(await screen.findByRole("cell", { name: "Laser rechts" })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
  });

  it("explains where machines come from when there are none", async () => {
    stub([NORD], { nord: { status: 200, body: detail(NORD, []) } });
    renderRoute("/customers/muster", TEST_ME);

    expect(await screen.findByRole("heading", { name: "Noch keine Maschinen" })).toBeInTheDocument();
  });
});
