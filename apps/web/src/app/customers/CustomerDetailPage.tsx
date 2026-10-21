import { UserX } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";

import { BackLink } from "@/components/common/BackLink";
import { EmptyState } from "@/components/common/EmptyState";
import { LoadFailed } from "@/components/common/LoadFailed";
import { Spinner } from "@/components/common/Spinner";
import { UrlTabs } from "@/components/common/UrlTabs";
import { useCurrentTenant } from "@/hooks/useCurrentTenant";
import { getErrorCode } from "@/lib/api/errors";
import { useCustomer } from "@/lib/api/hooks/customers";
import type { CustomerRead } from "@/lib/api/types";

import { CustomerContactForm } from "./CustomerContactForm";
import { CustomerDeliveries } from "./CustomerDeliveries";
import { CustomerMachines } from "./CustomerMachines";

// NAMING §7: `?tab=machines|deliveries|operators`. "operators" waits for the operators API (§3.7, Raven), so the tab
// is left out until then rather than shown empty.
type CustomerTab = "machines" | "deliveries";

// `/customers/:customerId` (NAMING §7).
export function CustomerDetailPage() {
  const { currentTenant } = useCurrentTenant();
  const { customerId = "" } = useParams();
  // AppLayout renders pages only for users with a tenant.
  return currentTenant ? <CustomerDetail tenantId={currentTenant.tenant_id} customerId={customerId} /> : null;
}

function CustomerDetail({ tenantId, customerId }: { tenantId: string; customerId: string }) {
  const { t } = useTranslation();
  const customer = useCustomer(tenantId, customerId);

  let content;
  if (customer.isPending) {
    content = <Spinner />;
  } else if (customer.isError) {
    // Unknown, another tenant's or a malformed id: for the user, all mean "this link leads nowhere".
    const code = getErrorCode(customer.error);
    content =
      code === "not_found" || code === "validation_failed" ? (
        <EmptyState
          icon={UserX}
          title={t("customers.detail.notFoundTitle")}
          description={t("customers.detail.notFoundDescription")}
        />
      ) : (
        <LoadFailed title={t("customers.detail.loadFailed")} onRetry={() => void customer.refetch()} />
      );
  } else {
    content = <CustomerOverview tenantId={tenantId} customer={customer.data} />;
  }

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <BackLink to="/customers" label={t("customers.detail.back")} />
      {content}
    </div>
  );
}

function CustomerOverview({ tenantId, customer }: { tenantId: string; customer: CustomerRead }) {
  const { t } = useTranslation();
  const tabs = [
    { value: "machines", label: t("customers.tabs.machines") },
    { value: "deliveries", label: t("customers.tabs.deliveries") },
  ] as const satisfies readonly { value: CustomerTab; label: string }[];

  return (
    <>
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">{customer.name}</h1>
        <p className="text-muted-foreground text-sm">
          {t("customers.detail.summary", { count: customer.delivery_count })}
        </p>
      </header>

      <CustomerContactForm tenantId={tenantId} customer={customer} />

      <UrlTabs label={t("customers.tabs.label")} tabs={tabs}>
        {(tab) =>
          tab === "deliveries" ? (
            <CustomerDeliveries tenantId={tenantId} customer={customer} />
          ) : (
            <CustomerMachines tenantId={tenantId} customer={customer} />
          )
        }
      </UrlTabs>
    </>
  );
}
