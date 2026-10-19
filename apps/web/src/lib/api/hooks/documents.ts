// TanStack Query hooks for the document library: spaces and folders (API.md §3.2), documents (§3.3).
// Names from the "Frontend fn / hook" column. Every hook takes the tenant id from `useCurrentTenant()`.
import { type InfiniteData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createDocument,
  createDocumentVersion,
  createFolder,
  createUpload,
  createSpace,
  deleteFolder,
  getDocument,
  linkLanguageVariant,
  listDocuments,
  listDocumentVersions,
  listFolders,
  listSpaces,
  restoreDocument,
  trashDocument,
  unlinkLanguageVariant,
  updateDocument,
  updateFolder,
  updateSpace,
} from "../endpoints";
import { queryKeys } from "../queryKeys";
import type {
  DocumentCreate,
  DocumentRead,
  DocumentUpdate,
  DocumentVersionCreate,
  DocumentVersionRead,
  LanguageVariantLink,
  FolderCreate,
  FolderUpdate,
  ListDocumentsQuery,
  Page_DocumentListItem_,
  SpaceCreate,
  SpaceUpdate,
  UploadCreate,
} from "../types";

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

// While a listed document is still being processed by the worker (pending / processing), the list is asked again
// this often, so "In Bearbeitung" turns into "Bereit" without a reload. It stops once every row is done, and
// TanStack Query does not poll while the browser tab is in the background.
export const PROCESSING_REFETCH_MS = 3000;

function isProcessing(status: DocumentRead["processing_status"]): boolean {
  return status === "pending" || status === "processing";
}

export function getProcessingRefetchInterval(data: InfiniteData<Page_DocumentListItem_> | undefined): number | false {
  const anyProcessing = data?.pages.some((page) => page.items.some((item) => isProcessing(item.processing_status)));
  return anyProcessing ? PROCESSING_REFETCH_MS : false;
}

// Documents (API.md §3.3). The list is paged by `next_cursor`; `fetchNextPage()` loads more ("Mehr laden"). `query`
// holds the filters without `cursor`; every filter combination is its own cache entry.
export function useDocuments(tenantId: string, query: Omit<ListDocumentsQuery, "cursor">) {
  return useInfiniteQuery({
    queryKey: queryKeys.tenants.documents(tenantId, query),
    queryFn: ({ pageParam }) => listDocuments(tenantId, { ...query, cursor: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    refetchInterval: (query) => getProcessingRefetchInterval(query.state.data),
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

// Reloads every document query of the tenant (lists and details: one prefix). Trash and restore call it once the
// whole batch is done, not once per document.
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

// Upload of new documents (API.md §3.3): create_upload → PUT to `upload_url` → create_document. The upload dialog
// runs many files and reports each one itself (no global toast); it reloads the document lists once at the end,
// so useCreateDocument does not reload after every single file.
export function useCreateUpload(tenantId: string) {
  return useMutation({
    mutationFn: (body: UploadCreate) => createUpload(tenantId, body),
    meta: { errorToast: false },
  });
}

export function useCreateDocument(tenantId: string) {
  return useMutation({
    mutationFn: (body: DocumentCreate) => createDocument(tenantId, body),
    meta: { errorToast: false },
  });
}

// One document (DocumentDetailPage). Polled like the list while its current version is processed.
export function useDocument(tenantId: string, documentId: string) {
  return useQuery({
    queryKey: queryKeys.tenants.document(tenantId, documentId),
    queryFn: () => getDocument(tenantId, documentId),
    refetchInterval: (query) =>
      isProcessing(query.state.data?.processing_status ?? null) ? PROCESSING_REFETCH_MS : false,
    // The page shows "not found" and load errors itself.
    meta: { errorToast: false },
  });
}

// Every version, newest first (never paged); polled while one is processed.
export function useDocumentVersions(tenantId: string, documentId: string) {
  return useQuery({
    queryKey: queryKeys.tenants.documentVersions(tenantId, documentId),
    queryFn: () => listDocumentVersions(tenantId, documentId),
    select: (page) => page.items,
    refetchInterval: (query) =>
      query.state.data?.items.some((version: DocumentVersionRead) => isProcessing(version.processing_status))
        ? PROCESSING_REFETCH_MS
        : false,
    meta: { errorToast: false },
  });
}

// Changes to one document also change lists (title, type …) and other documents (a language group), so the hooks
// below reload every document query of the tenant, the detail included (useInvalidateDocuments).
// The forms and dialogs of DocumentDetailPage show errors in place, so none of these use the global toast.

export function useUpdateDocument(tenantId: string, documentId: string) {
  const invalidate = useInvalidateDocuments(tenantId);
  return useMutation({
    mutationFn: (body: DocumentUpdate) => updateDocument(tenantId, documentId, body),
    meta: { errorToast: false },
    onSuccess: invalidate,
  });
}

export function useCreateDocumentVersion(tenantId: string, documentId: string) {
  const invalidate = useInvalidateDocuments(tenantId);
  return useMutation({
    mutationFn: (body: DocumentVersionCreate) => createDocumentVersion(tenantId, documentId, body),
    meta: { errorToast: false },
    onSuccess: invalidate,
  });
}

export function useLinkLanguageVariant(tenantId: string, documentId: string) {
  const invalidate = useInvalidateDocuments(tenantId);
  return useMutation({
    mutationFn: (body: LanguageVariantLink) => linkLanguageVariant(tenantId, documentId, body),
    meta: { errorToast: false },
    onSuccess: invalidate,
  });
}

export function useUnlinkLanguageVariant(tenantId: string, documentId: string) {
  const invalidate = useInvalidateDocuments(tenantId);
  return useMutation({
    mutationFn: (variantDocumentId: string) => unlinkLanguageVariant(tenantId, documentId, variantDocumentId),
    meta: { errorToast: false },
    onSuccess: invalidate,
  });
}
