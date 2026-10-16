// TanStack Query hooks for the document library: spaces and folders (API.md §3.2), documents (§3.3).
// Names from the "Frontend fn / hook" column. Every hook takes the tenant id from `useCurrentTenant()`.
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createFolder,
  createSpace,
  deleteFolder,
  listDocuments,
  listFolders,
  listSpaces,
  restoreDocument,
  trashDocument,
  updateFolder,
  updateSpace,
} from "../endpoints";
import { queryKeys } from "../queryKeys";
import type { FolderCreate, FolderUpdate, ListDocumentsQuery, SpaceCreate, SpaceUpdate } from "../types";

// The whole list in one page (`next_cursor` is always null for spaces and folders).
export function useSpaces(tenantId: string) {
  return useQuery({
    queryKey: queryKeys.tenants.spaces(tenantId),
    queryFn: () => listSpaces(tenantId),
    select: (page) => page.items,
    // DocumentsPage shows a load error with a retry button.
    meta: { errorToast: false },
  });
}

// Flat list sorted by `path`; FolderTree builds the tree from `parent_id`. Waits until a space is chosen.
export function useFolders(tenantId: string, spaceId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.tenants.folders(tenantId, spaceId ?? ""),
    queryFn: () => listFolders(tenantId, spaceId ?? ""),
    enabled: spaceId !== undefined,
    select: (page) => page.items,
    meta: { errorToast: false },
  });
}

// The space and folder mutations below turn the global error toast off: their dialogs show a taken name under the
// field and other errors inside the dialog (M1-B1 push 2).

export function useCreateSpace(tenantId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: SpaceCreate) => createSpace(tenantId, body),
    meta: { errorToast: false },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.tenants.spaces(tenantId) }),
  });
}

export function useUpdateSpace(tenantId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ spaceId, body }: { spaceId: string; body: SpaceUpdate }) => updateSpace(tenantId, spaceId, body),
    meta: { errorToast: false },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.tenants.spaces(tenantId) }),
  });
}

// Folder changes reload the folder list instead of patching the cache: a rename changes the `path` of every
// subfolder, and the list must stay sorted by it.
function useInvalidateFolders(tenantId: string) {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: queryKeys.tenants.allFolders(tenantId) });
}

export function useCreateFolder(tenantId: string) {
  const invalidateFolders = useInvalidateFolders(tenantId);
  return useMutation({
    mutationFn: (body: FolderCreate) => createFolder(tenantId, body),
    meta: { errorToast: false },
    onSuccess: invalidateFolders,
  });
}

export function useUpdateFolder(tenantId: string) {
  const invalidateFolders = useInvalidateFolders(tenantId);
  return useMutation({
    mutationFn: ({ folderId, body }: { folderId: string; body: FolderUpdate }) =>
      updateFolder(tenantId, folderId, body),
    meta: { errorToast: false },
    onSuccess: invalidateFolders,
  });
}

export function useDeleteFolder(tenantId: string) {
  const invalidateFolders = useInvalidateFolders(tenantId);
  return useMutation({
    mutationFn: (folderId: string) => deleteFolder(tenantId, folderId),
    meta: { errorToast: false },
    onSuccess: invalidateFolders,
  });
}

// Documents (API.md §3.3). The list is paged by `next_cursor`; `fetchNextPage()` loads more ("Mehr laden"). `query`
// holds the filters without `cursor`; every filter combination is its own cache entry.
export function useDocuments(tenantId: string, query: Omit<ListDocumentsQuery, "cursor">) {
  return useInfiniteQuery({
    queryKey: queryKeys.tenants.documents(tenantId, query),
    queryFn: ({ pageParam }) => listDocuments(tenantId, { ...query, cursor: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    // DocumentsTable shows load errors with a retry button.
    meta: { errorToast: false },
  });
}

// What a trash or restore of several documents did. Both actions are safe to repeat (API: trashing a trashed
// document changes nothing), so a partly failed batch can simply be run again for `failed`.
export interface BulkResult {
  succeeded: string[];
  failed: string[];
}

// One request per document (the API has no bulk endpoint), all at once; never throws, the caller reports the result.
async function runForEach(
  documentIds: string[],
  action: (documentId: string) => Promise<unknown>,
): Promise<BulkResult> {
  const results = await Promise.allSettled(documentIds.map(action));
  return {
    succeeded: documentIds.filter((_, index) => results[index]?.status === "fulfilled"),
    failed: documentIds.filter((_, index) => results[index]?.status === "rejected"),
  };
}

// Trash and restore change which list a document belongs to: every document list is reloaded once the whole batch
// is done (not once per document). One document is a list of one.
function useInvalidateDocuments(tenantId: string) {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: queryKeys.tenants.allDocuments(tenantId) });
}

export function useTrashDocument(tenantId: string) {
  const invalidateDocuments = useInvalidateDocuments(tenantId);
  return useMutation({
    mutationFn: (documentIds: string[]) => runForEach(documentIds, (id) => trashDocument(tenantId, id)),
    onSettled: invalidateDocuments,
  });
}

export function useRestoreDocument(tenantId: string) {
  const invalidateDocuments = useInvalidateDocuments(tenantId);
  return useMutation({
    mutationFn: (documentIds: string[]) => runForEach(documentIds, (id) => restoreDocument(tenantId, id)),
    onSettled: invalidateDocuments,
  });
}
