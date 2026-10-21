import { createBrowserRouter, type RouteObject } from "react-router";

import { CustomerDetailPage } from "@/app/customers/CustomerDetailPage";
import { CustomersPage } from "@/app/customers/CustomersPage";
import { DocumentDetailPage } from "@/app/documents/DocumentDetailPage";
import { DocumentsPage } from "@/app/documents/DocumentsPage";
import { ProductDetailPage } from "@/app/products/ProductDetailPage";
import { ProductsPage } from "@/app/products/ProductsPage";
import { AcceptInvitationPage } from "@/auth/AcceptInvitationPage";
import { AuthLayout } from "@/auth/AuthLayout";
import { ForgotPasswordPage } from "@/auth/ForgotPasswordPage";
import { LoginPage } from "@/auth/LoginPage";
import { ResetPasswordPage } from "@/auth/ResetPasswordPage";
import { AppLayout } from "@/components/layout/AppLayout";
import { PagePlaceholder } from "@/components/layout/PagePlaceholder";
import { RouteErrorPage } from "@/components/layout/RouteErrorPage";
import type { RouteHandle } from "@/components/layout/routeHandle";
import { ShellPlaceholder } from "@/components/layout/ShellPlaceholder";
import { StaffLayout } from "@/staff/StaffLayout";
import { StaffTenantDetailPage } from "@/staff/StaffTenantDetailPage";
import { StaffTenantsPage } from "@/staff/StaffTenantsPage";

// Route areas (ARCHITECTURE §6, NAMING §7): manufacturer app inside AppLayout; portal (/m, /s), operator (/operator),
// staff (/staff) and auth pages never get the manufacturer frame. Placeholders are replaced per roadmap task.
export const routes: RouteObject[] = [
  {
    // Anything that crashes outside a manufacturer page (a layout, auth, staff, portal) gets the full-screen error page.
    errorElement: <RouteErrorPage isFullScreen />,
    children: [
      {
        path: "/",
        element: <AppLayout />,
        handle: { crumb: (t) => t("shell.nav.dashboard") } satisfies RouteHandle,
        children: [
          {
            // A crashing page is replaced inside the frame, so the menu stays usable.
            errorElement: <RouteErrorPage />,
            children: [
              { index: true, element: <PagePlaceholder /> },
              {
                path: "documents",
                handle: { crumb: (t) => t("shell.nav.documents") } satisfies RouteHandle,
                children: [
                  { index: true, element: <DocumentsPage /> },
                  // Nested, so the breadcrumb reads "Übersicht › Dokumente › Dokument".
                  {
                    path: ":documentId",
                    element: <DocumentDetailPage />,
                    handle: { crumb: (t) => t("documents.detail.crumb") } satisfies RouteHandle,
                  },
                ],
              },
              {
                path: "products",
                handle: { crumb: (t) => t("shell.nav.products") } satisfies RouteHandle,
                children: [
                  { index: true, element: <ProductsPage /> },
                  {
                    path: ":productId",
                    element: <ProductDetailPage />,
                    handle: { crumb: (t) => t("products.detail.crumb") } satisfies RouteHandle,
                  },
                ],
              },
              {
                path: "customers",
                handle: { crumb: (t) => t("shell.nav.customers") } satisfies RouteHandle,
                children: [
                  { index: true, element: <CustomersPage /> },
                  {
                    path: ":customerId",
                    element: <CustomerDetailPage />,
                    handle: { crumb: (t) => t("customers.detail.crumb") } satisfies RouteHandle,
                  },
                ],
              },
              // DeliveryWorkspacePage comes with the second half of M2-B6 (after H-15); the links already lead here.
              {
                path: "deliveries/:deliveryId",
                element: <PagePlaceholder />,
                handle: { crumb: (t) => t("deliveries.detail.crumb") } satisfies RouteHandle,
              },
              {
                path: "settings",
                element: <PagePlaceholder />,
                handle: { crumb: (t) => t("shell.nav.settings") } satisfies RouteHandle,
              },
            ],
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
      {
        path: "/staff",
        element: <StaffLayout />,
        children: [
          { index: true, element: <StaffTenantsPage /> },
          { path: "tenants/:tenantId", element: <StaffTenantDetailPage /> },
        ],
      },
      { path: "*", element: <ShellPlaceholder /> },
    ],
  },
];

export const router = createBrowserRouter(routes);
