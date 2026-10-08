// TanStack Query hooks for /staff. Names from the "Frontend fn / hook" column of docs/API.md §6.
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { staffCreateTenant, staffGetTenant, staffListTenants, staffUpdateTenant } from "../endpoints";
import { queryKeys } from "../queryKeys";
import type { StaffTenantRead, StaffTenantUpdate } from "../types";

// Page by page via `next_cursor`; `fetchNextPage()` loads the next one ("Mehr laden").
export function useStaffTenants() {
  return useInfiniteQuery({
    queryKey: queryKeys.staff.tenantList(),
    queryFn: ({ pageParam }) => staffListTenants(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    // StaffTenantsPage shows a load error with a retry button.
    meta: { errorToast: false },
  });
}

export function useStaffCreateTenant() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: staffCreateTenant,
    // The create dialog shows a taken slug under its field.
    meta: { errorToast: false },
    onSuccess: (tenant: StaffTenantRead) => {
      queryClient.setQueryData(queryKeys.staff.tenant(tenant.id), tenant);
      return queryClient.invalidateQueries({ queryKey: queryKeys.staff.tenantList() });
    },
  });
}

export function useStaffTenant(tenantId: string) {
  return useQuery({
    queryKey: queryKeys.staff.tenant(tenantId),
    queryFn: () => staffGetTenant(tenantId),
    // StaffTenantDetailPage shows "not found" and load errors itself.
    meta: { errorToast: false },
  });
}

export function useStaffUpdateTenant(tenantId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: StaffTenantUpdate) => staffUpdateTenant(tenantId, body),
    onSuccess: (tenant: StaffTenantRead) => {
      queryClient.setQueryData(queryKeys.staff.tenant(tenant.id), tenant);
      return queryClient.invalidateQueries({ queryKey: queryKeys.staff.tenantList() });
    },
  });
}
