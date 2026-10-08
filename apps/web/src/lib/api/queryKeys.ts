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
  },
  // Staff data is not tenant-scoped (admin DB engine); logout drops it like every non-auth query.
  staff: {
    all: () => ["staff"] as const,
    tenantList: () => ["staff", "tenants", "list"] as const,
    tenant: (tenantId: string) => ["staff", "tenants", tenantId] as const,
  },
} as const;
