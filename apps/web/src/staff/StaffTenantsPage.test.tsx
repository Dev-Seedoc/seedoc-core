import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MeRead, StaffTenantListItem, StaffTenantRead } from "@/lib/api/types";
import { apiError, renderRoute, stubApi, TEST_ME } from "@/test/renderRoute";

const STAFF: MeRead = { ...TEST_ME, is_staff: true, mfa_verified: true };
const LIST = "GET /api/v1/staff/tenants";
const CREATE = "POST /api/v1/staff/tenants";

function listItem(overrides: Partial<StaffTenantListItem>): StaffTenantListItem {
  return {
    id: "00000000-0000-4000-8000-00000000000a",
    name: "Alpha Maschinenbau",
    slug: "alpha-maschinenbau",
    status: "active",
    member_count: 3,
    created_at: "2026-10-06T10:00:00Z",
    ...overrides,
  };
}

const CREATED: StaffTenantRead = {
  id: "00000000-0000-4000-8000-0000000000c1",
  name: "Müller Maschinenbau GmbH",
  slug: "mueller-maschinenbau-gmbh",
  status: "active",
  created_at: "2026-10-08T10:00:00Z",
  updated_at: "2026-10-08T10:00:00Z",
  members: [],
  open_invitations: [],
};

function page(items: StaffTenantListItem[], nextCursor: string | null = null) {
  return { status: 200, body: { items, next_cursor: nextCursor } };
}

function openCreateDialog() {
  // The header button; an empty list shows a second one in its empty state.
  const [createButton] = screen.getAllByRole("button", { name: "Hersteller anlegen" });
  if (!createButton) {
    throw new Error("no create button");
  }
  fireEvent.click(createButton);
  return screen.getByRole("dialog", { name: "Hersteller anlegen" });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("StaffTenantsPage", () => {
  it("lists tenants with link, short name, German status, members and date", async () => {
    stubApi({ [LIST]: page([listItem({}), listItem({ id: "b", name: "Beta Anlagen", status: "inactive" })]) });
    renderRoute("/staff", STAFF);

    const link = await screen.findByRole("link", { name: "Alpha Maschinenbau" });
    expect(link).toHaveAttribute("href", "/staff/tenants/00000000-0000-4000-8000-00000000000a");
    const row = link.closest("tr");
    if (!row) {
      throw new Error("tenant link is not in a table row");
    }
    expect(within(row).getByText("alpha-maschinenbau")).toBeInTheDocument();
    expect(within(row).getByText("Aktiv")).toBeInTheDocument();
    expect(within(row).getByText("3")).toBeInTheDocument();
    expect(within(row).getByText("06.10.2026")).toBeInTheDocument();
    expect(screen.getByText("Inaktiv")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mehr laden" })).not.toBeInTheDocument();
  });

  it("loads the next page with the cursor", async () => {
    const fetchMock = stubApi({
      [LIST]: (request) =>
        new URL(request.url).searchParams.get("cursor") === "next-1"
          ? page([listItem({ id: "c", name: "Gamma Technik" })])
          : page([listItem({})], "next-1"),
    });
    renderRoute("/staff", STAFF);

    fireEvent.click(await screen.findByRole("button", { name: "Mehr laden" }));

    expect(await screen.findByRole("link", { name: "Gamma Technik" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Alpha Maschinenbau" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mehr laden" })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("explains an empty list", async () => {
    stubApi({ [LIST]: page([]) });
    renderRoute("/staff", STAFF);

    expect(await screen.findByRole("heading", { name: "Noch keine Hersteller" })).toBeInTheDocument();
  });
});

describe("CreateTenantDialog", () => {
  it("suggests the short name from the name until it is edited", async () => {
    stubApi({ [LIST]: page([]) });
    renderRoute("/staff", STAFF);
    await screen.findByRole("heading", { name: "Noch keine Hersteller" });

    const dialog = openCreateDialog();
    const name = within(dialog).getByLabelText("Name");
    const slug = within(dialog).getByLabelText("Kurzname (Slug)");

    fireEvent.change(name, { target: { value: "Müller Maschinenbau GmbH" } });
    expect(slug).toHaveValue("mueller-maschinenbau-gmbh");

    fireEvent.change(slug, { target: { value: "mueller" } });
    fireEvent.change(name, { target: { value: "Müller Maschinenbau AG" } });
    expect(slug).toHaveValue("mueller");
  });

  it("sends nothing when the input is invalid", async () => {
    const fetchMock = stubApi({ [LIST]: page([]) });
    renderRoute("/staff", STAFF);
    await screen.findByRole("heading", { name: "Noch keine Hersteller" });

    const dialog = openCreateDialog();
    fireEvent.change(within(dialog).getByLabelText("Kurzname (Slug)"), { target: { value: "Bad Slug" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Anlegen" }));

    expect(await within(dialog).findByText("Bitte geben Sie einen Namen ein.")).toBeInTheDocument();
    expect(within(dialog).getByText(/Der Kurzname muss 2 bis 63 Zeichen lang sein/)).toBeInTheDocument();
    expect(within(dialog).getByText("Bitte geben Sie eine gültige E-Mail-Adresse ein.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([request]) => request.method === "POST")).toBe(false);
  });

  it("shows a taken short name under its field", async () => {
    stubApi({ [LIST]: page([]), [CREATE]: apiError(409, "conflict", { field: "slug" }) });
    renderRoute("/staff", STAFF);
    await screen.findByRole("heading", { name: "Noch keine Hersteller" });

    const dialog = openCreateDialog();
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "Alpha Maschinenbau" } });
    fireEvent.change(within(dialog).getByLabelText("E-Mail-Adresse des Inhabers"), {
      target: { value: "owner@example.com" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Anlegen" }));

    expect(await within(dialog).findByText("Dieser Kurzname ist bereits vergeben.")).toBeInTheDocument();
    expect(within(dialog).queryByRole("alert")).not.toBeInTheDocument();
  });

  it("creates the tenant and opens its page", async () => {
    const fetchMock = stubApi({
      [LIST]: page([]),
      [CREATE]: { status: 201, body: CREATED },
      [`GET /api/v1/staff/tenants/${CREATED.id}`]: { status: 200, body: CREATED },
    });
    const router = renderRoute("/staff", STAFF);
    await screen.findByRole("heading", { name: "Noch keine Hersteller" });

    const dialog = openCreateDialog();
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "Müller Maschinenbau GmbH" } });
    fireEvent.change(within(dialog).getByLabelText("E-Mail-Adresse des Inhabers"), {
      target: { value: "owner@example.com" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Anlegen" }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/staff/tenants/${CREATED.id}`);
    });
    const createRequest = fetchMock.mock.calls.find(([request]) => request.method === "POST")?.[0];
    expect(await createRequest?.json()).toEqual({
      name: "Müller Maschinenbau GmbH",
      slug: "mueller-maschinenbau-gmbh",
      owner_email: "owner@example.com",
    });
  });
});
