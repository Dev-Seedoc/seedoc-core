import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useSyncExternalStore } from "react";

import { useMe } from "@/lib/api/hooks/auth";
import { queryKeys } from "@/lib/api/queryKeys";
import type { TenantMembershipRead } from "@/lib/api/types";

// App URLs carry no tenant (NAMING §7), so the chosen tenant is remembered in this browser. It is only a
// convenience: if it is missing, blocked, or no longer one of the user's memberships, the first membership is used.
const STORAGE_KEY = "seedoc.currentTenantId";

const listeners = new Set<() => void>();

function readStoredTenantId(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStoredTenantId(tenantId: string): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, tenantId);
  } catch {
    // Storage blocked (private mode): the choice lasts until reload.
  }
  for (const listener of listeners) {
    listener();
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  // Another tab switched tenant.
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

interface CurrentTenant {
  currentTenant: TenantMembershipRead | null;
  memberships: TenantMembershipRead[];
  switchTenant: (tenantId: string) => void;
}

export function useCurrentTenant(): CurrentTenant {
  const queryClient = useQueryClient();
  const { data: me } = useMe();
  const storedTenantId = useSyncExternalStore(subscribe, readStoredTenantId);

  const memberships = me?.memberships ?? [];
  const currentTenant = memberships.find((m) => m.tenant_id === storedTenantId) ?? memberships[0] ?? null;
  const currentTenantId = currentTenant?.tenant_id;

  const switchTenant = useCallback(
    (tenantId: string) => {
      if (tenantId === currentTenantId) {
        return;
      }
      // Never keep one tenant's data around while another tenant is shown.
      if (currentTenantId) {
        queryClient.removeQueries({ queryKey: queryKeys.tenants.all(currentTenantId) });
      }
      writeStoredTenantId(tenantId);
    },
    [currentTenantId, queryClient],
  );

  return { currentTenant, memberships, switchTenant };
}
