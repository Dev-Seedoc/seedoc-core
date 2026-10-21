// One function per operation_id, named camelCase(operation_id) (docs/API.md). Each returns the response body or
// throws ApiError.
import { client } from "./client";
import { toApiError } from "./errors";
import type {
  AcceptInvitationRequest,
  CustomerCreate,
  CustomerRead,
  CustomerUpdate,
  DeliveryCreate,
  DeliveryRead,
  DocumentCreate,
  DocumentRead,
  DocumentUpdate,
  DocumentVersionCreate,
  DocumentVersionRead,
  FolderCreate,
  FolderRead,
  FolderUpdate,
  HealthRead,
  InvitationPreview,
  LanguageVariantLink,
  ListDeliveriesQuery,
  ListDocumentsQuery,
  LoginRequest,
  MeRead,
  Page_CustomerRead_,
  Page_DeliveryListItem_,
  Page_DocumentListItem_,
  LanguageMatrixRead,
  Page_DocumentVersionRead_,
  Page_FolderRead_,
  Page_ProductRead_,
  Page_ProductReleaseRead_,
  Page_SpaceRead_,
  Page_StaffTenantListItem_,
  PasswordResetConfirmRequest,
  PasswordResetRequest,
  ProductCreate,
  ProductDocumentsSet,
  ProductRead,
  ProductReleaseDetailRead,
  ProductUpdate,
  ReauthenticateRequest,
  SpaceCreate,
  SpaceRead,
  SpaceUpdate,
  StaffTenantCreate,
  StaffTenantRead,
  StaffTenantUpdate,
  TotpSetupRead,
  UploadCreate,
  UploadRead,
  VerifyTotpRequest,
  VersionFileUrlRead,
} from "./types";

interface ApiResult<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

async function unwrap<T>(request: Promise<ApiResult<T>>): Promise<T> {
  const { data, error, response } = await request;
  if (!response.ok || data === undefined) {
    throw toApiError(response.status, error);
  }
  return data;
}

// For 202/204 endpoints, which have no body.
async function unwrapEmpty(request: Promise<ApiResult<unknown>>): Promise<void> {
  const { error, response } = await request;
  if (!response.ok) {
    throw toApiError(response.status, error);
  }
}

// Health

export function getHealth(): Promise<HealthRead> {
  return unwrap(client.GET("/api/v1/health"));
}

// Auth

export function login(body: LoginRequest): Promise<MeRead> {
  return unwrap(client.POST("/api/v1/auth/login", { body }));
}

export function logout(): Promise<void> {
  return unwrapEmpty(client.POST("/api/v1/auth/logout"));
}

export function getMe(): Promise<MeRead> {
  return unwrap(client.GET("/api/v1/auth/me"));
}

export function reauthenticate(body: ReauthenticateRequest): Promise<void> {
  return unwrapEmpty(client.POST("/api/v1/auth/reauth", { body }));
}

export function requestPasswordReset(body: PasswordResetRequest): Promise<void> {
  return unwrapEmpty(client.POST("/api/v1/auth/password-reset", { body }));
}

export function confirmPasswordReset(body: PasswordResetConfirmRequest): Promise<void> {
  return unwrapEmpty(client.POST("/api/v1/auth/password-reset/confirm", { body }));
}

export function getInvitation(token: string): Promise<InvitationPreview> {
  return unwrap(client.GET("/api/v1/auth/invitations/{token}", { params: { path: { token } } }));
}

export function acceptInvitation(token: string, body: AcceptInvitationRequest): Promise<MeRead> {
  return unwrap(client.POST("/api/v1/auth/invitations/{token}/accept", { params: { path: { token } }, body }));
}

export function setupTotp(): Promise<TotpSetupRead> {
  return unwrap(client.POST("/api/v1/auth/totp/setup"));
}

export function verifyTotp(body: VerifyTotpRequest): Promise<void> {
  return unwrapEmpty(client.POST("/api/v1/auth/totp/verify", { body }));
}

// Staff

