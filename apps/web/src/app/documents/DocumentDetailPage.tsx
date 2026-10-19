import { ArrowLeft, FileQuestion, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useNavigate, useParams } from "react-router";

import { EmptyState } from "@/components/common/EmptyState";
import { LoadFailed } from "@/components/common/LoadFailed";
import { Spinner } from "@/components/common/Spinner";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useCurrentTenant } from "@/hooks/useCurrentTenant";
import { getErrorCode } from "@/lib/api/errors";
import { useDocument } from "@/lib/api/hooks/documents";
import type { DocumentRead } from "@/lib/api/types";
import { formatDateTime } from "@/lib/formatDate";
import { getLanguageLabel } from "@/lib/languages";

import { DocumentMetadataForm } from "./DocumentMetadataForm";
import { DocumentVersions } from "./DocumentVersions";
import { LanguageVariants } from "./LanguageVariants";
import { RestoreDocumentsButton } from "./RestoreDocumentsButton";

// `/documents/:documentId` (NAMING §7).
export function DocumentDetailPage() {
  const { currentTenant } = useCurrentTenant();
  const { documentId = "" } = useParams();
  // AppLayout renders pages only for users with a tenant.
  return currentTenant ? <DocumentDetail tenantId={currentTenant.tenant_id} documentId={documentId} /> : null;
}

// Back to the list the user came from (with its folder, filters and tab); opened directly, to /documents.
function BackLink() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const cameFromApp = location.key !== "default";
  return (
    <Button variant="ghost" size="sm" className="self-start" asChild>
      <Link
        to="/documents"
        onClick={(event) => {
          if (cameFromApp) {
            event.preventDefault();
            void navigate(-1);
          }
        }}
      >
        <ArrowLeft aria-hidden="true" />
        {t("documents.detail.back")}
      </Link>
    </Button>
  );
}

function DocumentDetail({ tenantId, documentId }: { tenantId: string; documentId: string }) {
  const { t } = useTranslation();
  const document = useDocument(tenantId, documentId);

  let content;
  if (document.isPending) {
    content = <Spinner />;
  } else if (document.isError) {
    // Unknown, another tenant's or a malformed id: for the user, all mean "this link leads nowhere".
    const code = getErrorCode(document.error);
    content =
      code === "not_found" || code === "validation_failed" ? (
        <EmptyState
          icon={FileQuestion}
          title={t("documents.detail.notFoundTitle")}
          description={t("documents.detail.notFoundDescription")}
        />
      ) : (
        <LoadFailed title={t("documents.detail.loadFailed")} onRetry={() => void document.refetch()} />
      );
  } else {
    content = <DocumentOverview tenantId={tenantId} document={document.data} />;
  }

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <BackLink />
      {content}
    </div>
  );
}

function DocumentOverview({ tenantId, document }: { tenantId: string; document: DocumentRead }) {
  const { t } = useTranslation();
  const isTrashed = document.trashed_at !== null;

  const facts: [string, string][] = [
    [t("documents.table.docType"), t(`common.docType.${document.doc_type}`)],
    [t("documents.table.language"), getLanguageLabel(document.language, t)],
    [t("documents.table.accessLevel"), t(`common.accessLevel.${document.access_level}`)],
    [t("documents.detail.versionsCount"), String(document.versions_count)],
    [t("documents.detail.releasedIn"), String(document.released_in_count)],
    [t("documents.table.updatedAt"), formatDateTime(document.updated_at)],
  ];

  return (
    <>
      {isTrashed && document.trashed_at && (
        <div
          role="status"
          className="flex flex-wrap items-center gap-3 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
        >
          <Trash2 className="size-4 shrink-0" aria-hidden="true" />
          <span className="mr-auto">
            {t("documents.detail.trashedBanner", { date: formatDateTime(document.trashed_at) })}
          </span>
          <RestoreDocumentsButton tenantId={tenantId} documents={[document]} />
        </div>
      )}

      <header className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{document.title}</h1>
          {document.processing_status && <StatusBadge status={document.processing_status} />}
          {isTrashed && <Badge variant="outline">{t("documents.detail.trashed")}</Badge>}
        </div>
        <p className="text-muted-foreground text-sm">
          {document.folder_path}
          {document.current_version_no !== null &&
            ` · ${t("documents.table.versionNo", { no: document.current_version_no })}`}
        </p>
      </header>

      <section aria-labelledby="document-facts" className="rounded-lg border p-4">
        <h2 id="document-facts" className="sr-only">
          {t("documents.detail.facts")}
        </h2>
        <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-3">
          {facts.map(([label, value]) => (
            <div key={label} className="flex flex-col gap-0.5">
              <dt className="text-muted-foreground text-xs">{label}</dt>
              <dd className="text-sm">{value}</dd>
            </div>
          ))}
        </dl>
      </section>

      <DocumentMetadataForm tenantId={tenantId} document={document} />
      <LanguageVariants tenantId={tenantId} document={document} />
      <DocumentVersions tenantId={tenantId} document={document} />
    </>
  );
}
