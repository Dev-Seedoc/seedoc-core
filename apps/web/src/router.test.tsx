import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it } from "vitest";

import { routes } from "./router";

describe("router", () => {
  it("renders the shell for any path", () => {
    const router = createMemoryRouter(routes, { initialEntries: ["/m/some-token"] });

    render(<RouterProvider router={router} />);

    expect(screen.getByRole("heading", { name: "SeeDoc" })).toBeInTheDocument();
  });
});