export function staffListTenants(cursor?: string): Promise<Page_StaffTenantListItem_> {
  return unwrap(client.GET("/api/v1/staff/tenants", { params: { query: { cursor } } }));
}

export function staffCreateTenant(body: StaffTenantCreate): Promise<StaffTenantRead> {
  return unwrap(client.POST("/api/v1/staff/tenants", { body }));
}

export function staffGetTenant(tenantId: string): Promise<StaffTenantRead> {
  return unwrap(client.GET("/api/v1/staff/tenants/{tenant_id}", { params: { path: { tenant_id: tenantId } } }));
}

export function staffUpdateTenant(tenantId: string, body: StaffTenantUpdate): Promise<StaffTenantRead> {
  return unwrap(client.PATCH("/api/v1/staff/tenants/{tenant_id}", { params: { path: { tenant_id: tenantId } }, body }));
}

// Manufacturer app: spaces and folders (API.md §3.2)

function tenantPath(tenantId: string) {
  return { tenant_id: tenantId };
}

export function listSpaces(tenantId: string): Promise<Page_SpaceRead_> {
  return unwrap(client.GET("/api/v1/app/tenants/{tenant_id}/spaces", { params: { path: tenantPath(tenantId) } }));
}

export function createSpace(tenantId: string, body: SpaceCreate): Promise<SpaceRead> {
  return unwrap(
    client.POST("/api/v1/app/tenants/{tenant_id}/spaces", { params: { path: tenantPath(tenantId) }, body }),
  );
}

export function updateSpace(tenantId: string, spaceId: string, body: SpaceUpdate): Promise<SpaceRead> {
  return unwrap(
    client.PATCH("/api/v1/app/tenants/{tenant_id}/spaces/{space_id}", {
      params: { path: { ...tenantPath(tenantId), space_id: spaceId } },
      body,
    }),
  );
}

export function listFolders(tenantId: string, spaceId: string): Promise<Page_FolderRead_> {
  return unwrap(
    client.GET("/api/v1/app/tenants/{tenant_id}/folders", {
      params: { path: tenantPath(tenantId), query: { space_id: spaceId } },
    }),
  );
}

export function createFolder(tenantId: string, body: FolderCreate): Promise<FolderRead> {
  return unwrap(
    client.POST("/api/v1/app/tenants/{tenant_id}/folders", { params: { path: tenantPath(tenantId) }, body }),
  );
}

export function updateFolder(tenantId: string, folderId: string, body: FolderUpdate): Promise<FolderRead> {
  return unwrap(
    client.PATCH("/api/v1/app/tenants/{tenant_id}/folders/{folder_id}", {
      params: { path: { ...tenantPath(tenantId), folder_id: folderId } },
      body,
    }),
  );
}

export function deleteFolder(tenantId: string, folderId: string): Promise<void> {
  return unwrapEmpty(
    client.DELETE("/api/v1/app/tenants/{tenant_id}/folders/{folder_id}", {
      params: { path: { ...tenantPath(tenantId), folder_id: folderId } },
    }),
  );
}

// Manufacturer app: documents (API.md §3.3)

export function listDocuments(tenantId: string, query: ListDocumentsQuery): Promise<Page_DocumentListItem_> {
  return unwrap(
    client.GET("/api/v1/app/tenants/{tenant_id}/documents", { params: { path: tenantPath(tenantId), query } }),
  );
}

export function trashDocument(tenantId: string, documentId: string): Promise<DocumentRead> {
  return unwrap(
    client.POST("/api/v1/app/tenants/{tenant_id}/documents/{document_id}/trash", {
      params: { path: { ...tenantPath(tenantId), document_id: documentId } },
    }),
  );
}

export function restoreDocument(tenantId: string, documentId: string): Promise<DocumentRead> {
  return unwrap(
    client.POST("/api/v1/app/tenants/{tenant_id}/documents/{document_id}/restore", {
      params: { path: { ...tenantPath(tenantId), document_id: documentId } },
    }),
  );
}

