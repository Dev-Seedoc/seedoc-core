import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MeRead } from "@/lib/api/types";
import { apiError, renderRoute, stubApi, TEST_ME } from "@/test/renderRoute";

const STAFF: MeRead = { ...TEST_ME, is_staff: true, mfa_verified: true };
const STAFF_NEEDS_TOTP: MeRead = { ...STAFF, mfa_verified: false };
const VERIFY = "POST /api/v1/auth/totp/verify";
const SETUP = "POST /api/v1/auth/totp/setup";

function enterCode(code: string) {
  fireEvent.change(screen.getByLabelText("Bestätigungscode"), { target: { value: code } });
  fireEvent.click(screen.getByRole("button", { name: "Bestätigen" }));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("StaffLayout", () => {
  it("sends logged-out visitors to the login page", async () => {
    stubApi({ "GET /api/v1/auth/me": apiError(401, "unauthenticated") });

    const router = renderRoute("/staff");

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/login");
    });
  });

  it("sends members who are not staff to the app", () => {
    const router = renderRoute("/staff", TEST_ME);

    expect(router.state.location.pathname).toBe("/");
  });

  it("shows the staff console to verified staff", () => {
    renderRoute("/staff", STAFF);

    expect(screen.getByRole("navigation", { name: "Navigation SeeDoc-Team" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Hersteller" })).toHaveAttribute("href", "/staff");
    expect(screen.getByRole("link", { name: "Zur Anwendung" })).toHaveAttribute("href", "/");
  });

  it("asks staff for a TOTP code before showing anything", () => {
    renderRoute("/staff", STAFF_NEEDS_TOTP);

    expect(screen.getByRole("heading", { name: "Bestätigungscode eingeben" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Navigation SeeDoc-Team" })).not.toBeInTheDocument();
  });
});

describe("TotpScreen", () => {
  it("rejects a code that is not 6 digits and sends nothing", async () => {
    const fetchMock = stubApi({});
    renderRoute("/staff", STAFF_NEEDS_TOTP);

    enterCode("12345");

    expect(await screen.findByText("Bitte geben Sie den 6-stelligen Code ein.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("says the code is wrong instead of mentioning e-mail and password", async () => {
    stubApi({ [VERIFY]: apiError(401, "invalid_credentials") });
    renderRoute("/staff", STAFF_NEEDS_TOTP);

    enterCode("123456");

    expect(await screen.findByRole("alert")).toHaveTextContent("Der Code ist falsch oder abgelaufen.");
  });

  it("opens the console after a correct code", async () => {
    const fetchMock = stubApi({ [VERIFY]: { status: 204 }, "GET /api/v1/auth/me": { status: 200, body: STAFF } });
    renderRoute("/staff", STAFF_NEEDS_TOTP);

    enterCode("123 456");

    expect(await screen.findByRole("navigation", { name: "Navigation SeeDoc-Team" })).toBeInTheDocument();
    const verifyRequest = fetchMock.mock.calls.find(([request]) => request.url.endsWith("/totp/verify"))?.[0];
    expect(await verifyRequest?.json()).toEqual({ code: "123456" });
  });

  it("shows the key in blocks of four during setup", async () => {
    stubApi({
      [SETUP]: {
        status: 200,
        body: { otpauth_uri: "otpauth://totp/SeeDoc:staff@example.com?secret=JBSWY3DPEHPK3PXP&issuer=SeeDoc" },
      },
    });
    renderRoute("/staff", STAFF_NEEDS_TOTP);

    fireEvent.click(screen.getByRole("button", { name: "Jetzt einrichten" }));
    expect(screen.getByRole("heading", { name: "Zwei-Faktor-Authentifizierung einrichten" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Einrichtung starten" }));

    expect(await screen.findByText("JBSW Y3DP EHPK 3PXP")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "In Authenticator-App öffnen" })).toHaveAttribute(
      "href",
      "otpauth://totp/SeeDoc:staff@example.com?secret=JBSWY3DPEHPK3PXP&issuer=SeeDoc",
    );
    expect(screen.getByLabelText("Bestätigungscode")).toBeInTheDocument();
  });

  it("goes back to code entry when TOTP is already set up", async () => {
    stubApi({ [SETUP]: apiError(409, "conflict") });
    renderRoute("/staff", STAFF_NEEDS_TOTP);

    fireEvent.click(screen.getByRole("button", { name: "Jetzt einrichten" }));
    fireEvent.click(screen.getByRole("button", { name: "Einrichtung starten" }));

    expect(await screen.findByText(/bereits eingerichtet/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Bestätigungscode eingeben" })).toBeInTheDocument();
  });

  it("switches to setup when the account has no TOTP yet", async () => {
    stubApi({ [VERIFY]: apiError(409, "conflict") });
    renderRoute("/staff", STAFF_NEEDS_TOTP);

    enterCode("123456");

    expect(
      await screen.findByRole("heading", { name: "Zwei-Faktor-Authentifizierung einrichten" }),
    ).toBeInTheDocument();
  });
});
