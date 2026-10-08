import { Building2, Loader2, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, Outlet, useLocation } from "react-router";

import { EmptyState } from "@/components/common/EmptyState";
import { Button } from "@/components/ui/button";
import { getErrorCode } from "@/lib/api/errors";
import { useMe } from "@/lib/api/hooks/auth";

import { AppSidebar } from "./AppSidebar";
import { TopBar } from "./TopBar";

function FullScreen({ children }: { children: ReactNode }) {
  return <div className="flex min-h-svh items-center justify-center p-6">{children}</div>;
}

// Frame of the manufacturer app (ARCHITECTURE §6: sidebar layout, desktop-first). Pages render in <Outlet />.
// Only users with at least one tenant membership see it; everyone else is sent where they belong.
export function AppLayout() {
  const { t } = useTranslation();
  const location = useLocation();
  const { data: me, error, isPending, refetch } = useMe();

  if (isPending) {
    return (
      <FullScreen>
        <Loader2 className="text-muted-foreground size-6 animate-spin" aria-hidden="true" />
        <span className="sr-only">{t("shell.loading")}</span>
      </FullScreen>
    );
  }

  if (error) {
    if (getErrorCode(error) === "unauthenticated") {
      // `from` lets the login page (M0-B5) send the user back after logging in.
      return <Navigate to="/login" replace state={{ from: location }} />;
    }
    return (
      <FullScreen>
        <EmptyState
          icon={TriangleAlert}
          title={t("shell.loadFailed.title")}
          description={t(`errors.${getErrorCode(error)}`)}
          action={<Button onClick={() => void refetch()}>{t("common.actions.retry")}</Button>}
        />
      </FullScreen>
    );
  }

  if (me.memberships.length === 0) {
    if (me.is_staff) {
      return <Navigate to="/staff" replace />;
    }
    if (me.operator_orgs.length > 0) {
      return <Navigate to="/operator" replace />;
    }
    return (
      <FullScreen>
        <EmptyState icon={Building2} title={t("shell.noTenant.title")} description={t("shell.noTenant.description")} />
      </FullScreen>
    );
  }

  return (
    <div className="flex min-h-svh">
      <AppSidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
