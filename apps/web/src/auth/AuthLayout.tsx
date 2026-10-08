import { useTranslation } from "react-i18next";
import { Outlet } from "react-router";

// Frame of the pages before login (login, password reset, invitation): a centred card, no app navigation.
export function AuthLayout() {
  const { t } = useTranslation();

  return (
    <div className="bg-muted/40 flex min-h-svh flex-col items-center justify-center gap-6 p-6">
      <div className="text-2xl font-semibold tracking-tight">{t("common.appName")}</div>
      <main className="bg-background w-full max-w-sm rounded-lg border p-6 shadow-sm">
        <Outlet />
      </main>
    </div>
  );
}
