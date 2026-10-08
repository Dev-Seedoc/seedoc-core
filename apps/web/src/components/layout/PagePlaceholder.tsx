import { Construction } from "lucide-react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/common/EmptyState";

// Stands in for a manufacturer page until its roadmap task builds the real one.
export function PagePlaceholder() {
  const { t } = useTranslation();

  return (
    <EmptyState
      icon={Construction}
      title={t("shell.placeholder.title")}
      description={t("shell.placeholder.description")}
    />
  );
}
