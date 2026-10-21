import type { ListDeliveriesQuery, ListDocumentsQuery } from "./types";

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
    // Every product query (list, details, set, matrix, releases): saving a product or its set invalidates this prefix.
    allProducts: (tenantId: string) => ["tenants", tenantId, "products"] as const,
    products: (tenantId: string) => ["tenants", tenantId, "products", "list"] as const,
    product: (tenantId: string, productId: string) => ["tenants", tenantId, "products", "detail", productId] as const,
    productDocuments: (tenantId: string, productId: string) =>
      ["tenants", tenantId, "products", "detail", productId, "documents"] as const,
    productLanguageMatrix: (tenantId: string, productId: string) =>
      ["tenants", tenantId, "products", "detail", productId, "languages"] as const,
    productReleases: (tenantId: string, productId: string) =>
      ["tenants", tenantId, "products", "detail", productId, "releases"] as const,
    productRelease: (tenantId: string, productId: string, releaseNo: number) =>
      ["tenants", tenantId, "products", "detail", productId, "releases", releaseNo] as const,
    // Customers and deliveries: creating a delivery changes a customer's `delivery_count`, so delivery mutations
    // invalidate both prefixes.
    allCustomers: (tenantId: string) => ["tenants", tenantId, "customers"] as const,
    customers: (tenantId: string) => ["tenants", tenantId, "customers", "list"] as const,
    customer: (tenantId: string, customerId: string) =>
      ["tenants", tenantId, "customers", "detail", customerId] as const,
    allDeliveries: (tenantId: string) => ["tenants", tenantId, "deliveries"] as const,
    deliveries: (tenantId: string, query: ListDeliveriesQuery) =>
      ["tenants", tenantId, "deliveries", "list", query] as const,
    delivery: (tenantId: string, deliveryId: string) =>
      ["tenants", tenantId, "deliveries", "detail", deliveryId] as const,
  },
  // Staff data is not tenant-scoped (admin DB engine); logout drops it like every non-auth query.
  staff: {
    all: () => ["staff"] as const,
    tenantList: () => ["staff", "tenants", "list"] as const,
    tenant: (tenantId: string) => ["staff", "tenants", tenantId] as const,
  },
} as const;
