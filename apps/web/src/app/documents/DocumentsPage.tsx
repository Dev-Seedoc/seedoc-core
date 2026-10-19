import { FolderTree as FolderTreeIcon, Library, Pencil, Plus, Upload } from "lucide-react";
import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";

import { EmptyState } from "@/components/common/EmptyState";
import { LoadFailed } from "@/components/common/LoadFailed";
import { NativeSelect } from "@/components/common/NativeSelect";
import { Spinner } from "@/components/common/Spinner";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { useCurrentTenant } from "@/hooks/useCurrentTenant";
import { useFolders, useSpaces } from "@/lib/api/hooks/documents";
import type { DocumentListItem, FolderRead, SpaceRead } from "@/lib/api/types";

import { FolderActions } from "./FolderActions";
import { FolderDialog, type FolderDialogTarget } from "./FolderDialog";
import { ColumnsMenu } from "./ColumnsMenu";
import type { DocumentColumn } from "./documentColumns";
import { type DocumentFilters, documentFilterParams, hasDocumentFilters, readDocumentFilters } from "./documentFilters";
import { DocumentFiltersBar } from "./DocumentFiltersBar";
import { DocumentsTable, type DocumentsView } from "./DocumentsTable";
import { FolderTree } from "./FolderTree";
import { MoveToTrashButton } from "./MoveToTrashButton";
import { RestoreDocumentsButton } from "./RestoreDocumentsButton";
import { SpaceDialog, type SpaceDialogTarget } from "./SpaceDialog";
import { UploadDialog } from "./UploadDialog";
import { useHiddenDocumentColumns } from "./useHiddenDocumentColumns";

// The selection lives in the URL (`?space_id=…&folder_id=…`, the API's query names), so reload, back and links keep it.
const SPACE_PARAM = "space_id";
const FOLDER_PARAM = "folder_id";
// The trash is a tab of the page (NAMING §7: `?tab=<id>`); without it, the library is shown.
const TAB_PARAM = "tab";
const TRASH_TAB = "trash";

// Columns that make no sense in a view or scope: neither shown nor offered in the "Spalten" menu.
const VIEW_UNAVAILABLE_COLUMNS: Record<DocumentsView, DocumentColumn[]> = {
  library: ["trashedAt"],
  trash: ["status", "updatedAt"],
};
// Inside one folder every row has the same folder; that column only helps across the whole space.
const FOLDER_SCOPE_UNAVAILABLE_COLUMNS: DocumentColumn[] = ["folder"];

// `/documents` (NAMING §7). Left: space + folder tree (M1-B1); right: the documents of the folder (M1-B2).
export function DocumentsPage() {
  const { currentTenant } = useCurrentTenant();
  // AppLayout renders pages only for users with a tenant.
  return currentTenant ? (
    <DocumentsWorkspace
      tenantId={currentTenant.tenant_id}
      // BUSINESS_RULES §1: spaces are created and renamed by admins and owners; the API answers 403 to editors.
      canManageSpaces={currentTenant.role !== "editor"}
    />
  ) : null;
}

// Space actions for admins/owners; `undefined` hides them (editors).
interface SpaceActions {
  onCreate: () => void;
  onRename: (space: SpaceRead) => void;
}

function DocumentsWorkspace({ tenantId, canManageSpaces }: { tenantId: string; canManageSpaces: boolean }) {
  const { t } = useTranslation();
  const spaces = useSpaces(tenantId);
  const [, setSearchParams] = useSearchParams();
  const [spaceDialogTarget, setSpaceDialogTarget] = useState<SpaceDialogTarget | null>(null);
  const spaceActions: SpaceActions | undefined = canManageSpaces
    ? {
        onCreate: () => {
          setSpaceDialogTarget({ kind: "create" });
        },
        onRename: (space) => {
          setSpaceDialogTarget({ kind: "rename", space });
        },
      }
    : undefined;

  let content: ReactNode;
  if (spaces.isPending) {
    content = <Spinner />;
  } else if (spaces.isError) {
    content = <LoadFailed title={t("documents.spaces.loadFailed")} onRetry={() => void spaces.refetch()} />;
  } else if (spaces.data.length === 0) {
    content = (
      <EmptyState
        icon={Library}
        title={t("documents.spaces.emptyTitle")}
        description={
          spaceActions ? t("documents.spaces.emptyDescriptionAdmin") : t("documents.spaces.emptyDescription")
        }
        action={
          spaceActions && (
            <Button onClick={spaceActions.onCreate}>
              <Plus aria-hidden="true" />
              {t("documents.spaces.create")}
            </Button>
          )
        }
      />
    );
  } else {
    content = <SpaceBrowser tenantId={tenantId} spaces={spaces.data} spaceActions={spaceActions} />;
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold tracking-tight">{t("documents.page.title")}</h1>
      {content}
      <SpaceDialog
        tenantId={tenantId}
        target={spaceDialogTarget}
        onClose={() => {
          setSpaceDialogTarget(null);
        }}
        onSaved={(space) => {
          // A new space opens right away; a renamed one stays selected.
          setSearchParams({ [SPACE_PARAM]: space.id });
        }}
      />
    </div>
  );
}

