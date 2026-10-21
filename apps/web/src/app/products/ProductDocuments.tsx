import { FileStack, ListChecks, X } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { toast } from "sonner";

import { EmptyState } from "@/components/common/EmptyState";
import { LoadFailed } from "@/components/common/LoadFailed";
import { Spinner } from "@/components/common/Spinner";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { getErrorMessage } from "@/lib/api/errors";
import { useProductDocuments, useSetProductDocuments } from "@/lib/api/hooks/products";
import type { DocumentListItem, ProductRead } from "@/lib/api/types";
import { getLanguageLabel } from "@/lib/languages";

import { ProductDocumentsPicker } from "./ProductDocumentsPicker";

// The product's document set (API.md §3.4): what its next release freezes. Trashed members are hidden by the API.
export function ProductDocuments({ tenantId, product }: { tenantId: string; product: ProductRead }) {
  const { t } = useTranslation();
  const documents = useProductDocuments(tenantId, product.id);
  const setDocuments = useSetProductDocuments(tenantId, product.id);
  const [isPickerOpen, setIsPickerOpen] = useState(false);

  // Removing one sends the rest as the new set.
  function handleRemove(document: DocumentListItem) {
    const rest = (documents.data ?? []).filter((item) => item.id !== document.id).map((item) => item.id);
    setDocuments.mutate(
      { document_ids: rest },
      {
        onSuccess: () => toast.success(t("products.documents.removed", { title: document.title })),
        onError: (error) => toast.error(getErrorMessage(error)),
      },
    );
  }

  const chooseButton = (
    <Button
      variant="outline"
      size="sm"
      disabled={!documents.data}
      onClick={() => {
        setIsPickerOpen(true);
      }}
    >
      <ListChecks aria-hidden="true" />
      {t("products.documents.choose")}
    </Button>
  );

  let content;
  if (documents.isPending) {
    content = <Spinner />;
  } else if (documents.isError) {
    content = <LoadFailed title={t("products.documents.loadFailed")} onRetry={() => void documents.refetch()} />;
  } else if (documents.data.length === 0) {
    content = (
      <EmptyState
        icon={FileStack}
        title={t("products.documents.emptyTitle")}
        description={t("products.documents.emptyDescription")}
        action={chooseButton}
      />
    );
  } else {
    content = (
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("documents.table.title")}</TableHead>
              <TableHead>{t("documents.table.docType")}</TableHead>
              <TableHead>{t("documents.table.language")}</TableHead>
              <TableHead>{t("documents.table.folder")}</TableHead>
              <TableHead>{t("documents.table.status")}</TableHead>
              <TableHead>
                <span className="sr-only">{t("documents.table.actions")}</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {documents.data.map((document) => (
              <TableRow key={document.id}>
                <TableCell className="max-w-72 truncate font-medium">
                  <Link to={`/documents/${document.id}`} className="hover:underline">
                    {document.title}
                  </Link>
                </TableCell>
                <TableCell>{t(`common.docType.${document.doc_type}`)}</TableCell>
                <TableCell>{getLanguageLabel(document.language, t)}</TableCell>
                <TableCell className="text-muted-foreground max-w-64 truncate" title={document.folder_path}>
                  {document.folder_path}
                </TableCell>
                <TableCell>
                  {document.processing_status ? <StatusBadge status={document.processing_status} /> : "—"}
                </TableCell>
                <TableCell className="text-right">
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={setDocuments.isPending}
                    aria-label={t("products.documents.removeDocument", { title: document.title })}
                    onClick={() => {
                      handleRemove(document);
                    }}
                  >
                    <X aria-hidden="true" />
                    {t("products.documents.remove")}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    );
  }

  return (
    <section aria-labelledby="product-documents" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-col gap-1">
          <h2 id="product-documents" className="text-lg font-semibold">
            {t("products.documents.title")}
          </h2>
          <p className="text-muted-foreground text-sm">{t("products.documents.description")}</p>
        </div>
        {documents.data && documents.data.length > 0 && chooseButton}
      </div>
      {content}
      {documents.data && (
        <ProductDocumentsPicker
          tenantId={tenantId}
          product={product}
          current={documents.data}
          open={isPickerOpen}
          onClose={() => {
            setIsPickerOpen(false);
          }}
        />
      )}
    </section>
  );
}
