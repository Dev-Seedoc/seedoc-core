import { fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MeRead, StaffTenantRead } from "@/lib/api/types";
import { apiError, renderRoute, stubApi, TEST_ME } from "@/test/renderRoute";

const STAFF: MeRead = { ...TEST_ME, is_staff: true, mfa_verified: true };
const TENANT_ID = "00000000-0000-4000-8000-00000000000a";
const PATH = `/staff/tenants/${TENANT_ID}`;
const GET = `GET /api/v1/staff/tenants/${TENANT_ID}`;
const PATCH = `PATCH /api/v1/staff/tenants/${TENANT_ID}`;

const TENANT: StaffTenantRead = {
  id: TENANT_ID,
  name: "Alpha Maschinenbau",
  slug: "alpha-maschinenbau",
  status: "active",
  created_at: "2026-10-06T10:00:00Z",
  updated_at: "2026-10-07T10:00:00Z",
  members: [
    { user_id: "u1", email: "owner@alpha.example", full_name: "Olga Owner", role: "owner" },
    { user_id: "u2", email: "editor@alpha.example", full_name: null, role: "editor" },
  ],
  open_invitations: [
    {
      id: "i1",
      email: "admin@alpha.example",
      role: "admin",
      expires_at: "2026-10-13T10:00:00Z",
      created_at: "2026-10-06T10:00:00Z",
    },
  ],
};

function rowOf(text: string): HTMLElement {
  const row = screen.getByText(text).closest("tr");
  if (!row) {
    throw new Error(`no table row contains "${text}"`);
  }
  return row;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("StaffTenantDetailPage", () => {
  it("shows the tenant with its members and open invitations", async () => {
    stubApi({ [GET]: { status: 200, body: TENANT } });
    renderRoute(PATH, STAFF);

    expect(await screen.findByRole("heading", { name: "Alpha Maschinenbau" })).toBeInTheDocument();
    expect(screen.getByText("alpha-maschinenbau")).toBeInTheDocument();
    expect(screen.getByText("Aktiv")).toBeInTheDocument();
    // The back link inside the page (the header nav has a "Hersteller" link too).
    expect(within(screen.getByRole("main")).getByRole("link", { name: "Hersteller" })).toHaveAttribute(
      "href",
      "/staff",
    );

    const ownerRow = rowOf("owner@alpha.example");
    expect(within(ownerRow).getByText("Olga Owner")).toBeInTheDocument();
    expect(within(ownerRow).getByText("Inhaber")).toBeInTheDocument();
    const editorRow = rowOf("editor@alpha.example");
    expect(within(editorRow).getByText("—")).toBeInTheDocument();
    expect(within(editorRow).getByText("Redakteur")).toBeInTheDocument();

    const invitationRow = rowOf("admin@alpha.example");
    expect(within(invitationRow).getByText("Administrator")).toBeInTheDocument();
  });

  it("deactivates only after confirming", async () => {
    const fetchMock = stubApi({
      [GET]: { status: 200, body: TENANT },
      [PATCH]: { status: 200, body: { ...TENANT, status: "inactive" } },
    });
    renderRoute(PATH, STAFF);

    fireEvent.click(await screen.findByRole("button", { name: "Deaktivieren" }));
    const dialog = screen.getByRole("alertdialog", { name: "Hersteller deaktivieren?" });
    expect(within(dialog).getByText(/QR-Portale dieses Herstellers sind nicht mehr erreichbar/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([request]) => request.method === "PATCH")).toBe(false);

    fireEvent.click(within(dialog).getByRole("button", { name: "Deaktivieren" }));

    expect(await screen.findByText("Inaktiv")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Aktivieren" })).toBeInTheDocument();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    const patchRequest = fetchMock.mock.calls.find(([request]) => request.method === "PATCH")?.[0];
    expect(await patchRequest?.json()).toEqual({ status: "inactive" });
  });

  it("explains an unknown tenant", async () => {
    stubApi({ [GET]: apiError(404, "not_found") });
    renderRoute(PATH, STAFF);

    expect(await screen.findByRole("heading", { name: "Hersteller nicht gefunden" })).toBeInTheDocument();
  });
});
