import { ArrowLeft, Building2, Loader2, TriangleAlert } from "lucide-react";
import { type ReactNode, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";

import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { EmptyState } from "@/components/common/EmptyState";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { getErrorCode, getErrorMessage } from "@/lib/api/errors";
import { useStaffTenant, useStaffUpdateTenant } from "@/lib/api/hooks/staff";
import type { StaffTenantRead } from "@/lib/api/types";
import { formatDate, formatDateTime } from "@/lib/formatDate";

function BackLink() {
  const { t } = useTranslation();

  return (
    <Link
      to="/staff"
      className="text-muted-foreground hover:text-foreground inline-flex w-fit items-center gap-1.5 text-sm"
    >
      <ArrowLeft className="size-4" aria-hidden="true" />
      {t("staff.tenantDetail.back")}
    </Link>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function StatusAction({ tenant }: { tenant: StaffTenantRead }) {
  const { t } = useTranslation();
  const updateTenant = useStaffUpdateTenant(tenant.id);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const isActive = tenant.status === "active";

  function handleConfirm() {
    updateTenant.mutate(
      { status: isActive ? "inactive" : "active" },
      {
        onSuccess: () => {
          setIsConfirmOpen(false);
        },
      },
    );
  }

  return (
    <>
      <Button
        variant={isActive ? "destructive" : "default"}
        onClick={() => {
          setIsConfirmOpen(true);
        }}
      >
        {isActive ? t("staff.tenantDetail.deactivate") : t("staff.tenantDetail.activate")}
      </Button>
      <ConfirmDialog
        open={isConfirmOpen}
        onOpenChange={setIsConfirmOpen}
        title={isActive ? t("staff.tenantDetail.deactivateTitle") : t("staff.tenantDetail.activateTitle")}
        description={
          isActive ? t("staff.tenantDetail.deactivateDescription") : t("staff.tenantDetail.activateDescription")
        }
        confirmLabel={isActive ? t("staff.tenantDetail.deactivate") : t("staff.tenantDetail.activate")}
        variant={isActive ? "destructive" : "default"}
        isPending={updateTenant.isPending}
        onConfirm={handleConfirm}
      />
    </>
  );
}

function TenantDetail({ tenant }: { tenant: StaffTenantRead }) {
  const { t } = useTranslation();

  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">{tenant.name}</h1>
            <StatusBadge status={tenant.status} />
          </div>
          <dl className="text-muted-foreground flex flex-wrap gap-x-6 gap-y-1 text-sm">
            <div className="flex gap-1.5">
              <dt>{t("staff.tenantDetail.slug")}:</dt>
              <dd className="text-foreground font-mono">{tenant.slug}</dd>
            </div>
            <div className="flex gap-1.5">
              <dt>{t("staff.tenantDetail.createdAt")}:</dt>
              <dd className="text-foreground">{formatDate(tenant.created_at)}</dd>
            </div>
            <div className="flex gap-1.5">
              <dt>{t("staff.tenantDetail.updatedAt")}:</dt>
              <dd className="text-foreground">{formatDateTime(tenant.updated_at)}</dd>
            </div>
          </dl>
        </div>
        <StatusAction tenant={tenant} />
      </div>

      <Section title={t("staff.tenantDetail.members")}>
        {tenant.members.length === 0 ? (
          <p className="text-muted-foreground text-sm">{t("staff.tenantDetail.membersEmpty")}</p>
        ) : (
          <div className="rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("staff.tenantDetail.name")}</TableHead>
                  <TableHead>{t("staff.tenantDetail.email")}</TableHead>
                  <TableHead>{t("staff.tenantDetail.role")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tenant.members.map((member) => (
                  <TableRow key={member.user_id}>
                    <TableCell>{member.full_name ?? "—"}</TableCell>
                    <TableCell>{member.email}</TableCell>
                    <TableCell>{t(`common.memberRole.${member.role}`)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Section>

      <Section title={t("staff.tenantDetail.invitations")}>
        {tenant.open_invitations.length === 0 ? (
          <p className="text-muted-foreground text-sm">{t("staff.tenantDetail.invitationsEmpty")}</p>
        ) : (
          <div className="rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("staff.tenantDetail.email")}</TableHead>
                  <TableHead>{t("staff.tenantDetail.role")}</TableHead>
                  <TableHead>{t("staff.tenantDetail.expiresAt")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tenant.open_invitations.map((invitation) => (
                  <TableRow key={invitation.id}>
                    <TableCell>{invitation.email}</TableCell>
                    <TableCell>{invitation.role ? t(`common.memberRole.${invitation.role}`) : "—"}</TableCell>
                    <TableCell>{formatDateTime(invitation.expires_at)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Section>
    </>
  );
}

export function StaffTenantDetailPage() {
  const { t } = useTranslation();
  const { tenantId = "" } = useParams();
  const tenant = useStaffTenant(tenantId);

  function renderContent() {
    if (tenant.isPending) {
      return (
        <div className="flex justify-center py-12">
          <Loader2 className="text-muted-foreground size-6 animate-spin" aria-hidden="true" />
          <span className="sr-only">{t("shell.loading")}</span>
        </div>
      );
    }

    if (tenant.isError) {
      // A malformed ID fails validation; for the user both mean "this link leads nowhere".
      const code = getErrorCode(tenant.error);
      if (code === "not_found" || code === "validation_failed") {
        return (
          <EmptyState
            icon={Building2}
            title={t("staff.tenantDetail.notFoundTitle")}
            description={t("staff.tenantDetail.notFoundDescription")}
          />
        );
      }
      return (
        <EmptyState
          icon={TriangleAlert}
          title={t("shell.loadFailed.title")}
          description={getErrorMessage(tenant.error)}
          action={
            <Button variant="outline" onClick={() => void tenant.refetch()}>
              {t("common.actions.retry")}
            </Button>
          }
        />
      );
    }

    return <TenantDetail tenant={tenant.data} />;
  }

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <BackLink />
      {renderContent()}
    </div>
  );
}
