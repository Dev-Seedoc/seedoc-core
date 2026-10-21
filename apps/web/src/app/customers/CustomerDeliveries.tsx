import { Plus, Truck } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { EmptyState } from "@/components/common/EmptyState";
import { LoadFailed } from "@/components/common/LoadFailed";
import { Spinner } from "@/components/common/Spinner";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useDeliveries } from "@/lib/api/hooks/customers";
import type { CustomerRead } from "@/lib/api/types";

import { CreateDeliveryDialog } from "./CreateDeliveryDialog";

// The customer's deliveries (API.md §3.5 `list_deliveries?customer_id=`), by name.
export function CustomerDeliveries({ tenantId, customer }: { tenantId: string; customer: CustomerRead }) {
  const { t } = useTranslation();
  const deliveries = useDeliveries(tenantId, { customer_id: customer.id });
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  const createButton = (
    <Button
      variant="outline"
      size="sm"
      onClick={() => {
        setIsCreateOpen(true);
      }}
    >
      <Plus aria-hidden="true" />
      {t("deliveries.create.open")}
    </Button>
  );

  let content;
  if (deliveries.isPending) {
    content = <Spinner />;
  } else if (deliveries.isError) {
    content = <LoadFailed title={t("deliveries.list.loadFailed")} onRetry={() => void deliveries.refetch()} />;
  } else if (deliveries.data.length === 0) {
    content = (
      <EmptyState
        icon={Truck}
        title={t("deliveries.list.emptyTitle")}
        description={t("deliveries.list.emptyDescription")}
        action={createButton}
      />
    );
  } else {
    content = (
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("deliveries.list.name")}</TableHead>
              <TableHead>{t("deliveries.list.kind")}</TableHead>
              <TableHead>{t("deliveries.list.orderNo")}</TableHead>
              <TableHead>{t("deliveries.list.status")}</TableHead>
              <TableHead className="text-right">{t("deliveries.list.machines")}</TableHead>
              <TableHead>{t("deliveries.list.release")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {deliveries.data.map((delivery) => (
              <TableRow key={delivery.id}>
                <TableCell className="font-medium">
                  <Link to={`/deliveries/${delivery.id}`} className="hover:underline">
                    {delivery.name}
                  </Link>
                </TableCell>
                <TableCell>{t(`deliveries.kind.${delivery.kind}`)}</TableCell>
                <TableCell>{delivery.order_no ?? "—"}</TableCell>
                <TableCell>
                  <StatusBadge status={delivery.status} />
                </TableCell>
                <TableCell className="text-right tabular-nums">{delivery.machine_count}</TableCell>
                <TableCell>
                  {delivery.current_release_no === null
                    ? "—"
                    : t("deliveries.list.releaseNo", { no: delivery.current_release_no })}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    );
  }

  return (
    <section aria-labelledby="customer-deliveries" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="customer-deliveries" className="text-lg font-semibold">
          {t("deliveries.list.title")}
        </h2>
        {deliveries.data && deliveries.data.length > 0 && createButton}
      </div>
      {content}
      <CreateDeliveryDialog
        tenantId={tenantId}
        customer={customer}
        open={isCreateOpen}
        onClose={() => {
          setIsCreateOpen(false);
        }}
      />
    </section>
  );
}
