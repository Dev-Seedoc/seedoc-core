import type { ListDocumentsQuery } from "./types";

// Query key factory (NAMING §6): queryKeys.<area>.<name>(...). Tenant-scoped areas start with
// ["tenants", tenantId, ...] so invalidating ["tenants", tenantId] refreshes everything of one tenant.
export const queryKeys = {
  auth: {
    all: () => ["auth"] as const,
    me: () => ["auth", "me"] as const,
    invitation: (token: string) => ["auth", "invitations", token] as const,
  },
  tenants: {
    all: (tenantId: string) => ["tenants", tenantId] as const,
    spaces: (tenantId: string) => ["tenants", tenantId, "spaces"] as const,
    // Every space's folder list; a folder change invalidates this prefix.
    allFolders: (tenantId: string) => ["tenants", tenantId, "folders"] as const,
    folders: (tenantId: string, spaceId: string) => ["tenants", tenantId, "folders", spaceId] as const,
    // Every document list; trash/restore (and later uploads) invalidate this prefix.
    allDocuments: (tenantId: string) => ["tenants", tenantId, "documents"] as const,
    documents: (tenantId: string, query: ListDocumentsQuery) => ["tenants", tenantId, "documents", query] as const,
    // One document and its versions, under the same prefix: trash, upload or a variant link refreshes them too.
    document: (tenantId: string, documentId: string) =>
      ["tenants", tenantId, "documents", "detail", documentId] as const,
    documentVersions: (tenantId: string, documentId: string) =>
      ["tenants", tenantId, "documents", "detail", documentId, "versions"] as const,
  },
  // Staff data is not tenant-scoped (admin DB engine); logout drops it like every non-auth query.
  staff: {
    all: () => ["staff"] as const,
    tenantList: () => ["staff", "tenants", "list"] as const,
    tenant: (tenantId: string) => ["staff", "tenants", tenantId] as const,
  },
} as const;
