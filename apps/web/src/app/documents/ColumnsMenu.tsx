import { Columns3 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

import type { DocumentColumn } from "./documentColumns";
import { HIDEABLE_DOCUMENT_COLUMNS } from "./useHiddenDocumentColumns";

interface ColumnsMenuProps {
  hiddenColumns: DocumentColumn[];
  // Columns that make no sense right now (the folder column inside a folder): not offered.
  unavailableColumns?: DocumentColumn[];
  onChange: (column: DocumentColumn, visible: boolean) => void;
}

export function ColumnsMenu({ hiddenColumns, unavailableColumns = [], onChange }: ColumnsMenuProps) {
  const { t } = useTranslation();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm">
          <Columns3 aria-hidden="true" />
          {t("documents.columns.label")}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>{t("documents.columns.title")}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {HIDEABLE_DOCUMENT_COLUMNS.filter((column) => !unavailableColumns.includes(column)).map((column) => (
          <DropdownMenuCheckboxItem
            key={column}
            checked={!hiddenColumns.includes(column)}
            // Keep the menu open, so several columns can be switched in one go.
            onSelect={(event) => {
              event.preventDefault();
            }}
            onCheckedChange={(checked) => {
              onChange(column, checked);
            }}
          >
            {t(`documents.table.${column}`)}
          </DropdownMenuCheckboxItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
