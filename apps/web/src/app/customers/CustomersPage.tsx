import { Plus, Users } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router";

import { EmptyState } from "@/components/common/EmptyState";
import { LoadFailed } from "@/components/common/LoadFailed";
import { Spinner } from "@/components/common/Spinner";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useCurrentTenant } from "@/hooks/useCurrentTenant";
import { useCustomers } from "@/lib/api/hooks/customers";
import type { CustomerRead } from "@/lib/api/types";

import { CreateCustomerDialog } from "./CreateCustomerDialog";

// `/customers` (NAMING §7): every customer of the tenant, by name (API order).
export function CustomersPage() {
  const { currentTenant } = useCurrentTenant();
  // AppLayout renders pages only for users with a tenant.
  return currentTenant ? <CustomerList tenantId={currentTenant.tenant_id} /> : null;
}

function CustomerList({ tenantId }: { tenantId: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const customers = useCustomers(tenantId);
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  const createButton = (
    <Button
      onClick={() => {
        setIsCreateOpen(true);
      }}
    >
      <Plus aria-hidden="true" />
      {t("customers.create.open")}
    </Button>
  );

  let content;
  if (customers.isPending) {
    content = <Spinner />;
  } else if (customers.isError) {
    content = <LoadFailed title={t("customers.list.loadFailed")} onRetry={() => void customers.refetch()} />;
  } else if (customers.data.length === 0) {
    content = (
      <EmptyState
        icon={Users}
        title={t("customers.list.emptyTitle")}
        description={t("customers.list.emptyDescription")}
        action={createButton}
      />
    );
  } else {
    content = <CustomerTable customers={customers.data} />;
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight">{t("customers.list.title")}</h1>
        {customers.data && customers.data.length > 0 && createButton}
      </div>
      {content}
      <CreateCustomerDialog
        tenantId={tenantId}
        open={isCreateOpen}
        onClose={() => {
          setIsCreateOpen(false);
        }}
        onCreated={(customer) => {
          setIsCreateOpen(false);
          void navigate(`/customers/${customer.id}`);
        }}
      />
    </div>
  );
}

function CustomerTable({ customers }: { customers: CustomerRead[] }) {
  const { t } = useTranslation();
  return (
    <div className="rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("customers.list.name")}</TableHead>
            <TableHead>{t("customers.list.contactName")}</TableHead>
            <TableHead>{t("customers.list.contactEmail")}</TableHead>
            <TableHead className="text-right">{t("customers.list.deliveries")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {customers.map((customer) => (
            <TableRow key={customer.id}>
              <TableCell className="font-medium">
                <Link to={`/customers/${customer.id}`} className="hover:underline">
                  {customer.name}
                </Link>
              </TableCell>
              <TableCell>{customer.contact_name ?? "—"}</TableCell>
              <TableCell>
                {customer.contact_email ? (
                  <a href={`mailto:${customer.contact_email}`} className="hover:underline">
                    {customer.contact_email}
                  </a>
                ) : (
                  "—"
                )}
              </TableCell>
              <TableCell className="text-right tabular-nums">{customer.delivery_count}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
