import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ConfirmDialog } from "./ConfirmDialog";

function renderDialog(props: Partial<Parameters<typeof ConfirmDialog>[0]> = {}) {
  const onConfirm = vi.fn();
  const onOpenChange = vi.fn();
  render(
    <ConfirmDialog
      open
      onOpenChange={onOpenChange}
      title="Dokument löschen?"
      description="Das Dokument wird in den Papierkorb verschoben."
      onConfirm={onConfirm}
      {...props}
    />,
  );
  return { onConfirm, onOpenChange };
}

describe("ConfirmDialog", () => {
  it("shows title, description and the default German buttons", () => {
    renderDialog();

    expect(screen.getByRole("alertdialog", { name: "Dokument löschen?" })).toBeInTheDocument();
    expect(screen.getByText("Das Dokument wird in den Papierkorb verschoben.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Abbrechen" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Bestätigen" })).toBeInTheDocument();
  });

  it("calls onConfirm and stays open until the caller closes it", () => {
    const { onConfirm, onOpenChange } = renderDialog({ confirmLabel: "Löschen", variant: "destructive" });

    fireEvent.click(screen.getByRole("button", { name: "Löschen" }));

    expect(onConfirm).toHaveBeenCalledOnce();
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it("closes on Abbrechen without confirming", () => {
    const { onConfirm, onOpenChange } = renderDialog();

    fireEvent.click(screen.getByRole("button", { name: "Abbrechen" }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("disables both buttons while the action runs", () => {
    renderDialog({ isPending: true });

    expect(screen.getByRole("button", { name: "Abbrechen" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Bestätigen" })).toBeDisabled();
  });
});
