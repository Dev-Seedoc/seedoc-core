// TanStack Query hooks for customers and deliveries (API.md §3.5). Names from the "Frontend fn / hook" column.
// The customer screens show load and save errors in place, so none of these use the global error toast.
import { queryOptions, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createCustomer,
  createDelivery,
  getCustomer,
  getDelivery,
  listCustomers,
  listDeliveries,
  updateCustomer,
} from "../endpoints";
import { queryKeys } from "../queryKeys";
import type { CustomerCreate, CustomerUpdate, DeliveryCreate, ListDeliveriesQuery } from "../types";

// The whole list in one page (`next_cursor` is always null for customers).
export function useCustomers(tenantId: string) {
  return useQuery({
    queryKey: queryKeys.tenants.customers(tenantId),
    queryFn: () => listCustomers(tenantId),
    select: (page) => page.items,
    meta: { errorToast: false },
  });
}

export function useCustomer(tenantId: string, customerId: string) {
  return useQuery({
    queryKey: queryKeys.tenants.customer(tenantId, customerId),
    queryFn: () => getCustomer(tenantId, customerId),
    meta: { errorToast: false },
  });
}

function useInvalidateCustomers(tenantId: string) {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: queryKeys.tenants.allCustomers(tenantId) });
}

export function useCreateCustomer(tenantId: string) {
  const invalidate = useInvalidateCustomers(tenantId);
  return useMutation({
    mutationFn: (body: CustomerCreate) => createCustomer(tenantId, body),
    meta: { errorToast: false },
    onSuccess: invalidate,
  });
}

export function useUpdateCustomer(tenantId: string, customerId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CustomerUpdate) => updateCustomer(tenantId, customerId, body),
    meta: { errorToast: false },
    // Delivery lists show the customer's name too.
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.tenants.allCustomers(tenantId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.tenants.allDeliveries(tenantId) }),
      ]),
  });
}

// Deliveries by name; `query` filters by customer and status. Never paged.
export function useDeliveries(tenantId: string, query: ListDeliveriesQuery) {
  return useQuery({
    queryKey: queryKeys.tenants.deliveries(tenantId, query),
    queryFn: () => listDeliveries(tenantId, query),
    select: (page) => page.items,
    meta: { errorToast: false },
  });
}

// Options of one delivery query, shared by useDelivery and by screens that load several deliveries at once with
// `useQueries` (the customer's "Maschinen" tab: API.md has no machine list per customer).
export function deliveryQueryOptions(tenantId: string, deliveryId: string) {
  return queryOptions({
    queryKey: queryKeys.tenants.delivery(tenantId, deliveryId),
    queryFn: () => getDelivery(tenantId, deliveryId),
    meta: { errorToast: false },
  });
}

export function useDelivery(tenantId: string, deliveryId: string) {
  return useQuery(deliveryQueryOptions(tenantId, deliveryId));
}

export function useCreateDelivery(tenantId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: DeliveryCreate) => createDelivery(tenantId, body),
    meta: { errorToast: false },
    // A new delivery changes its customer's `delivery_count`.
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.tenants.allDeliveries(tenantId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.tenants.allCustomers(tenantId) }),
      ]),
  });
}
