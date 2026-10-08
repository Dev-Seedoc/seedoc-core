import { Building2, Loader2, Plus, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { EmptyState } from "@/components/common/EmptyState";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { getErrorMessage } from "@/lib/api/errors";
import { useStaffTenants } from "@/lib/api/hooks/staff";
import { formatDate } from "@/lib/formatDate";

import { CreateTenantDialog } from "./CreateTenantDialog";

export function StaffTenantsPage() {
  const { t } = useTranslation();
  const tenants = useStaffTenants();
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  const createButton = (
    <Button
      onClick={() => {
        setIsCreateOpen(true);
      }}
    >
      <Plus aria-hidden="true" />
      {t("staff.tenants.create")}
    </Button>
  );

  function renderContent() {
    if (tenants.isPending) {
      return (
        <div className="flex justify-center py-12">
          <Loader2 className="text-muted-foreground size-6 animate-spin" aria-hidden="true" />
          <span className="sr-only">{t("shell.loading")}</span>
        </div>
      );
    }

    if (tenants.isError) {
      return (
        <EmptyState
          icon={TriangleAlert}
          title={t("shell.loadFailed.title")}
          description={getErrorMessage(tenants.error)}
          action={
            <Button variant="outline" onClick={() => void tenants.refetch()}>
              {t("common.actions.retry")}
            </Button>
          }
        />
      );
    }

    const items = tenants.data.pages.flatMap((page) => page.items);
    if (items.length === 0) {
      return (
        <EmptyState
          icon={Building2}
          title={t("staff.tenants.emptyTitle")}
          description={t("staff.tenants.emptyDescription")}
          action={createButton}
        />
      );
    }

    return (
      <div className="flex flex-col gap-4">
        <div className="rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("staff.tenants.name")}</TableHead>
                <TableHead>{t("staff.tenants.slug")}</TableHead>
                <TableHead>{t("staff.tenants.status")}</TableHead>
                <TableHead className="text-right">{t("staff.tenants.memberCount")}</TableHead>
                <TableHead>{t("staff.tenants.createdAt")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((tenant) => (
                <TableRow key={tenant.id}>
                  <TableCell className="font-medium">
                    <Link to={`/staff/tenants/${tenant.id}`} className="hover:underline">
                      {tenant.name}
                    </Link>
                  </TableCell>
                  <TableCell className="text-muted-foreground font-mono text-xs">{tenant.slug}</TableCell>
                  <TableCell>
                    <StatusBadge status={tenant.status} />
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{tenant.member_count}</TableCell>
                  <TableCell>{formatDate(tenant.created_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        {tenants.hasNextPage && (
          <div className="flex justify-center">
            <Button
              variant="outline"
              disabled={tenants.isFetchingNextPage}
              onClick={() => void tenants.fetchNextPage()}
            >
              {t("staff.tenants.loadMore")}
            </Button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight">{t("staff.tenants.title")}</h1>
        {createButton}
      </div>
      {renderContent()}
      <CreateTenantDialog open={isCreateOpen} onOpenChange={setIsCreateOpen} />
    </div>
  );
}
