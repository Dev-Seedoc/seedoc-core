import { Link2, Search, Unlink } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { Spinner } from "@/components/common/Spinner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { getErrorCode, getErrorMessage } from "@/lib/api/errors";
import { useDocuments, useLinkLanguageVariant, useUnlinkLanguageVariant } from "@/lib/api/hooks/documents";
import type { DocumentListItem, DocumentRead, LanguageVariantRead } from "@/lib/api/types";
import { getLanguageLabel } from "@/lib/languages";

const SEARCH_DELAY_MS = 300;
const SEARCH_LIMIT = 20;

interface LanguageVariantsProps {
  tenantId: string;
  document: DocumentRead;
}

// Translations of this document: documents of the same language group, one per language (API.md §3.3,
// BUSINESS_RULES §3). Linking puts the other document's whole group into this one; unlinking takes one out.
export function LanguageVariants({ tenantId, document }: LanguageVariantsProps) {
  const { t } = useTranslation();
  const [isLinkOpen, setIsLinkOpen] = useState(false);
  const [toUnlink, setToUnlink] = useState<LanguageVariantRead | null>(null);
  const unlink = useUnlinkLanguageVariant(tenantId, document.id);
  // The API refuses both on a trashed document (409); a trashed variant can still be unlinked from here.
  const isTrashed = document.trashed_at !== null;

  function handleUnlink() {
    if (!toUnlink) {
      return;
    }
    unlink.mutate(toUnlink.document_id, {
      onSuccess: () => {
        toast.success(t("documents.variants.unlinked", { title: toUnlink.title }));
        setToUnlink(null);
      },
      onError: (error) => {
        toast.error(getErrorMessage(error));
        setToUnlink(null);
      },
    });
  }

  return (
    <section aria-labelledby="document-variants" className="flex flex-col gap-4 rounded-lg border p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-col gap-1">
          <h2 id="document-variants" className="text-lg font-semibold">
            {t("documents.variants.title")}
          </h2>
          <p className="text-muted-foreground text-sm">{t("documents.variants.description")}</p>
        </div>
        <Button
          variant="outline"
          size="sm"
          disabled={isTrashed}
          onClick={() => {
            setIsLinkOpen(true);
          }}
        >
          <Link2 aria-hidden="true" />
          {t("documents.variants.link")}
        </Button>
      </div>

      {document.language_variants.length === 0 ? (
        <p className="text-muted-foreground text-sm">{t("documents.variants.empty")}</p>
      ) : (
        <ul className="flex flex-col divide-y rounded-md border" aria-label={t("documents.variants.title")}>
          {document.language_variants.map((variant) => (
            <li key={variant.document_id} className="flex items-center gap-3 px-3 py-2">
              <span className="text-muted-foreground w-28 shrink-0 text-sm">
                {getLanguageLabel(variant.language, t)}
              </span>
              <Link
                to={`/documents/${variant.document_id}`}
                className="min-w-0 flex-1 truncate text-sm hover:underline"
              >
                {variant.title}
              </Link>
              <Button
                variant="ghost"
                size="sm"
                disabled={isTrashed}
                aria-label={t("documents.variants.unlinkVariant", { title: variant.title })}
                onClick={() => {
                  setToUnlink(variant);
                }}
              >
                <Unlink aria-hidden="true" />
                {t("documents.variants.unlink")}
              </Button>
            </li>
          ))}
        </ul>
      )}

      <LinkVariantDialog
        tenantId={tenantId}
        document={document}
        open={isLinkOpen}
        onClose={() => {
          setIsLinkOpen(false);
        }}
      />
      <ConfirmDialog
        open={toUnlink !== null}
        onOpenChange={(open) => {
          if (!open) {
            setToUnlink(null);
          }
        }}
        title={t("documents.variants.unlinkTitle", { title: toUnlink?.title ?? "" })}
        description={t("documents.variants.unlinkDescription")}
        confirmLabel={t("documents.variants.unlink")}
        isPending={unlink.isPending}
        onConfirm={handleUnlink}
      />
    </section>
  );
}