export function createUpload(tenantId: string, body: UploadCreate): Promise<UploadRead> {
  return unwrap(
    client.POST("/api/v1/app/tenants/{tenant_id}/uploads", { params: { path: tenantPath(tenantId) }, body }),
  );
}

export function createDocument(tenantId: string, body: DocumentCreate): Promise<DocumentRead> {
  return unwrap(
    client.POST("/api/v1/app/tenants/{tenant_id}/documents", { params: { path: tenantPath(tenantId) }, body }),
  );
}

function documentPath(tenantId: string, documentId: string) {
  return { ...tenantPath(tenantId), document_id: documentId };
}

export function getDocument(tenantId: string, documentId: string): Promise<DocumentRead> {
  return unwrap(
    client.GET("/api/v1/app/tenants/{tenant_id}/documents/{document_id}", {
      params: { path: documentPath(tenantId, documentId) },
    }),
  );
}

export function updateDocument(tenantId: string, documentId: string, body: DocumentUpdate): Promise<DocumentRead> {
  return unwrap(
    client.PATCH("/api/v1/app/tenants/{tenant_id}/documents/{document_id}", {
      params: { path: documentPath(tenantId, documentId) },
      body,
    }),
  );
}

export function listDocumentVersions(tenantId: string, documentId: string): Promise<Page_DocumentVersionRead_> {
  return unwrap(
    client.GET("/api/v1/app/tenants/{tenant_id}/documents/{document_id}/versions", {
      params: { path: documentPath(tenantId, documentId) },
    }),
  );
}

export function createDocumentVersion(
  tenantId: string,
  documentId: string,
  body: DocumentVersionCreate,
): Promise<DocumentVersionRead> {
  return unwrap(
    client.POST("/api/v1/app/tenants/{tenant_id}/documents/{document_id}/versions", {
      params: { path: documentPath(tenantId, documentId) },
      body,
    }),
  );
}

// A presigned download link, valid for 120 s (API.md §3.3): fetched right before use, so it has no hook (NAMING §6).
export function getVersionFileUrl(
  tenantId: string,
  documentId: string,
  versionId: string,
): Promise<VersionFileUrlRead> {
  return unwrap(
    client.GET("/api/v1/app/tenants/{tenant_id}/documents/{document_id}/versions/{version_id}/file", {
      params: { path: { ...documentPath(tenantId, documentId), version_id: versionId } },
    }),
  );
}

export function linkLanguageVariant(
  tenantId: string,
  documentId: string,
  body: LanguageVariantLink,
): Promise<DocumentRead> {
  return unwrap(
    client.POST("/api/v1/app/tenants/{tenant_id}/documents/{document_id}/language-variants", {
      params: { path: documentPath(tenantId, documentId) },
      body,
    }),
  );
}

export function unlinkLanguageVariant(
  tenantId: string,
  documentId: string,
  variantDocumentId: string,
): Promise<DocumentRead> {
  return unwrap(
    client.DELETE("/api/v1/app/tenants/{tenant_id}/documents/{document_id}/language-variants/{variant_document_id}", {
      params: { path: { ...documentPath(tenantId, documentId), variant_document_id: variantDocumentId } },
    }),
  );
}

// Manufacturer app: products (API.md §3.4)

export function listProducts(tenantId: string): Promise<Page_ProductRead_> {
  return unwrap(client.GET("/api/v1/app/tenants/{tenant_id}/products", { params: { path: tenantPath(tenantId) } }));
}

export function createProduct(tenantId: string, body: ProductCreate): Promise<ProductRead> {
  return unwrap(
    client.POST("/api/v1/app/tenants/{tenant_id}/products", { params: { path: tenantPath(tenantId) }, body }),
  );
}

function productPath(tenantId: string, productId: string) {
  return { ...tenantPath(tenantId), product_id: productId };
}

export function getProduct(tenantId: string, productId: string): Promise<ProductRead> {
  return unwrap(
    client.GET("/api/v1/app/tenants/{tenant_id}/products/{product_id}", {
      params: { path: productPath(tenantId, productId) },
    }),
  );
}

