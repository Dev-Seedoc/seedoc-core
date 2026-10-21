// TanStack Query hooks for products (API.md §3.4). Names from the "Frontend fn / hook" column. Every query lives
// under `queryKeys.tenants.allProducts`, so one invalidation refreshes counts, the set, the matrix and the list.
// The product screens show load and save errors in place, so none of these use the global error toast.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createProduct,
  getProduct,
  getProductLanguageMatrix,
  getProductRelease,
  listProductDocuments,
  listProductReleases,
  listProducts,
  setProductDocuments,
  updateProduct,
} from "../endpoints";
import { queryKeys } from "../queryKeys";
import type { ProductCreate, ProductDocumentsSet, ProductUpdate } from "../types";

// The whole list in one page (`next_cursor` is always null for products).
export function useProducts(tenantId: string) {
  return useQuery({
    queryKey: queryKeys.tenants.products(tenantId),
    queryFn: () => listProducts(tenantId),
    select: (page) => page.items,
    meta: { errorToast: false },
  });
}

export function useProduct(tenantId: string, productId: string) {
  return useQuery({
    queryKey: queryKeys.tenants.product(tenantId, productId),
    queryFn: () => getProduct(tenantId, productId),
    meta: { errorToast: false },
  });
}

export function useProductDocuments(tenantId: string, productId: string) {
  return useQuery({
    queryKey: queryKeys.tenants.productDocuments(tenantId, productId),
    queryFn: () => listProductDocuments(tenantId, productId),
    select: (page) => page.items,
    meta: { errorToast: false },
  });
}

export function useProductLanguageMatrix(tenantId: string, productId: string) {
  return useQuery({
    queryKey: queryKeys.tenants.productLanguageMatrix(tenantId, productId),
    queryFn: () => getProductLanguageMatrix(tenantId, productId),
    meta: { errorToast: false },
  });
}

export function useProductReleases(tenantId: string, productId: string) {
  return useQuery({
    queryKey: queryKeys.tenants.productReleases(tenantId, productId),
    queryFn: () => listProductReleases(tenantId, productId),
    select: (page) => page.items,
    meta: { errorToast: false },
  });
}

// One release with its frozen items; loaded only when `releaseNo` is set (the row the user opened).
export function useProductRelease(tenantId: string, productId: string, releaseNo: number | null) {
  return useQuery({
    queryKey: queryKeys.tenants.productRelease(tenantId, productId, releaseNo ?? 0),
    queryFn: () => getProductRelease(tenantId, productId, releaseNo ?? 0),
    enabled: releaseNo !== null,
    meta: { errorToast: false },
  });
}

// A product change can move it in the list (name) and change its matrix (languages); the set changes counts, the
// matrix and the list. So every mutation reloads the whole products prefix.
function useInvalidateProducts(tenantId: string) {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: queryKeys.tenants.allProducts(tenantId) });
}

export function useCreateProduct(tenantId: string) {
  const invalidate = useInvalidateProducts(tenantId);
  return useMutation({
    mutationFn: (body: ProductCreate) => createProduct(tenantId, body),
    meta: { errorToast: false },
    onSuccess: invalidate,
  });
}

export function useUpdateProduct(tenantId: string, productId: string) {
  const invalidate = useInvalidateProducts(tenantId);
  return useMutation({
    mutationFn: (body: ProductUpdate) => updateProduct(tenantId, productId, body),
    meta: { errorToast: false },
    onSuccess: invalidate,
  });
}

export function useSetProductDocuments(tenantId: string, productId: string) {
  const invalidate = useInvalidateProducts(tenantId);
  return useMutation({
    mutationFn: (body: ProductDocumentsSet) => setProductDocuments(tenantId, productId, body),
    meta: { errorToast: false },
    onSuccess: invalidate,
  });
}
