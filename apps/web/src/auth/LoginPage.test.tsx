import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiError, renderRoute, stubApi, TEST_ME } from "@/test/renderRoute";

const LOGGED_OUT = { "GET /api/v1/auth/me": apiError(401, "unauthenticated") };

function fillAndSubmit(email: string, password: string) {
  fireEvent.change(screen.getByLabelText("E-Mail-Adresse"), { target: { value: email } });
  fireEvent.change(screen.getByLabelText("Passwort"), { target: { value: password } });
  fireEvent.click(screen.getByRole("button", { name: "Anmelden" }));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("LoginPage", () => {
  it("shows German field errors and sends nothing when the form is empty", async () => {
    const fetchMock = stubApi(LOGGED_OUT);
    renderRoute("/login");

    fireEvent.click(await screen.findByRole("button", { name: "Anmelden" }));

    expect(await screen.findByText("Bitte geben Sie eine gültige E-Mail-Adresse ein.")).toBeInTheDocument();
    expect(screen.getByText("Bitte geben Sie Ihr Passwort ein.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([request]) => request.method === "POST")).toBe(false);
  });

  it("shows a wrong password inline", async () => {
    stubApi({ ...LOGGED_OUT, "POST /api/v1/auth/login": apiError(401, "invalid_credentials") });
    renderRoute("/login");

    fillAndSubmit("owner@example.com", "wrong-password-123");

    expect(await screen.findByRole("alert")).toHaveTextContent("Ungültige E-Mail-Adresse oder falsches Passwort.");
  });

  it("shows the rate limit inline", async () => {
    stubApi({
      ...LOGGED_OUT,
      "POST /api/v1/auth/login": apiError(429, "rate_limited", { retry_after_seconds: 900 }),
    });
    renderRoute("/login");

    fillAndSubmit("owner@example.com", "wrong-password-123");

    expect(await screen.findByRole("alert")).toHaveTextContent("Zu viele Anfragen.");
  });

  it("sends the credentials and returns to the page the user wanted", async () => {
    const fetchMock = stubApi({ ...LOGGED_OUT, "POST /api/v1/auth/login": { status: 200, body: TEST_ME } });
    const router = renderRoute({ pathname: "/login", state: { from: { pathname: "/documents" } } });

    fillAndSubmit("owner@example.com", "correct-horse-battery");

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/documents");
    });
    const loginRequest = fetchMock.mock.calls.find(([request]) => request.method === "POST")?.[0];
    expect(await loginRequest?.json()).toEqual({ email: "owner@example.com", password: "correct-horse-battery" });
  });

  it("goes to the overview after login without a remembered page", async () => {
    stubApi({ ...LOGGED_OUT, "POST /api/v1/auth/login": { status: 200, body: TEST_ME } });
    const router = renderRoute("/login");

    fillAndSubmit("owner@example.com", "correct-horse-battery");

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/");
    });
  });

  it("sends a logged-in user away from the login page", () => {
    const router = renderRoute("/login", TEST_ME);

    expect(router.state.location.pathname).toBe("/");
  });
});
