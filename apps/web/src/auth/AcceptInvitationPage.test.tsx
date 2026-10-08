import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { InvitationPreview } from "@/lib/api/types";
import { apiError, type FakeResponse, renderRoute, stubApi, TEST_ME } from "@/test/renderRoute";

const PATH = "/invite/invite-token";
const GET_INVITATION = "GET /api/v1/auth/invitations/invite-token";
const ACCEPT = "POST /api/v1/auth/invitations/invite-token/accept";
const LOGGED_OUT = { "GET /api/v1/auth/me": apiError(401, "unauthenticated") };

const TEAM_INVITATION: InvitationPreview = {
  kind: "tenant_member",
  tenant_name: "Alpha Maschinenbau",
  operator_org_name: null,
  email: "new.member@example.com",
  has_account: false,
};

function invitation(overrides: Partial<InvitationPreview> = {}): FakeResponse {
  return { status: 200, body: { ...TEAM_INVITATION, ...overrides } };
}

function acceptBody(fetchMock: ReturnType<typeof stubApi>): Promise<unknown> | undefined {
  const request = fetchMock.mock.calls.find(([r]) => r.method === "POST" && r.url.endsWith("/accept"))?.[0];
  return request?.json();
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AcceptInvitationPage", () => {
  it("creates an account for a new person and opens the app", async () => {
    const fetchMock = stubApi({
      ...LOGGED_OUT,
      [GET_INVITATION]: invitation(),
      [ACCEPT]: { status: 200, body: TEST_ME },
    });
    const router = renderRoute(PATH);

    expect(await screen.findByRole("heading", { name: "Einladung zu Alpha Maschinenbau" })).toBeInTheDocument();
    expect(screen.getByText("Die Einladung gilt für new.member@example.com.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Name (optional)"), { target: { value: "Nina Neu" } });
    fireEvent.change(screen.getByLabelText("Neues Passwort"), { target: { value: "correct-horse-battery" } });
    fireEvent.change(screen.getByLabelText("Passwort wiederholen"), { target: { value: "correct-horse-battery" } });
    fireEvent.click(screen.getByRole("button", { name: "Konto erstellen und beitreten" }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/");
    });
    expect(await acceptBody(fetchMock)).toEqual({ password: "correct-horse-battery", full_name: "Nina Neu" });
  });

  it("asks an existing account for its password", async () => {
    const fetchMock = stubApi({
      ...LOGGED_OUT,
      [GET_INVITATION]: invitation({ has_account: true }),
      [ACCEPT]: { status: 200, body: TEST_ME },
    });
    renderRoute(PATH);

    expect(await screen.findByText(/Sie haben bereits ein SeeDoc-Konto/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Neues Passwort")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Passwort"), { target: { value: "existing-password-123" } });
    fireEvent.click(screen.getByRole("button", { name: "Einladung annehmen" }));

    await waitFor(async () => {
      expect(await acceptBody(fetchMock)).toEqual({ password: "existing-password-123" });
    });
  });

  it("shows a wrong password inline", async () => {
    stubApi({
      ...LOGGED_OUT,
      [GET_INVITATION]: invitation({ has_account: true }),
      [ACCEPT]: apiError(401, "invalid_credentials"),
    });
    renderRoute(PATH);

    fireEvent.change(await screen.findByLabelText("Passwort"), { target: { value: "wrong-password-123" } });
    fireEvent.click(screen.getByRole("button", { name: "Einladung annehmen" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Ungültige E-Mail-Adresse oder falsches Passwort.");
  });

  it("lets the invited person accept with one click when already logged in", async () => {
    const me = { ...TEST_ME, user: { ...TEST_ME.user, email: "New.Member@example.com" } };
    const fetchMock = stubApi({
      [GET_INVITATION]: invitation({ has_account: true }),
      [ACCEPT]: { status: 200, body: me },
    });
    const router = renderRoute(PATH, me);

    fireEvent.click(await screen.findByRole("button", { name: "Einladung annehmen" }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/");
    });
    expect(screen.queryByLabelText("Passwort")).not.toBeInTheDocument();
    expect(await acceptBody(fetchMock)).toEqual({});
  });

  it("asks someone logged in as another user to log out first", async () => {
    stubApi({
      ...LOGGED_OUT,
      [GET_INVITATION]: invitation({ has_account: true }),
      "POST /api/v1/auth/logout": { status: 204 },
    });
    renderRoute(PATH, TEST_ME);

    expect(
      await screen.findByRole("heading", { name: "Sie sind mit einem anderen Konto angemeldet" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/gilt für new\.member@example\.com, Sie sind als owner@example\.com angemeldet/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Einladung annehmen" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Abmelden" }));

    // After logout the page re-checks and shows the form for the invited account.
    expect(await screen.findByText(/Sie haben bereits ein SeeDoc-Konto/)).toBeInTheDocument();
  });

  it("explains an invalid invitation", async () => {
    stubApi({ ...LOGGED_OUT, [GET_INVITATION]: apiError(410, "invitation_invalid") });
    renderRoute(PATH);

    expect(await screen.findByRole("heading", { name: "Diese Einladung ist nicht mehr gültig" })).toBeInTheDocument();
  });

  it("sends operators to their own area after accepting", async () => {
    stubApi({
      ...LOGGED_OUT,
      [GET_INVITATION]: invitation({ kind: "operator", tenant_name: null, operator_org_name: "Kunde GmbH Betrieb" }),
      [ACCEPT]: { status: 200, body: { ...TEST_ME, memberships: [] } },
    });
    const router = renderRoute(PATH);

    expect(await screen.findByRole("heading", { name: "Einladung zu Kunde GmbH Betrieb" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Neues Passwort"), { target: { value: "correct-horse-battery" } });
    fireEvent.change(screen.getByLabelText("Passwort wiederholen"), { target: { value: "correct-horse-battery" } });
    fireEvent.click(screen.getByRole("button", { name: "Konto erstellen und beitreten" }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/operator");
    });
  });
});
