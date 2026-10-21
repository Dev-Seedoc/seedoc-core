import type { TFunction } from "i18next";
import { Search } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { NativeCheckbox } from "@/components/common/NativeCheckbox";
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
import { useDocuments } from "@/lib/api/hooks/documents";
import { useSetProductDocuments } from "@/lib/api/hooks/products";
import type { DocumentListItem, ProductRead } from "@/lib/api/types";
import { getLanguageLabel } from "@/lib/languages";

const SEARCH_DELAY_MS = 300;
const PAGE_SIZE = 50;
// API.md §3.4: `set_product_documents` takes at most 500 ids.
const MAX_DOCUMENTS = 500;

interface ProductDocumentsPickerProps {
  tenantId: string;
  product: ProductRead;
  current: DocumentListItem[];
  open: boolean;
  onClose: () => void;
}

export function ProductDocumentsPicker({ open, onClose, ...props }: ProductDocumentsPickerProps) {
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
      <DialogContent className="sm:max-w-2xl" closeLabel={t("common.actions.close")}>
        {/* A fresh selection (the current set) every time the dialog opens. */}
        {open && <PickerForm {...props} onClose={onClose} />}
      </DialogContent>
    </Dialog>
  );
}

// The API's reason for refusing a set, in the user's words (API.md §3.4): 409 = a chosen document was trashed in the
// meantime, 422 = it became machine-specific; anything else (e.g. 404, deleted) gets the general message.
function getSetErrorMessage(error: unknown, t: TFunction): string {
  const code = getErrorCode(error);
  if (code === "conflict") {
    return t("products.documents.error.trashed");
  }
  if (code === "validation_failed") {
    return t("products.documents.error.machineSpecific");
  }
  return getErrorMessage(error);
}

function PickerForm({ tenantId, product, current, onClose }: Omit<ProductDocumentsPickerProps, "open">) {
  const { t } = useTranslation();
  const setDocuments = useSetProductDocuments(tenantId, product.id);
  const [selected, setSelected] = useState(() => new Set(current.map((document) => document.id)));
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  // Starts in the product's own space, if it has one; the user can widen it to every space.
  const [onlyOwnSpace, setOnlyOwnSpace] = useState(product.space_id !== null);
  const documents = useDocuments(tenantId, {
    q: query || undefined,
    space_id: onlyOwnSpace ? (product.space_id ?? undefined) : undefined,
    limit: PAGE_SIZE,
  });

  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(search.trim());
    }, SEARCH_DELAY_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [search]);

  const items = documents.data?.pages.flatMap((page) => page.items) ?? [];
  const tooMany = selected.size > MAX_DOCUMENTS;

  function toggle(documentId: string, isChecked: boolean) {
    setSelected((previous) => {
      const next = new Set(previous);
      if (isChecked) {
        next.add(documentId);
      } else {
        next.delete(documentId);
      }
      return next;
    });
  }

  function handleSave() {
    setDocuments.mutate(
      { document_ids: [...selected] },
      {
        onSuccess: (page) => {
          toast.success(t("products.documents.saved", { count: page.items.length }));
          onClose();
        },
      },
    );
  }

  let results;
  if (documents.isPending) {
    results = <Spinner />;
  } else if (documents.isError) {
    results = <p className="text-destructive py-6 text-center text-sm">{getErrorMessage(documents.error)}</p>;
  } else if (items.length === 0) {
    results = <p className="text-muted-foreground py-6 text-center text-sm">{t("products.documents.noResults")}</p>;
  } else {
    results = (
      <ul
        className="flex max-h-80 flex-col divide-y overflow-y-auto rounded-md border"
        aria-label={t("products.documents.results")}
      >
        {items.map((item) => {
          // Machine-specific documents belong to one machine, never to a product (API answers 422).
          const isMachineSpecific = item.machine_id !== null;
          const checkboxId = `product-document-${item.id}`;
          return (
            <li key={item.id} className="flex items-center gap-3 px-3 py-2">
              <NativeCheckbox
                id={checkboxId}
                checked={selected.has(item.id)}
                disabled={isMachineSpecific && !selected.has(item.id)}
                onChange={(event) => {
                  toggle(item.id, event.target.checked);
                }}
              />
              <label htmlFor={checkboxId} className="flex min-w-0 flex-1 flex-col">
                <span className="truncate text-sm font-medium">{item.title}</span>
                <span className="text-muted-foreground truncate text-xs">
                  {getLanguageLabel(item.language, t)} · {item.folder_path}
                </span>
              </label>
              {isMachineSpecific && (
                <span className="text-muted-foreground shrink-0 text-xs">
                  {t("products.documents.machineSpecific")}
                </span>
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
        <DialogTitle>{t("products.documents.pickerTitle", { name: product.name })}</DialogTitle>
        <DialogDescription>{t("products.documents.pickerDescription")}</DialogDescription>
      </DialogHeader>

      <div className="flex flex-col gap-2">
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
        {product.space_id !== null && (
          <label className="flex items-center gap-2 text-sm">
            <NativeCheckbox
              checked={onlyOwnSpace}
              onChange={(event) => {
                setOnlyOwnSpace(event.target.checked);
              }}
            />
            {t("products.documents.onlyOwnSpace")}
          </label>
        )}
      </div>

      {results}
      {documents.hasNextPage && (
        <Button
          variant="ghost"
          size="sm"
          className="self-center"
          disabled={documents.isFetchingNextPage}
          onClick={() => void documents.fetchNextPage()}
        >
          {t("products.documents.loadMore")}
        </Button>
      )}

      {(setDocuments.isError || tooMany) && (
        <p
          role="alert"
          className="border-destructive/30 bg-destructive/10 text-destructive rounded-md border p-3 text-sm"
        >
          {tooMany
            ? t("products.documents.error.tooMany", { max: MAX_DOCUMENTS })
            : getSetErrorMessage(setDocuments.error, t)}
        </p>
      )}

      <DialogFooter className="items-center">
        <span className="text-muted-foreground mr-auto text-sm" aria-live="polite">
          {t("products.documents.selected", { count: selected.size })}
        </span>
        <Button type="button" variant="outline" disabled={setDocuments.isPending} onClick={onClose}>
          {t("common.actions.cancel")}
        </Button>
        <Button type="button" disabled={setDocuments.isPending || tooMany} onClick={handleSave}>
          {t("common.actions.save")}
        </Button>
      </DialogFooter>
    </>
  );
}
