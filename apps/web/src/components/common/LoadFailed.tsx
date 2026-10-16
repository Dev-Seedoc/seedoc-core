import { TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/common/EmptyState";
import { Button } from "@/components/ui/button";

// A list that could not be loaded, with a retry button. `title` is already translated by the caller.
export function LoadFailed({ title, onRetry }: { title: string; onRetry: () => void }) {
  const { t } = useTranslation();
  return (
    <EmptyState
      icon={TriangleAlert}
      title={title}
      action={
        <Button variant="outline" onClick={onRetry}>
          {t("common.actions.retry")}
        </Button>
      }
    />
  );
}
