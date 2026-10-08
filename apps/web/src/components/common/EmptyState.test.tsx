import { render, screen } from "@testing-library/react";
import { FileText } from "lucide-react";
import { describe, expect, it } from "vitest";

import { Button } from "@/components/ui/button";

import { EmptyState } from "./EmptyState";

describe("EmptyState", () => {
  it("shows title, description and action", () => {
    render(
      <EmptyState
        icon={FileText}
        title="Noch keine Dokumente"
        description="Laden Sie Ihr erstes Dokument hoch."
        action={<Button>Hochladen</Button>}
      />,
    );

    expect(screen.getByRole("heading", { name: "Noch keine Dokumente" })).toBeInTheDocument();
    expect(screen.getByText("Laden Sie Ihr erstes Dokument hoch.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hochladen" })).toBeInTheDocument();
  });

  it("renders with a title only", () => {
    render(<EmptyState title="Keine Einträge" />);

    expect(screen.getByRole("heading", { name: "Keine Einträge" })).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
