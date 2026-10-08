import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { queryKeys } from "@/lib/api/queryKeys";
import type { MeRead } from "@/lib/api/types";
import { routes } from "@/router";
import { apiError, renderRoute, stubApi } from "@/test/renderRoute";

const ME: MeRead = {
  user: { id: "00000000-0000-4000-8000-000000000001", email: "owner@example.com", full_name: "Olga Owner" },
  memberships: [
    { tenant_id: "00000000-0000-4000-8000-00000000000a", tenant_name: "Alpha Maschinenbau", role: "owner" },
  ],
  operator_orgs: [],
  is_staff: false,
  mfa_verified: false,
};

function renderApp(path: string, me?: MeRead) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  if (me) {
    queryClient.setQueryData(queryKeys.auth.me(), me);
  }
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

function stubMeResponse(status: number, code: string) {
  const body = JSON.stringify({ error: { code, message: code, details: {} } });
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(body, { status, headers: { "Content-Type": "application/json" } }))),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("AppLayout", () => {
  it("redirects to /login when nobody is logged in", async () => {
    stubMeResponse(401, "unauthenticated");

    const router = renderApp("/documents");

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/login");
    });
  });

  it("shows the sidebar, breadcrumbs, tenant and page for a member", () => {
    renderApp("/documents", ME);

    const nav = screen.getByRole("navigation", { name: "Hauptnavigation" });
    for (const label of ["Übersicht", "Dokumente", "Produkte", "Kunden", "Einstellungen"]) {
      expect(within(nav).getByRole("link", { name: label })).toBeInTheDocument();
    }
    expect(within(nav).queryByRole("link", { name: "SeeDoc-Team" })).not.toBeInTheDocument();

    const breadcrumbs = screen.getByRole("navigation", { name: "Seitenpfad" });
    expect(within(breadcrumbs).getByRole("link", { name: "Übersicht" })).toHaveAttribute("href", "/");
    expect(within(breadcrumbs).getByText("Dokumente")).toHaveAttribute("aria-current", "page");

    expect(screen.getByText("Alpha Maschinenbau")).toBeInTheDocument();
    expect(screen.getByText("Dieser Bereich ist in Arbeit")).toBeInTheDocument();
  });

  it("shows the staff link only to staff", () => {
    renderApp("/", { ...ME, is_staff: true });

    const nav = screen.getByRole("navigation", { name: "Hauptnavigation" });
    expect(within(nav).getByRole("link", { name: "SeeDoc-Team" })).toHaveAttribute("href", "/staff");
  });

  it("explains when the user belongs to no tenant", () => {
    renderApp("/", { ...ME, memberships: [] });

    expect(screen.getByRole("heading", { name: "Sie sind noch keinem Hersteller zugeordnet" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Hauptnavigation" })).not.toBeInTheDocument();
  });

  it("sends staff without a tenant to the staff console", () => {
    const router = renderApp("/", { ...ME, memberships: [], is_staff: true });

    expect(router.state.location.pathname).toBe("/staff");
  });

  it("offers a retry when the server fails", async () => {
    stubMeResponse(500, "internal_error");

    renderApp("/");

    expect(
      await screen.findByRole("heading", { name: "Die Anwendung konnte nicht geladen werden" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Wiederholen" })).toBeInTheDocument();
  });

  it("switches tenant from the top bar", async () => {
    renderApp("/", {
      ...ME,
      memberships: [
        ...ME.memberships,
        { tenant_id: "00000000-0000-4000-8000-00000000000b", tenant_name: "Beta Anlagen", role: "editor" },
      ],
    });

    fireEvent.keyDown(screen.getByRole("button", { name: "Hersteller wechseln" }), { key: "Enter" });
    fireEvent.click(await screen.findByRole("menuitemradio", { name: "Beta Anlagen" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Hersteller wechseln" })).toHaveTextContent("Beta Anlagen");
    });
  });

  it("never wraps portal pages in the manufacturer frame", () => {
    renderApp("/m/some-token", ME);

    expect(screen.queryByRole("navigation", { name: "Hauptnavigation" })).not.toBeInTheDocument();
  });
  it("logs out from the user menu and lands on the login page", async () => {
    stubApi({
      "POST /api/v1/auth/logout": { status: 204 },
      "GET /api/v1/auth/me": apiError(401, "unauthenticated"),
    });
    const router = renderRoute("/documents", ME);

    fireEvent.keyDown(screen.getByRole("button", { name: "Benutzermenü" }), { key: "Enter" });
    fireEvent.click(await screen.findByRole("menuitem", { name: "Abmelden" }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/login");
    });
    expect(await screen.findByRole("heading", { name: "Anmelden" })).toBeInTheDocument();
  });
});
