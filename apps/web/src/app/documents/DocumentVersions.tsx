import { Download, FileUp, Loader2 } from "lucide-react";
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { toast } from "sonner";

import { LoadFailed } from "@/components/common/LoadFailed";
import { Spinner } from "@/components/common/Spinner";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { getVersionFileUrl } from "@/lib/api/endpoints";
import { getErrorMessage } from "@/lib/api/errors";
import { useCreateDocumentVersion, useDocumentVersions } from "@/lib/api/hooks/documents";
import type { DocumentRead, DocumentVersionRead } from "@/lib/api/types";
import { formatDateTime } from "@/lib/formatDate";
import { formatBytes } from "@/lib/formatNumber";
import { checkPdf } from "@/lib/pdfCheck";
import { startDownload } from "@/lib/startDownload";

import { getUploadErrorMessage, type PdfUploadStep, usePdfUpload } from "./usePdfUpload";

interface DocumentVersionsProps {
  tenantId: string;
  document: DocumentRead;
}

// Every version of the document, newest first, with download and "Neue Version hochladen" (API.md §3.3).
export function DocumentVersions({ tenantId, document }: DocumentVersionsProps) {
  const { t } = useTranslation();
  const versions = useDocumentVersions(tenantId, document.id);

  let content;
  if (versions.isPending) {
    content = <Spinner />;
  } else if (versions.isError) {
    content = <LoadFailed title={t("documents.versions.loadFailed")} onRetry={() => void versions.refetch()} />;
  } else {
    content = <VersionTable tenantId={tenantId} versions={versions.data} />;
  }

  return (
    <section aria-labelledby="document-versions" className="flex flex-col gap-4 rounded-lg border p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="document-versions" className="text-lg font-semibold">
          {t("documents.versions.title")}
        </h2>
        <NewVersionButton tenantId={tenantId} document={document} />
      </div>
      {content}
    </section>
  );
}

function VersionTable({ tenantId, versions }: { tenantId: string; versions: DocumentVersionRead[] }) {
  const { t } = useTranslation();
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  // The link is valid for 120 s, so it is fetched only now, right before the download.
  async function handleDownload(version: DocumentVersionRead) {
    setDownloadingId(version.id);
    try {
      const { url } = await getVersionFileUrl(tenantId, version.document_id, version.id);
      startDownload(url);
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setDownloadingId(null);
    }
  }

  return (
    <div className="rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("documents.versions.version")}</TableHead>
            <TableHead>{t("documents.versions.file")}</TableHead>
            <TableHead className="text-right">{t("documents.versions.size")}</TableHead>
            <TableHead className="text-right">{t("documents.versions.pages")}</TableHead>
            <TableHead>{t("documents.table.status")}</TableHead>
            <TableHead>{t("documents.versions.uploadedAt")}</TableHead>
            <TableHead>
              <span className="sr-only">{t("documents.table.actions")}</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {versions.map((version) => (
            <TableRow key={version.id}>
              <TableCell className="whitespace-nowrap">
                <span className="tabular-nums">{t("documents.table.versionNo", { no: version.version_no })}</span>
                {version.is_current && (
                  <Badge variant="secondary" className="ml-2">
                    {t("documents.versions.current")}
                  </Badge>
                )}
              </TableCell>
              <TableCell className="max-w-56 truncate" title={version.file_name}>
                {version.file_name}
              </TableCell>
              <TableCell className="text-right tabular-nums">{formatBytes(version.size_bytes)}</TableCell>
              <TableCell className="text-right tabular-nums">{version.page_count ?? "—"}</TableCell>
              <TableCell>
                <div className="flex flex-col gap-1">
                  <StatusBadge status={version.processing_status} />
                  {version.processing_error && (
                    <span className="text-destructive max-w-64 text-xs">{version.processing_error}</span>
                  )}
                </div>
              </TableCell>
              <TableCell className="whitespace-nowrap tabular-nums">{formatDateTime(version.created_at)}</TableCell>
              <TableCell className="text-right">
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={downloadingId === version.id}
                  aria-label={t("documents.versions.downloadVersion", { no: version.version_no })}
                  onClick={() => void handleDownload(version)}
                >
                  <Download aria-hidden="true" />
                  {t("common.actions.download")}
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

type NewVersionState =
  | { name: "idle" }
  | PdfUploadStep
  | { name: "creating" }
  | { name: "done"; versionNo: number; duplicateOf: string | null };

// Uploads a new PDF as the next version; it becomes current at once (API.md §3.3). Not for a trashed document
// (the API answers 409).
function NewVersionButton({ tenantId, document }: { tenantId: string; document: DocumentRead }) {
  const { t } = useTranslation();
  const inputId = useId();
  const uploadPdf = usePdfUpload(tenantId);
  const createVersion = useCreateDocumentVersion(tenantId, document.id);
  const [state, setState] = useState<NewVersionState>({ name: "idle" });
  const isBusy = state.name === "hashing" || state.name === "uploading" || state.name === "creating";
  const isTrashed = document.trashed_at !== null;

  async function handleFile(file: File) {
    const problem = await checkPdf(file);
    if (problem) {
      toast.error(t(`documents.upload.problem.${problem}`));
      return;
    }
    try {
      const uploadId = await uploadPdf(file, setState);
      setState({ name: "creating" });
      const version = await createVersion.mutateAsync({ upload_id: uploadId });
      toast.success(t("documents.versions.uploaded", { no: version.version_no }));
      setState({ name: "done", versionNo: version.version_no, duplicateOf: version.duplicate_of_document_id ?? null });
    } catch (error) {
      toast.error(getUploadErrorMessage(error, t));
      setState({ name: "idle" });
    }
  }

  let progress = null;
  if (state.name === "uploading") {
    progress = t("documents.upload.phase.uploading", { percent: Math.round(state.progress * 100) });
  } else if (state.name === "hashing" || state.name === "creating") {
    progress = t(`documents.upload.phase.${state.name}`);
  }

  return (
    <div className="flex flex-col items-end gap-1">
      {/* Always the real label of the file input, also when locked: the input itself is disabled then. */}
      <Button
        variant="outline"
        size="sm"
        asChild
        aria-disabled={isTrashed || isBusy ? true : undefined}
        className={isTrashed || isBusy ? "pointer-events-none opacity-50" : undefined}
      >
        <label htmlFor={inputId} className="cursor-pointer">
          <FileUp aria-hidden="true" />
          {t("documents.versions.upload")}
        </label>
      </Button>
      <input
        id={inputId}
        type="file"
        accept="application/pdf,.pdf"
        className="sr-only"
        disabled={isTrashed || isBusy}
        onChange={(event) => {
          const file = event.target.files?.[0];
          // The same file can be chosen again later.
          event.target.value = "";
          if (file) {
            void handleFile(file);
          }
        }}
      />
      {progress && (
        <span className="text-muted-foreground flex items-center gap-1.5 text-xs" aria-live="polite">
          <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
          {progress}
        </span>
      )}
      {state.name === "done" && state.duplicateOf && (
        <span className="text-xs text-amber-700 dark:text-amber-400">
          {t("documents.upload.duplicateHint")}{" "}
          <Link to={`/documents/${state.duplicateOf}`} className="underline underline-offset-4">
            {t("documents.upload.openDuplicate")}
          </Link>
        </span>
      )}
    </div>
  );
}
