import { fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiError, renderRoute, stubApi } from "@/test/renderRoute";

const RESET = "POST /api/v1/auth/password-reset/confirm";

function fillAndSubmit(password: string, passwordRepeat: string) {
  fireEvent.change(screen.getByLabelText("Neues Passwort"), { target: { value: password } });
  fireEvent.change(screen.getByLabelText("Passwort wiederholen"), { target: { value: passwordRepeat } });
  fireEvent.click(screen.getByRole("button", { name: "Passwort speichern" }));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ResetPasswordPage", () => {
  it("rejects a password shorter than 12 characters", async () => {
    const fetchMock = stubApi({});
    renderRoute("/reset-password/reset-token");

    fillAndSubmit("too-short", "too-short");

    expect(await screen.findByText("Das Passwort muss zwischen 12 und 128 Zeichen lang sein.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects passwords that do not match", async () => {
    const fetchMock = stubApi({});
    renderRoute("/reset-password/reset-token");

    fillAndSubmit("correct-horse-battery", "correct-horse-battary");

    expect(await screen.findByText("Die Passwörter stimmen nicht überein.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sends token and password and confirms the change", async () => {
    const fetchMock = stubApi({ [RESET]: { status: 204 } });
    renderRoute("/reset-password/reset-token");

    fillAndSubmit("correct-horse-battery", "correct-horse-battery");

    expect(await screen.findByRole("heading", { name: "Ihr Passwort wurde geändert" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Zur Anmeldung" })).toHaveAttribute("href", "/login");
    expect(await fetchMock.mock.calls[0]?.[0].json()).toEqual({
      token: "reset-token",
      password: "correct-horse-battery",
    });
  });

  it("offers a new link when the token has expired", async () => {
    stubApi({ [RESET]: apiError(410, "invitation_invalid") });
    renderRoute("/reset-password/old-token");

    fillAndSubmit("correct-horse-battery", "correct-horse-battery");

    expect(
      await screen.findByRole("heading", { name: "Dieser Link ist ungültig oder abgelaufen" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Neuen Link anfordern" })).toHaveAttribute("href", "/forgot-password");
  });
});
