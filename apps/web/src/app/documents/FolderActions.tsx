import { Ellipsis, FolderPlus, Pencil, Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { getErrorCode, getErrorMessage } from "@/lib/api/errors";
import { useDeleteFolder } from "@/lib/api/hooks/documents";
import type { FolderRead } from "@/lib/api/types";

interface FolderActionsProps {
  tenantId: string;
  folder: FolderRead;
  onCreateSubfolder: () => void;
  onEdit: () => void;
  onDeleted: (folder: FolderRead) => void;
}

// Actions of the selected folder. They sit next to its heading, not inside the tree: a button inside a tree row
// would be unreachable with the tree's arrow keys and confuse screen readers (WAI-ARIA tree view).
export function FolderActions({ tenantId, folder, onCreateSubfolder, onEdit, onDeleted }: FolderActionsProps) {
  const { t } = useTranslation();
  const deleteFolder = useDeleteFolder(tenantId);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);

  function handleDelete() {
    deleteFolder.mutate(folder.id, {
      onSuccess: () => {
        toast.success(t("documents.folderActions.deleted"));
        setIsConfirmOpen(false);
        onDeleted(folder);
      },
      onError: (error) => {
        // API.md §3.2: only an empty folder can be deleted (trashed documents count too).
        toast.error(
          getErrorCode(error) === "conflict" ? t("documents.folderActions.notEmpty") : getErrorMessage(error),
        );
        setIsConfirmOpen(false);
      },
    });
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="icon" aria-label={t("documents.folderActions.label")}>
            <Ellipsis aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={onCreateSubfolder}>
            <FolderPlus aria-hidden="true" />
            {t("documents.folderActions.createSubfolder")}
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={onEdit}>
            <Pencil aria-hidden="true" />
            {t("common.actions.edit")}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            variant="destructive"
            onSelect={() => {
              setIsConfirmOpen(true);
            }}
          >
            <Trash2 aria-hidden="true" />
            {t("common.actions.delete")}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <ConfirmDialog
        open={isConfirmOpen}
        onOpenChange={setIsConfirmOpen}
        title={t("documents.folderActions.deleteTitle", { name: folder.name })}
        description={t("documents.folderActions.deleteDescription")}
        confirmLabel={t("common.actions.delete")}
        variant="destructive"
        isPending={deleteFolder.isPending}
        onConfirm={handleDelete}
      />
    </>
  );
}
