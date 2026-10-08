import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { queryKeys } from "@/lib/api/queryKeys";
import type { MeRead } from "@/lib/api/types";

import { useCurrentTenant } from "./useCurrentTenant";

const TENANT_A = "00000000-0000-4000-8000-00000000000a";
const TENANT_B = "00000000-0000-4000-8000-00000000000b";

const ME: MeRead = {
  user: { id: "00000000-0000-4000-8000-000000000001", email: "owner@example.com", full_name: "Olga Owner" },
  memberships: [
    { tenant_id: TENANT_A, tenant_name: "Alpha Maschinenbau", role: "owner" },
    { tenant_id: TENANT_B, tenant_name: "Beta Anlagen", role: "editor" },
  ],
  operator_orgs: [],
  is_staff: false,
  mfa_verified: false,
};

function setup(me: MeRead = ME) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: false } } });
  queryClient.setQueryData(queryKeys.auth.me(), me);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { queryClient, ...renderHook(() => useCurrentTenant(), { wrapper }) };
}

afterEach(() => {
  window.localStorage.clear();
});

describe("useCurrentTenant", () => {
  it("uses the first membership when nothing is stored", () => {
    const { result } = setup();

    expect(result.current.currentTenant?.tenant_name).toBe("Alpha Maschinenbau");
    expect(result.current.memberships).toHaveLength(2);
  });

  it("switches tenant and remembers the choice", () => {
    const { result } = setup();

    act(() => {
      result.current.switchTenant(TENANT_B);
    });

    expect(result.current.currentTenant?.tenant_name).toBe("Beta Anlagen");
    expect(window.localStorage.getItem("seedoc.currentTenantId")).toBe(TENANT_B);
  });

  it("ignores a stored tenant the user no longer belongs to", () => {
    window.localStorage.setItem("seedoc.currentTenantId", "00000000-0000-4000-8000-0000000000ff");

    const { result } = setup();

    expect(result.current.currentTenant?.tenant_id).toBe(TENANT_A);
  });

  it("drops the previous tenant's cached data when switching", () => {
    const { result, queryClient } = setup();
    queryClient.setQueryData([...queryKeys.tenants.all(TENANT_A), "documents"], ["cached"]);

    act(() => {
      result.current.switchTenant(TENANT_B);
    });

    expect(queryClient.getQueryData([...queryKeys.tenants.all(TENANT_A), "documents"])).toBeUndefined();
  });

  it("returns no tenant for a user without memberships", () => {
    const { result } = setup({ ...ME, memberships: [] });

    expect(result.current.currentTenant).toBeNull();
  });
});
