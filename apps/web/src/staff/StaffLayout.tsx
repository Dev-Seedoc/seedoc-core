import { Loader2, TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link, Navigate, NavLink, Outlet, useLocation } from "react-router";

import { EmptyState } from "@/components/common/EmptyState";
import { FullScreen } from "@/components/layout/FullScreen";
import { UserMenu } from "@/components/layout/UserMenu";
import { Button } from "@/components/ui/button";
import { getErrorCode } from "@/lib/api/errors";
import { useMe } from "@/lib/api/hooks/auth";
import { cn } from "@/lib/utils";

import { TotpScreen } from "./TotpScreen";

// Frame of the staff console (ARCHITECTURE §6: bare). Only staff whose session is confirmed with TOTP see a page;
// the API enforces the same (`/staff` answers 401 mfa_required), this guard only decides what to show.
export function StaffLayout() {
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

  if (!me.is_staff) {
    return <Navigate to="/" replace />;
  }

  if (!me.mfa_verified) {
    return <TotpScreen />;
  }

  return (
    <div className="flex min-h-svh flex-col">
      <header className="bg-background flex h-14 shrink-0 items-center justify-between gap-4 border-b px-6">
        <div className="flex items-center gap-6">
          <span className="text-lg font-semibold tracking-tight">
            {t("common.appName")} <span className="text-muted-foreground font-normal">· {t("staff.layout.title")}</span>
          </span>
          <nav aria-label={t("staff.nav.label")} className="flex items-center gap-1">
            <NavLink
              to="/staff"
              className={({ isActive }) =>
                cn(
                  "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                  isActive ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:text-foreground",
                )
              }
            >
              {t("staff.nav.tenants")}
            </NavLink>
          </nav>
        </div>
        <div className="flex items-center gap-2">
          {me.memberships.length > 0 && (
            <Button asChild variant="ghost" size="sm">
              <Link to="/">{t("staff.nav.backToApp")}</Link>
            </Button>
          )}
          <UserMenu />
        </div>
      </header>
      <main className="flex-1 p-6">
        <Outlet />
      </main>
    </div>
  );
}
