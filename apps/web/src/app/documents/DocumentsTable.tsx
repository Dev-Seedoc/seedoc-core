import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  type RowSelectionState,
  useReactTable,
} from "@tanstack/react-table";
import type { TFunction } from "i18next";
import { FileText, SearchX, Trash2 } from "lucide-react";
import { type ReactNode, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { EmptyState } from "@/components/common/EmptyState";
import { LoadFailed } from "@/components/common/LoadFailed";
import { NativeCheckbox } from "@/components/common/NativeCheckbox";
import { Spinner } from "@/components/common/Spinner";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useDocuments } from "@/lib/api/hooks/documents";
import type { DocumentListItem, ListDocumentsQuery } from "@/lib/api/types";
import { formatDateTime } from "@/lib/formatDate";
import { getLanguageLabel } from "@/lib/languages";

import type { DocumentColumn } from "./documentColumns";

const column = createColumnHelper<DocumentListItem>();
const EMPTY_CELL = <span className="text-muted-foreground">—</span>;

// The trash view asks for trashed documents too and keeps only those. A page of 200 (the API's maximum) makes
// "Mehr laden" rarely needed. Until list_documents can filter for trashed documents itself, a page can come back
// with fewer rows than it holds.
const TRASH_PAGE_LIMIT = 200;

export type DocumentsView = "library" | "trash";

function createColumns(t: TFunction, renderRowAction?: (document: DocumentListItem) => ReactNode) {
  const columns = [
    // Selection for bulk actions; not one of DOCUMENT_COLUMNS, so it is never offered in the "Spalten" menu.
    column.display({
      id: "select",
      header: ({ table }) => (
        <NativeCheckbox
          aria-label={t("documents.selection.selectAll")}
          checked={table.getIsAllRowsSelected()}
          indeterminate={table.getIsSomeRowsSelected()}
          onChange={table.getToggleAllRowsSelectedHandler()}
        />
      ),
      cell: ({ row }) => (
        <NativeCheckbox
          aria-label={t("documents.selection.selectRow", { title: row.original.title })}
          checked={row.getIsSelected()}
          onChange={row.getToggleSelectedHandler()}
        />
      ),
    }),
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
      cell: ({ getValue }) => getLanguageLabel(getValue(), t),
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
    column.accessor("trashed_at", {
      id: "trashedAt",
      header: t("documents.table.trashedAt"),
      cell: ({ getValue }) => {
        const trashedAt = getValue();
        return trashedAt ? (
          <span className="whitespace-nowrap tabular-nums">{formatDateTime(trashedAt)}</span>
        ) : (
          EMPTY_CELL
        );
      },
    }),
  ];
  if (!renderRowAction) {
    return columns;
  }
  // One action per row (e.g. "Wiederherstellen"); like the selection column, never in the "Spalten" menu.
  return [
    ...columns,
    column.display({
      id: "actions",
      header: () => <span className="sr-only">{t("documents.table.actions")}</span>,
      cell: ({ row }) => <div className="flex justify-end">{renderRowAction(row.original)}</div>,
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
  // Buttons for the selected documents (e.g. "In den Papierkorb"). After the action, `selectOnly` keeps just the
  // given rows selected — the failed ones — or none.
  renderSelectionActions?: (selected: DocumentListItem[], selectOnly: (documentIds: string[]) => void) => ReactNode;
  // The library (default) or the trash: only trashed documents, plus `renderRowAction` per row.
  view?: DocumentsView;
  renderRowAction?: (document: DocumentListItem) => ReactNode;
}

// The documents of one folder or space, by title (API order), 50 per page with "Mehr laden". No column sorting:
// sorting only the loaded rows would contradict the API's order once more pages are loaded.
export function DocumentsTable({
  tenantId,
  query,
  hiddenColumns = [],
  isFiltered,
  onResetFilters,
  renderSelectionActions,
  view = "library",
  renderRowAction,
}: DocumentsTableProps) {
  const { t } = useTranslation();
  const isTrash = view === "trash";
  const listQuery = isTrash ? { ...query, include_trashed: true, limit: TRASH_PAGE_LIMIT } : query;
  const documents = useDocuments(tenantId, listQuery);
  const columns = useMemo(() => createColumns(t, renderRowAction), [t, renderRowAction]);
  const rows = useMemo(() => {
    const items = documents.data?.pages.flatMap((page) => page.items) ?? [];
    return isTrash ? items.filter((item) => item.trashed_at !== null) : items;
  }, [documents.data, isTrash]);
  const columnVisibility = useMemo(() => Object.fromEntries(hiddenColumns.map((id) => [id, false])), [hiddenColumns]);

  // Never act on rows the user cannot see: other filters or another view start without a selection.
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const queryKey = JSON.stringify(listQuery);
  const [selectionQueryKey, setSelectionQueryKey] = useState(queryKey);
  if (selectionQueryKey !== queryKey) {
    setSelectionQueryKey(queryKey);
    setRowSelection({});
  }
  // Only rows that are still listed count (a trashed document drops out after the list reloads).
  const selected = rows.filter((row) => rowSelection[row.id]);
  function selectOnly(documentIds: string[]) {
    setRowSelection(Object.fromEntries(documentIds.map((id) => [id, true])));
  }
  function clearSelection() {
    selectOnly([]);
  }

  const table = useReactTable({
    data: rows,
    columns,
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
    enableRowSelection: true,
    onRowSelectionChange: setRowSelection,
    state: { columnVisibility, rowSelection },
  });

  if (documents.isPending) {
    return <Spinner />;
  }
  if (documents.isError) {
    return <LoadFailed title={t("documents.table.loadFailed")} onRetry={() => void documents.refetch()} />;
  }
  // In the trash, an empty first page can still be followed by pages with trashed documents ("Mehr laden").
  const mayHaveMore = isTrash && documents.hasNextPage;
  if (rows.length === 0 && isFiltered && !mayHaveMore) {
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
  if (rows.length === 0 && isTrash && !mayHaveMore) {
    return (
      <EmptyState
        icon={Trash2}
        title={t("documents.trash.emptyTitle")}
        description={t("documents.trash.emptyDescription")}
      />
    );
  }
  if (rows.length === 0 && !isTrash) {
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
      {selected.length > 0 && (
        <div className="bg-muted/50 flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2">
          <span className="mr-auto text-sm font-medium" aria-live="polite">
            {t("documents.selection.count", { count: selected.length })}
          </span>
          {renderSelectionActions?.(selected, selectOnly)}
          <Button variant="ghost" size="sm" onClick={clearSelection}>
            {t("documents.selection.clear")}
          </Button>
        </div>
      )}
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <TableHead key={header.id} className={header.id === "select" ? "w-10" : undefined}>
                    {flexRender(header.column.columnDef.header, header.getContext())}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.map((row) => (
              <TableRow key={row.id} data-state={row.getIsSelected() ? "selected" : undefined}>
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
