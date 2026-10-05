import { createBrowserRouter, type RouteObject } from "react-router";

import { ShellPlaceholder } from "@/components/layout/ShellPlaceholder";

// Route areas (ARCHITECTURE §6, NAMING §7): manufacturer app, portal (/m, /s), operator (/operator), staff (/staff).
// Pages are added per roadmap task; until then every path renders the placeholder shell.
export const routes: RouteObject[] = [{ path: "*", element: <ShellPlaceholder /> }];

export const router = createBrowserRouter(routes);
