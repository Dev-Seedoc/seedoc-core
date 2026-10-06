import { useTranslation } from "react-i18next";

// Product name only; real screens take their text from i18n (M0-B2).
export function ShellPlaceholder() {
  const { t } = useTranslation();

  return (
    <main className="flex min-h-svh items-center justify-center">
      <h1 className="text-2xl font-semibold tracking-tight">{t("common.appName")}</h1>
    </main>
  );
}
