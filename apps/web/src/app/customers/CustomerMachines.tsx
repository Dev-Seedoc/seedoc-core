import { useQueries } from "@tanstack/react-query";
import { Factory } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { EmptyState } from "@/components/common/EmptyState";
import { LoadFailed } from "@/components/common/LoadFailed";
import { Spinner } from "@/components/common/Spinner";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { deliveryQueryOptions, useDeliveries } from "@/lib/api/hooks/customers";
import type { CustomerRead, DeliveryListItem, MachineListItem } from "@/lib/api/types";

// Every machine of the customer, over all its deliveries. API.md has no machine list per customer, so this loads the
// customer's deliveries and then each delivery (with its machines) on its own: one failing delivery does not hide
// the machines of the others.
export function CustomerMachines({ tenantId, customer }: { tenantId: string; customer: CustomerRead }) {
  const { t } = useTranslation();
  const deliveries = useDeliveries(tenantId, { customer_id: customer.id });
  const list = deliveries.data ?? [];
  const details = useQueries({
    queries: list.map((delivery) => deliveryQueryOptions(tenantId, delivery.id)),
  });

  let content;
  if (deliveries.isPending || details.some((detail) => detail.isPending)) {
    content = <Spinner />;
  } else if (deliveries.isError) {
    content = <LoadFailed title={t("deliveries.list.loadFailed")} onRetry={() => void deliveries.refetch()} />;
  } else {
    const rows: { delivery: DeliveryListItem; machine: MachineListItem }[] = [];
    const failed: { delivery: DeliveryListItem; retry: () => void }[] = [];
    list.forEach((delivery, index) => {
      const detail = details[index];
      if (detail?.isError) {
        failed.push({ delivery, retry: () => void detail.refetch() });
      }
      for (const machine of detail?.data?.machines ?? []) {
        rows.push({ delivery, machine });
      }
    });
    content = (
      <>
        {failed.map(({ delivery, retry }) => (
          <div
            key={delivery.id}
            role="alert"
            className="border-destructive/30 bg-destructive/10 text-destructive flex flex-wrap items-center justify-between gap-2 rounded-md border p-3 text-sm"
          >
            {t("customers.machines.deliveryFailed", { name: delivery.name })}
            <Button variant="outline" size="sm" onClick={retry}>
              {t("common.actions.retry")}
            </Button>
          </div>
        ))}
        {rows.length === 0 && failed.length === 0 ? (
          <EmptyState
            icon={Factory}
            title={t("customers.machines.emptyTitle")}
            description={t("customers.machines.emptyDescription")}
          />
        ) : (
          rows.length > 0 && <MachineTable rows={rows} />
        )}
      </>
    );
  }

  return (
    <section aria-labelledby="customer-machines" className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2 id="customer-machines" className="text-lg font-semibold">
          {t("customers.machines.title")}
        </h2>
        <p className="text-muted-foreground text-sm">{t("customers.machines.description")}</p>
      </div>
      {content}
    </section>
  );
}

function MachineTable({ rows }: { rows: { delivery: DeliveryListItem; machine: MachineListItem }[] }) {
  const { t } = useTranslation();
  return (
    <div className="rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("customers.machines.name")}</TableHead>
            <TableHead>{t("customers.machines.serialNo")}</TableHead>
            <TableHead>{t("customers.machines.product")}</TableHead>
            <TableHead>{t("customers.machines.delivery")}</TableHead>
            <TableHead>{t("customers.machines.status")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map(({ delivery, machine }) => (
            <TableRow key={machine.id}>
              <TableCell className="font-medium">{machine.name}</TableCell>
              <TableCell className="font-mono text-xs">{machine.serial_no}</TableCell>
              <TableCell>
                <Link to={`/products/${machine.product_id}`} className="hover:underline">
                  {machine.product_name}
                </Link>
              </TableCell>
              <TableCell>
                <Link to={`/deliveries/${delivery.id}`} className="hover:underline">
                  {delivery.name}
                </Link>
              </TableCell>
              <TableCell>
                <StatusBadge status={machine.archived_at ? "archived" : "active"} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
