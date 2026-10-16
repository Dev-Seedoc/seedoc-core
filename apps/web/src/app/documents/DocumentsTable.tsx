import { createColumnHelper, flexRender, getCoreRowModel, useReactTable } from "@tanstack/react-table";
import type { TFunction } from "i18next";
import { FileText, SearchX } from "lucide-react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { EmptyState } from "@/components/common/EmptyState";
import { LoadFailed } from "@/components/common/LoadFailed";
import { Spinner } from "@/components/common/Spinner";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useDocuments } from "@/lib/api/hooks/documents";
import type { DocumentListItem, ListDocumentsQuery } from "@/lib/api/types";
import { formatDateTime } from "@/lib/formatDate";
import { SUPPORTED_LANGUAGES } from "@/lib/languages";

import type { DocumentColumn } from "./documentColumns";

// A language code from the API as its German name; an unknown code is shown as it is.
function languageLabel(code: string, t: TFunction): string {
  const known = SUPPORTED_LANGUAGES.find((language) => language === code);
  return known ? t(`common.language.${known}`) : code;
}

const column = createColumnHelper<DocumentListItem>();
const EMPTY_CELL = <span className="text-muted-foreground">—</span>;

function createColumns(t: TFunction) {
  return [
    column.accessor("title", {
      id: "title",
      header: t("documents.table.title"),
      cell: ({ row }) => (
        <Link to={`/documents/${row.original.id}`} className="font-medium hover:underline">
          {row.original.title}
        </Link>
      ),
    }),
    column.accessor("doc_type", {
      id: "docType",
      header: t("documents.table.docType"),
      cell: ({ getValue }) => t(`common.docType.${getValue()}`),
    }),
    column.accessor("language", {
      id: "language",
      header: t("documents.table.language"),
      cell: ({ getValue }) => languageLabel(getValue(), t),
    }),
    column.accessor("access_level", {
      id: "accessLevel",
      header: t("documents.table.accessLevel"),
      cell: ({ getValue }) => t(`common.accessLevel.${getValue()}`),
    }),
    column.accessor("folder_path", {
      id: "folder",
      header: t("documents.table.folder"),
      cell: ({ getValue }) => <span className="text-muted-foreground">{getValue()}</span>,
    }),
    column.accessor("current_version_no", {
      id: "version",
      header: t("documents.table.version"),
      // null: a document without a current version (the API allows it); shown as a dash.
      cell: ({ getValue }) => {
        const no = getValue();
        return no === null ? (
          EMPTY_CELL
        ) : (
          <span className="tabular-nums">{t("documents.table.versionNo", { no })}</span>
        );
      },
    }),
    column.accessor("processing_status", {
      id: "status",
      header: t("documents.table.status"),
      cell: ({ getValue }) => {
        const status = getValue();
        return status === null ? EMPTY_CELL : <StatusBadge status={status} />;
      },
    }),
    column.accessor("updated_at", {
      id: "updatedAt",
      header: t("documents.table.updatedAt"),
      cell: ({ getValue }) => <span className="whitespace-nowrap tabular-nums">{formatDateTime(getValue())}</span>,
    }),
  ];
}

interface DocumentsTableProps {
  tenantId: string;
  // The scope (a folder, or the whole space) plus filters; never `cursor`, the table pages itself.
  query: Omit<ListDocumentsQuery, "cursor">;
  hiddenColumns?: DocumentColumn[];
  // Set filters turn "no documents" into "nothing matches", with a button to reset them.
  isFiltered?: boolean;
  onResetFilters?: () => void;
}

// The documents of one folder or space, by title (API order), 50 per page with "Mehr laden". No column sorting:
// sorting only the loaded rows would contradict the API's order once more pages are loaded.
export function DocumentsTable({
  tenantId,
  query,
  hiddenColumns = [],
  isFiltered,
  onResetFilters,
}: DocumentsTableProps) {
  const { t } = useTranslation();
  const documents = useDocuments(tenantId, query);
  const columns = useMemo(() => createColumns(t), [t]);
  const rows = useMemo(() => documents.data?.pages.flatMap((page) => page.items) ?? [], [documents.data]);
  const columnVisibility = useMemo(() => Object.fromEntries(hiddenColumns.map((id) => [id, false])), [hiddenColumns]);

  const table = useReactTable({
    data: rows,
    columns,
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
    state: { columnVisibility },
  });

  if (documents.isPending) {
    return <Spinner />;
  }
  if (documents.isError) {
    return <LoadFailed title={t("documents.table.loadFailed")} onRetry={() => void documents.refetch()} />;
  }
  if (rows.length === 0 && isFiltered) {
    return (
      <EmptyState
        icon={SearchX}
        title={t("documents.table.noMatchesTitle")}
        description={t("documents.table.noMatchesDescription")}
        action={
          onResetFilters && (
            <Button variant="outline" onClick={onResetFilters}>
              {t("documents.filters.reset")}
            </Button>
          )
        }
      />
    );
  }
  if (rows.length === 0) {
    return (
      <EmptyState
        icon={FileText}
        title={t("documents.table.emptyTitle")}
        description={t("documents.table.emptyDescription")}
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <TableHead key={header.id}>
                    {flexRender(header.column.columnDef.header, header.getContext())}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.map((row) => (
              <TableRow key={row.id}>
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {documents.hasNextPage && (
        <div className="flex justify-center">
          <Button
            variant="outline"
            disabled={documents.isFetchingNextPage}
            onClick={() => void documents.fetchNextPage()}
          >
            {t("documents.table.loadMore")}
          </Button>
        </div>
      )}
    </div>
  );
}
