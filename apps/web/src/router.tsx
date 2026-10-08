import { createBrowserRouter, type RouteObject } from "react-router";

import { AcceptInvitationPage } from "@/auth/AcceptInvitationPage";
import { AuthLayout } from "@/auth/AuthLayout";
import { ForgotPasswordPage } from "@/auth/ForgotPasswordPage";
import { LoginPage } from "@/auth/LoginPage";
import { ResetPasswordPage } from "@/auth/ResetPasswordPage";
import { AppLayout } from "@/components/layout/AppLayout";
import { PagePlaceholder } from "@/components/layout/PagePlaceholder";
import type { RouteHandle } from "@/components/layout/routeHandle";
import { ShellPlaceholder } from "@/components/layout/ShellPlaceholder";

// Route areas (ARCHITECTURE §6, NAMING §7): manufacturer app inside AppLayout; portal (/m, /s), operator (/operator),
// staff (/staff) and auth pages never get the manufacturer frame. Placeholders are replaced per roadmap task.
export const routes: RouteObject[] = [
  {
    path: "/",
    element: <AppLayout />,
    handle: { crumb: (t) => t("shell.nav.dashboard") } satisfies RouteHandle,
    children: [
      { index: true, element: <PagePlaceholder /> },
      {
        path: "documents",
        element: <PagePlaceholder />,
        handle: { crumb: (t) => t("shell.nav.documents") } satisfies RouteHandle,
      },
      {
        path: "products",
        element: <PagePlaceholder />,
        handle: { crumb: (t) => t("shell.nav.products") } satisfies RouteHandle,
      },
      {
        path: "customers",
        element: <PagePlaceholder />,
        handle: { crumb: (t) => t("shell.nav.customers") } satisfies RouteHandle,
      },
      {
        path: "settings",
        element: <PagePlaceholder />,
        handle: { crumb: (t) => t("shell.nav.settings") } satisfies RouteHandle,
      },
    ],
  },
  {
    element: <AuthLayout />,
    children: [
      { path: "/login", element: <LoginPage /> },
      { path: "/forgot-password", element: <ForgotPasswordPage /> },
      { path: "/reset-password/:token", element: <ResetPasswordPage /> },
      { path: "/invite/:token", element: <AcceptInvitationPage /> },
    ],
  },
  { path: "*", element: <ShellPlaceholder /> },
];

export const router = createBrowserRouter(routes);
