import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it.each([
    ["ready", "Bereit", "success"],
    ["processing", "In Bearbeitung", "progress"],
    ["failed", "Fehlgeschlagen", "danger"],
    ["draft", "Entwurf", "neutral"],
  ] as const)("shows %s as the German label %s", (status, label, tone) => {
    render(<StatusBadge status={status} />);

    const badge = screen.getByText(label);
    expect(badge).toHaveAttribute("data-tone", tone);
  });
});