interface LinkVariantDialogProps {
  tenantId: string;
  document: DocumentRead;
  open: boolean;
  onClose: () => void;
}

function LinkVariantDialog({ tenantId, document, open, onClose }: LinkVariantDialogProps) {
  const { t } = useTranslation();
  return (
    <Dialog
      open={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) {
          onClose();
        }
      }}
    >
      <DialogContent className="sm:max-w-xl" closeLabel={t("common.actions.close")}>
        {/* A fresh search every time the dialog opens. */}
        {open && <LinkVariantSearch tenantId={tenantId} document={document} onClose={onClose} />}
      </DialogContent>
    </Dialog>
  );
}

function LinkVariantSearch({ tenantId, document, onClose }: Omit<LinkVariantDialogProps, "open">) {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const link = useLinkLanguageVariant(tenantId, document.id);
  // Only untrashed documents can be linked; list_documents leaves trashed ones out by default.
  const candidates = useDocuments(tenantId, { q: query || undefined, limit: SEARCH_LIMIT });

  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(search.trim());
    }, SEARCH_DELAY_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [search]);

  // Languages this group has already (the document and its variants; trashed members are not listed here, so the
  // API may still answer 409 for them).
  const takenLanguages = new Set([document.language, ...document.language_variants.map((variant) => variant.language)]);
  const items = (candidates.data?.pages.flatMap((page) => page.items) ?? []).filter(
    (item) => item.id !== document.id && item.group_id !== document.group_id,
  );

  function handleLink(candidate: DocumentListItem) {
    link.mutate(
      { document_id: candidate.id },
      {
        onSuccess: () => {
          toast.success(t("documents.variants.linked", { title: candidate.title }));
          onClose();
        },
      },
    );
  }

  let results;
  if (candidates.isPending) {
    results = <Spinner />;
  } else if (items.length === 0) {
    results = <p className="text-muted-foreground py-6 text-center text-sm">{t("documents.variants.noCandidates")}</p>;
  } else {
    results = (
      <ul
        className="flex max-h-72 flex-col divide-y overflow-y-auto rounded-md border"
        aria-label={t("documents.variants.candidates")}
      >
        {items.map((item) => {
          const isTaken = takenLanguages.has(item.language);
          return (
            <li key={item.id} className="flex items-center gap-3 px-3 py-2">
              <div className="flex min-w-0 flex-1 flex-col">
                <span className="truncate text-sm font-medium">{item.title}</span>
                <span className="text-muted-foreground truncate text-xs">
                  {getLanguageLabel(item.language, t)} · {item.folder_path}
                </span>
              </div>
              {isTaken ? (
                <span className="text-muted-foreground text-xs">{t("documents.variants.languageTaken")}</span>
              ) : (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={link.isPending}
                  aria-label={t("documents.variants.linkCandidate", { title: item.title })}
                  onClick={() => {
                    handleLink(item);
                  }}
                >
                  {t("documents.variants.choose")}
                </Button>
              )}
            </li>
          );
        })}
      </ul>
    );
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>{t("documents.variants.linkTitle", { title: document.title })}</DialogTitle>
        <DialogDescription>{t("documents.variants.linkDescription")}</DialogDescription>
      </DialogHeader>
      <div className="relative">
        <Search
          className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2"
          aria-hidden="true"
        />
        <Input
          type="search"
          className="pl-8"
          placeholder={t("documents.filters.search")}
          aria-label={t("documents.filters.search")}
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
          }}
        />
      </div>
      {results}
      {link.isError && (
        <p
          role="alert"
          className="border-destructive/30 bg-destructive/10 text-destructive rounded-md border p-3 text-sm"
        >
          {getErrorCode(link.error) === "conflict" ? t("documents.variants.conflict") : getErrorMessage(link.error)}
        </p>
      )}
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose}>
          {t("common.actions.cancel")}
        </Button>
      </DialogFooter>
    </>
  );
}
