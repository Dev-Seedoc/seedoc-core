import { TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/common/EmptyState";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface RouteErrorPageProps {
  // Outside any layout the page fills the screen; inside AppLayout it fills the content area and keeps the menu.
  isFullScreen?: boolean;
}

// Shown instead of React Router's raw error screen when a page crashes while rendering (for example when browser
// page translation changes the DOM under React). Reloading starts the page fresh.
export function RouteErrorPage({ isFullScreen = false }: RouteErrorPageProps) {
  const { t } = useTranslation();

  return (
    <div role="alert" className={cn("flex items-center justify-center p-6", isFullScreen && "min-h-svh")}>
      <EmptyState
        icon={TriangleAlert}
        title={t("shell.errorPage.title")}
        description={t("shell.errorPage.description")}
        action={
          <Button
            onClick={() => {
              window.location.reload();
            }}
          >
            {t("shell.errorPage.reload")}
          </Button>
        }
      />
    </div>
  );
}
