import { fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderRoute, stubApi } from "@/test/renderRoute";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ForgotPasswordPage", () => {
  it("shows a German error for an invalid e-mail address", async () => {
    const fetchMock = stubApi({});
    renderRoute("/forgot-password");

    fireEvent.change(screen.getByLabelText("E-Mail-Adresse"), { target: { value: "not-an-email" } });
    fireEvent.click(screen.getByRole("button", { name: "Link senden" }));

    expect(await screen.findByText("Bitte geben Sie eine gültige E-Mail-Adresse ein.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sends only the e-mail and always shows the same confirmation", async () => {
    const fetchMock = stubApi({ "POST /api/v1/auth/password-reset": { status: 202 } });
    renderRoute("/forgot-password");

    fireEvent.change(screen.getByLabelText("E-Mail-Adresse"), { target: { value: "someone@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Link senden" }));

    expect(await screen.findByRole("heading", { name: "Bitte prüfen Sie Ihr Postfach" })).toBeInTheDocument();
    expect(screen.getByText(/Falls ein Konto mit dieser E-Mail-Adresse existiert/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Zurück zur Anmeldung" })).toHaveAttribute("href", "/login");
    expect(await fetchMock.mock.calls[0]?.[0].json()).toEqual({ email: "someone@example.com" });
  });
});