export function updateProduct(tenantId: string, productId: string, body: ProductUpdate): Promise<ProductRead> {
  return unwrap(
    client.PATCH("/api/v1/app/tenants/{tenant_id}/products/{product_id}", {
      params: { path: productPath(tenantId, productId) },
      body,
    }),
  );
}

export function listProductDocuments(tenantId: string, productId: string): Promise<Page_DocumentListItem_> {
  return unwrap(
    client.GET("/api/v1/app/tenants/{tenant_id}/products/{product_id}/documents", {
      params: { path: productPath(tenantId, productId) },
    }),
  );
}

export function setProductDocuments(
  tenantId: string,
  productId: string,
  body: ProductDocumentsSet,
): Promise<Page_DocumentListItem_> {
  return unwrap(
    client.PUT("/api/v1/app/tenants/{tenant_id}/products/{product_id}/documents", {
      params: { path: productPath(tenantId, productId) },
      body,
    }),
  );
}

export function getProductLanguageMatrix(tenantId: string, productId: string): Promise<LanguageMatrixRead> {
  return unwrap(
    client.GET("/api/v1/app/tenants/{tenant_id}/products/{product_id}/languages", {
      params: { path: productPath(tenantId, productId) },
    }),
  );
}

export function listProductReleases(tenantId: string, productId: string): Promise<Page_ProductReleaseRead_> {
  return unwrap(
    client.GET("/api/v1/app/tenants/{tenant_id}/products/{product_id}/releases", {
      params: { path: productPath(tenantId, productId) },
    }),
  );
}

export function getProductRelease(
  tenantId: string,
  productId: string,
  releaseNo: number,
): Promise<ProductReleaseDetailRead> {
  return unwrap(
    client.GET("/api/v1/app/tenants/{tenant_id}/products/{product_id}/releases/{release_no}", {
      params: { path: { ...productPath(tenantId, productId), release_no: releaseNo } },
    }),
  );
}

// Manufacturer app: customers and deliveries (API.md §3.5)

export function listCustomers(tenantId: string): Promise<Page_CustomerRead_> {
  return unwrap(client.GET("/api/v1/app/tenants/{tenant_id}/customers", { params: { path: tenantPath(tenantId) } }));
}

export function createCustomer(tenantId: string, body: CustomerCreate): Promise<CustomerRead> {
  return unwrap(
    client.POST("/api/v1/app/tenants/{tenant_id}/customers", { params: { path: tenantPath(tenantId) }, body }),
  );
}

export function getCustomer(tenantId: string, customerId: string): Promise<CustomerRead> {
  return unwrap(
    client.GET("/api/v1/app/tenants/{tenant_id}/customers/{customer_id}", {
      params: { path: { ...tenantPath(tenantId), customer_id: customerId } },
    }),
  );
}

export function updateCustomer(tenantId: string, customerId: string, body: CustomerUpdate): Promise<CustomerRead> {
  return unwrap(
    client.PATCH("/api/v1/app/tenants/{tenant_id}/customers/{customer_id}", {
      params: { path: { ...tenantPath(tenantId), customer_id: customerId } },
      body,
    }),
  );
}

export function listDeliveries(tenantId: string, query: ListDeliveriesQuery): Promise<Page_DeliveryListItem_> {
  return unwrap(
    client.GET("/api/v1/app/tenants/{tenant_id}/deliveries", { params: { path: tenantPath(tenantId), query } }),
  );
}

export function createDelivery(tenantId: string, body: DeliveryCreate): Promise<DeliveryRead> {
  return unwrap(
    client.POST("/api/v1/app/tenants/{tenant_id}/deliveries", { params: { path: tenantPath(tenantId) }, body }),
  );
}

export function getDelivery(tenantId: string, deliveryId: string): Promise<DeliveryRead> {
  return unwrap(
    client.GET("/api/v1/app/tenants/{tenant_id}/deliveries/{delivery_id}", {
      params: { path: { ...tenantPath(tenantId), delivery_id: deliveryId } },
    }),
  );
}
