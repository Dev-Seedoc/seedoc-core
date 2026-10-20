import { fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter, Outlet, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RouteErrorPage } from "./RouteErrorPage";

function CrashingPage(): never {
  throw new Error("Failed to execute 'insertBefore' on 'Node'");
}

function Frame() {
  return (
    <div>
      <nav aria-label="Menü">Menü</nav>
      <Outlet />
    </div>
  );
}

describe("RouteErrorPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("replaces a crashing page inside the frame and reloads on request", async () => {
    // React reports caught render errors on the console; that is expected here.
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const reload = vi.fn();
    vi.stubGlobal("location", { reload });
    const router = createMemoryRouter(
      [
        {
          errorElement: <RouteErrorPage isFullScreen />,
          children: [
            {
              path: "/",
              element: <Frame />,
              children: [{ errorElement: <RouteErrorPage />, children: [{ index: true, element: <CrashingPage /> }] }],
            },
          ],
        },
      ],
      { initialEntries: ["/"] },
    );

    render(<RouterProvider router={router} />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Etwas ist schiefgelaufen");
    expect(alert).not.toHaveTextContent("insertBefore");
    expect(screen.getByRole("navigation", { name: "Menü" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Neu laden" }));
    expect(reload).toHaveBeenCalledOnce();
  });
});
