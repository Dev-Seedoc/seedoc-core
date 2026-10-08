import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiError, stubApi } from "@/test/renderRoute";

import { ReauthDialog } from "./ReauthDialog";

const REAUTH = "POST /api/v1/auth/reauth";

function renderDialog() {
  const onSuccess = vi.fn();
  const onOpenChange = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ReauthDialog open onOpenChange={onOpenChange} onSuccess={onSuccess} />
    </QueryClientProvider>,
  );
  return { onSuccess, onOpenChange };
}

function submitPassword(password: string) {
  fireEvent.change(screen.getByLabelText("Passwort"), { target: { value: password } });
  fireEvent.click(screen.getByRole("button", { name: "Bestätigen" }));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ReauthDialog", () => {
  it("closes and calls onSuccess after the right password", async () => {
    const fetchMock = stubApi({ [REAUTH]: { status: 204 } });
    const { onSuccess, onOpenChange } = renderDialog();

    expect(screen.getByRole("alertdialog", { name: "Bitte bestätigen Sie Ihr Passwort" })).toBeInTheDocument();
    submitPassword("correct-horse-battery");

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalledOnce();
    });
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(await fetchMock.mock.calls[0]?.[0].json()).toEqual({ password: "correct-horse-battery" });
  });

  it("shows a wrong password inside the dialog and does not continue", async () => {
    stubApi({ [REAUTH]: apiError(401, "invalid_credentials") });
    const { onSuccess, onOpenChange } = renderDialog();

    submitPassword("wrong-password-123");

    expect(await screen.findByRole("alert")).toHaveTextContent("Ungültige E-Mail-Adresse oder falsches Passwort.");
    expect(onSuccess).not.toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it("closes on Abbrechen without sending anything", () => {
    const fetchMock = stubApi({});
    const { onSuccess, onOpenChange } = renderDialog();

    fireEvent.click(screen.getByRole("button", { name: "Abbrechen" }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(onSuccess).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
