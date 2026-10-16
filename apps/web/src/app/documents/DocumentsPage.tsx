import { FileText, FolderTree as FolderTreeIcon, Library, Loader2, Plus, TriangleAlert } from "lucide-react";
import { type ReactNode, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";

import { EmptyState } from "@/components/common/EmptyState";
import { NativeSelect } from "@/components/common/NativeSelect";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { useCurrentTenant } from "@/hooks/useCurrentTenant";
import { useFolders, useSpaces } from "@/lib/api/hooks/documents";
import type { FolderRead, SpaceRead } from "@/lib/api/types";

import { FolderActions } from "./FolderActions";
import { FolderDialog, type FolderDialogTarget } from "./FolderDialog";
import { FolderTree } from "./FolderTree";

// The selection lives in the URL (`?space_id=…&folder_id=…`, the API's query names), so reload, back and links keep it.
const SPACE_PARAM = "space_id";
const FOLDER_PARAM = "folder_id";

function Spinner() {
  return (
    <div className="flex justify-center py-8">
      <Loader2 className="text-muted-foreground size-5 animate-spin" aria-hidden="true" />
    </div>
  );
}

function LoadFailed({ title, onRetry }: { title: string; onRetry: () => void }) {
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

// `/documents` (NAMING §7). Left: space + folder tree (M1-B1); right: the documents of the folder (M1-B2).
export function DocumentsPage() {
  const { currentTenant } = useCurrentTenant();
  // AppLayout renders pages only for users with a tenant.
  return currentTenant ? <DocumentsWorkspace tenantId={currentTenant.tenant_id} /> : null;
}

function DocumentsWorkspace({ tenantId }: { tenantId: string }) {
  const { t } = useTranslation();
  const spaces = useSpaces(tenantId);

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
        description={t("documents.spaces.emptyDescription")}
      />
    );
  } else {
    content = <SpaceBrowser tenantId={tenantId} spaces={spaces.data} />;
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold tracking-tight">{t("documents.page.title")}</h1>
      {content}
    </div>
  );
}

function SpaceBrowser({ tenantId, spaces }: { tenantId: string; spaces: SpaceRead[] }) {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  // An unknown or missing space in the URL falls back to the first space (sorted by name by the API).
  const space = spaces.find((candidate) => candidate.id === searchParams.get(SPACE_PARAM)) ?? spaces[0];
  const folders = useFolders(tenantId, space?.id);
  const folderId = searchParams.get(FOLDER_PARAM) ?? undefined;
  const selectedFolder = folders.data?.find((folder) => folder.id === folderId);
  const [dialogTarget, setDialogTarget] = useState<FolderDialogTarget | null>(null);

  if (!space) {
    return null;
  }

  function selectSpace(spaceId: string) {
    setSearchParams({ [SPACE_PARAM]: spaceId });
  }

  // `undefined` = no folder selected (e.g. after deleting a top-level folder).
  function selectFolder(id: string | undefined) {
    if (space) {
      setSearchParams(id ? { [SPACE_PARAM]: space.id, [FOLDER_PARAM]: id } : { [SPACE_PARAM]: space.id });
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
        {folders.data && folders.data.length > 0 && <div>{createFolderButton}</div>}
        {tree}
      </aside>

      <section className="flex min-w-0 flex-1 flex-col gap-4" aria-live="polite">
        <div className="flex items-center justify-between gap-4">
          <h2 className="min-w-0 truncate text-lg font-semibold">
            {selectedFolder ? selectedFolder.path : t("documents.folders.noSelection")}
          </h2>
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
        {/* M1-B2 replaces this with the documents table of the selected folder. Not the shared page placeholder:
            its "Dieser Bereich …" would read as "this space" here. */}
        <EmptyState
          icon={FileText}
          title={t("documents.list.comingSoonTitle")}
          description={t("documents.list.comingSoonDescription")}
        />
      </section>

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