interface SpaceBrowserProps {
  tenantId: string;
  spaces: SpaceRead[];
  spaceActions: SpaceActions | undefined;
}

function SpaceBrowser({ tenantId, spaces, spaceActions }: SpaceBrowserProps) {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  // An unknown or missing space in the URL falls back to the first space (sorted by name by the API).
  const space = spaces.find((candidate) => candidate.id === searchParams.get(SPACE_PARAM)) ?? spaces[0];
  const folders = useFolders(tenantId, space?.id);
  const folderId = searchParams.get(FOLDER_PARAM) ?? undefined;
  const selectedFolder = folders.data?.find((folder) => folder.id === folderId);
  // Rebuilt only when the URL changes, so the search delay in DocumentFiltersBar is not restarted by other renders.
  const filters = useMemo(() => readDocumentFilters(searchParams), [searchParams]);
  const view: DocumentsView = searchParams.get(TAB_PARAM) === TRASH_TAB ? "trash" : "library";
  const { hiddenColumns, setColumnVisible } = useHiddenDocumentColumns();
  const unavailableColumns = useMemo(
    () => [...VIEW_UNAVAILABLE_COLUMNS[view], ...(selectedFolder ? FOLDER_SCOPE_UNAVAILABLE_COLUMNS : [])],
    [view, selectedFolder],
  );
  const renderRestoreRow = useCallback(
    (document: DocumentListItem) => <RestoreDocumentsButton tenantId={tenantId} documents={[document]} inRow />,
    [tenantId],
  );
  const tableHiddenColumns = useMemo(
    () => [...hiddenColumns, ...unavailableColumns],
    [hiddenColumns, unavailableColumns],
  );

  // Merges `change` into the filters; `null` clears them all. React Router's setSearchParams does not queue updates
  // (its callback gets the URL of the last render), so changes made before the next render build on
  // `pendingParams` and never overwrite each other. Filter changes replace the history entry: Back goes to the
  // previous folder, not to every typed letter.
  const pendingParams = useRef<URLSearchParams | null>(null);
  useEffect(() => {
    pendingParams.current = null;
  }, [searchParams]);
  const spaceId = space?.id;
  const changeFilters = useCallback(
    (change: Partial<DocumentFilters> | null) => {
      const current = pendingParams.current ?? searchParams;
      const next = change === null ? {} : { ...readDocumentFilters(current), ...change };
      const params = new URLSearchParams(documentFilterParams(next));
      for (const key of [SPACE_PARAM, FOLDER_PARAM, TAB_PARAM]) {
        const value = current.get(key);
        if (value) {
          params.set(key, value);
        }
      }
      if (spaceId && !params.has(SPACE_PARAM)) {
        params.set(SPACE_PARAM, spaceId);
      }
      pendingParams.current = params;
      setSearchParams(params, { replace: true });
    },
    [searchParams, setSearchParams, spaceId],
  );
  const [dialogTarget, setDialogTarget] = useState<FolderDialogTarget | null>(null);
  const [isUploadOpen, setIsUploadOpen] = useState(false);

  if (!space) {
    return null;
  }

  function selectSpace(spaceId: string) {
    setSearchParams({ [SPACE_PARAM]: spaceId });
  }

  // Library or trash, for the same space, folder and filters.
  function changeView(next: DocumentsView) {
    const params = new URLSearchParams(searchParams);
    if (space) {
      // Like every other change: the shown space is written out, also when it was only the default.
      params.set(SPACE_PARAM, space.id);
    }
    if (next === "trash") {
      params.set(TAB_PARAM, TRASH_TAB);
    } else {
      params.delete(TAB_PARAM);
    }
    setSearchParams(params);
  }

  // `undefined` = no folder selected (e.g. after deleting a top-level folder). The filters stay: "only data sheets"
  // while browsing folders. A new space starts without them (selectSpace).
  function selectFolder(id: string | undefined) {
    if (space) {
      setSearchParams({
        [SPACE_PARAM]: space.id,
        ...(id ? { [FOLDER_PARAM]: id } : {}),
        ...documentFilterParams(filters),
        ...(view === "trash" ? { [TAB_PARAM]: TRASH_TAB } : {}),
      });
    }
  }

  const createFolderButton = (
    <Button
      variant="outline"
      size="sm"
      onClick={() => {
        setDialogTarget({ kind: "create", parent: null });
      }}
    >
      <Plus aria-hidden="true" />
      {t("documents.folders.create")}
    </Button>
  );

  let tree: ReactNode;
  if (folders.isPending) {
    tree = <Spinner />;
  } else if (folders.isError) {
    tree = <LoadFailed title={t("documents.folders.loadFailed")} onRetry={() => void folders.refetch()} />;
  } else if (folders.data.length === 0) {
    tree = (
      <EmptyState
        icon={FolderTreeIcon}
        title={t("documents.folders.emptyTitle")}
        description={t("documents.folders.emptyDescription")}
        action={createFolderButton}
        className="py-8"
      />
    );
  } else {
    tree = (
      <FolderTree
        // A new space gets a fresh tree (expanded folders belong to one space).
        key={space.id}
        folders={folders.data}
        selectedFolderId={selectedFolder?.id}
        onSelect={selectFolder}
        label={t("documents.folders.treeLabel", { space: space.name })}
      />
    );
  }

  return (
    <div className="flex flex-col gap-6 lg:flex-row">
      <aside className="flex w-full shrink-0 flex-col gap-4 lg:w-72">
        {spaces.length > 1 ? (
          <div className="flex flex-col gap-2">
            <Label htmlFor="documents-space">{t("documents.spaces.label")}</Label>
            <NativeSelect
              id="documents-space"
              value={space.id}
              onChange={(event) => {
                selectSpace(event.target.value);
              }}
            >
              {spaces.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.name}
                </option>
              ))}
            </NativeSelect>
          </div>
        ) : (
          <p className="text-sm">
            <span className="text-muted-foreground">{t("documents.spaces.label")}: </span>
            <span className="font-medium">{space.name}</span>
          </p>
        )}
        {spaceActions && (
          <div className="flex gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                spaceActions.onRename(space);
              }}
            >
              <Pencil aria-hidden="true" />
              {t("documents.spaces.rename")}
            </Button>
            <Button variant="ghost" size="sm" onClick={spaceActions.onCreate}>
              <Plus aria-hidden="true" />
              {t("documents.spaces.create")}
            </Button>
          </div>
        )}
        {folders.data && folders.data.length > 0 && <div>{createFolderButton}</div>}
        {tree}
      </aside>

      <section className="flex min-w-0 flex-1 flex-col gap-4">
        <div className="flex items-center justify-between gap-4">
          <h2 className="min-w-0 truncate text-lg font-semibold">
            {selectedFolder ? selectedFolder.path : t("documents.folders.allInSpace", { space: space.name })}
          </h2>
          {selectedFolder && view === "library" && (
            <Button
              size="sm"
              onClick={() => {
                setIsUploadOpen(true);
              }}
            >
              <Upload aria-hidden="true" />
              {t("documents.upload.open")}
            </Button>
          )}
          {selectedFolder && (
            <FolderActions
              tenantId={tenantId}
              folder={selectedFolder}
              onCreateSubfolder={() => {
                setDialogTarget({ kind: "create", parent: selectedFolder });
              }}
              onEdit={() => {
                setDialogTarget({ kind: "edit", folder: selectedFolder });
              }}
              onDeleted={(folder) => {
                selectFolder(folder.parent_id ?? undefined);
              }}
            />
          )}
        </div>
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div className="flex flex-wrap items-end gap-2">
            <div className="flex rounded-md border p-0.5" role="group" aria-label={t("documents.views.label")}>
              {(["library", "trash"] as const).map((option) => (
                <Button
                  key={option}
                  variant={view === option ? "secondary" : "ghost"}
                  size="sm"
                  aria-pressed={view === option}
                  onClick={() => {
                    changeView(option);
                  }}
                >
                  {t(`documents.views.${option}`)}
                </Button>
              ))}
            </div>
            <DocumentFiltersBar filters={filters} onChange={changeFilters} />
          </div>
          <ColumnsMenu
            hiddenColumns={hiddenColumns}
            unavailableColumns={unavailableColumns}
            onChange={setColumnVisible}
          />
        </div>
        {view === "trash" && <p className="text-muted-foreground text-sm">{t("documents.trash.hint")}</p>}
        {/* A folder in the URL is only known once the folder list is there: wait for it rather than load the whole
            space first and the folder right after. */}
        {folderId && folders.isPending ? (
          <Spinner />
        ) : (
          <DocumentsTable
            // A new table (rows, paging) per folder / space; filter changes reload it in place.
            key={selectedFolder?.id ?? space.id}
            tenantId={tenantId}
            query={{ ...(selectedFolder ? { folder_id: selectedFolder.id } : { space_id: space.id }), ...filters }}
            isFiltered={hasDocumentFilters(filters)}
            onResetFilters={() => {
              changeFilters(null);
            }}
            hiddenColumns={tableHiddenColumns}
            view={view}
            renderRowAction={view === "trash" ? renderRestoreRow : undefined}
            renderSelectionActions={(selected, selectOnly) =>
              view === "trash" ? (
                <RestoreDocumentsButton tenantId={tenantId} documents={selected} onDone={selectOnly} />
              ) : (
                <MoveToTrashButton tenantId={tenantId} documents={selected} onDone={selectOnly} />
              )
            }
          />
        )}
      </section>

      {selectedFolder && (
        <UploadDialog
          tenantId={tenantId}
          folder={selectedFolder}
          open={isUploadOpen}
          onClose={() => {
            setIsUploadOpen(false);
          }}
        />
      )}
      <FolderDialog
        tenantId={tenantId}
        spaceId={space.id}
        target={dialogTarget}
        onClose={() => {
          setDialogTarget(null);
        }}
        onSaved={(folder: FolderRead) => {
          selectFolder(folder.id);
        }}
      />
    </div>
  );
}
