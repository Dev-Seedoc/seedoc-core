import type { TFunction } from "i18next";

// `handle` of a route in router.tsx. `crumb` gives the breadcrumb label for that route.
export interface RouteHandle {
  crumb?: (t: TFunction) => string;
}

export function isRouteHandle(handle: unknown): handle is RouteHandle {
  return typeof handle === "object" && handle !== null && "crumb" in handle && typeof handle.crumb === "function";
}
