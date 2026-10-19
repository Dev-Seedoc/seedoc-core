import { Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { useTrashDocument } from "@/lib/api/hooks/documents";
import type { DocumentListItem } from "@/lib/api/types";

interface MoveToTrashButtonProps {
  tenantId: string;
  documents: DocumentListItem[];
  // Called with the documents that could not be moved, so they stay selected for another try.
  onDone: (failedIds: string[]) => void;
}

// "In den Papierkorb" for the selected documents, after a confirmation (BUSINESS_RULES §3: restorable for 30 days,
// releases keep their frozen version).
export function MoveToTrashButton({ tenantId, documents, onDone }: MoveToTrashButtonProps) {
  const { t } = useTranslation();
  const trash = useTrashDocument(tenantId);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const count = documents.length;

  function handleConfirm() {
    trash.mutate(
      documents.map((document) => document.id),
      {
        onSuccess: ({ succeeded, failed }) => {
          if (failed.length === 0) {
            toast.success(t("documents.trash.moved", { count: succeeded.length }));
          } else {
            toast.error(t("documents.trash.partlyMoved", { moved: succeeded.length, failed: failed.length }));
          }
          setIsConfirmOpen(false);
          onDone(failed);
        },
      },
    );
  }

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        onClick={() => {
          setIsConfirmOpen(true);
        }}
      >
        <Trash2 aria-hidden="true" />
        {t("documents.trash.moveToTrash")}
      </Button>
      <ConfirmDialog
        open={isConfirmOpen}
        onOpenChange={setIsConfirmOpen}
        title={t("documents.trash.confirmTitle", { count })}
        description={t("documents.trash.confirmDescription")}
        confirmLabel={t("documents.trash.moveToTrash")}
        variant="destructive"
        isPending={trash.isPending}
        onConfirm={handleConfirm}
      />
    </>
  );
}
