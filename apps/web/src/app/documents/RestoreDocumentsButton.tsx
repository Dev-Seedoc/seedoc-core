import { ArchiveRestore } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { useRestoreDocument } from "@/lib/api/hooks/documents";
import type { DocumentListItem } from "@/lib/api/types";

interface RestoreDocumentsButtonProps {
  tenantId: string;
  documents: DocumentListItem[];
  // In a table row: one document, its title in the accessible name.
  inRow?: boolean;
  // Called with the documents that could not be restored, so they stay selected for another try.
  onDone?: (failedIds: string[]) => void;
}

// Takes documents out of the trash. No confirmation: restoring changes nothing irreversibly.
export function RestoreDocumentsButton({ tenantId, documents, inRow = false, onDone }: RestoreDocumentsButtonProps) {
  const { t } = useTranslation();
  const restore = useRestoreDocument(tenantId);

  function handleRestore() {
    restore.mutate(
      documents.map((document) => document.id),
      {
        onSuccess: ({ succeeded, failed }) => {
          if (failed.length === 0) {
            toast.success(t("documents.trash.restored", { count: succeeded.length }));
          } else {
            toast.error(t("documents.trash.partlyRestored", { restored: succeeded.length, failed: failed.length }));
          }
          onDone?.(failed);
        },
      },
    );
  }

  return (
    <Button
      variant={inRow ? "ghost" : "outline"}
      size="sm"
      disabled={restore.isPending}
      aria-label={inRow && documents[0] ? t("documents.trash.restoreRow", { title: documents[0].title }) : undefined}
      onClick={handleRestore}
    >
      <ArchiveRestore aria-hidden="true" />
      {t("documents.trash.restore")}
    </Button>
  );
}
