import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { toast } from "sonner";

import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { ApiError, getErrorMessage } from "@/lib/api/errors";
import { useCreateProductRelease, useProductDocuments } from "@/lib/api/hooks/products";
import type { DocumentListItem, ProductRead } from "@/lib/api/types";
import { cn } from "@/lib/utils";

// API.md §3.4 `ProductReleaseCreate.change_note`: at most 2,000 characters after trimming.
const CHANGE_NOTE_MAX_LENGTH = 2000;

interface Problem {
  code: string;
  document_id?: string;
}

// `details.problems` of a 409 publish_blocked (API.md §3.4), or null for any other error.
function getProblems(error: unknown): Problem[] | null {
  if (!(error instanceof ApiError) || error.code !== "publish_blocked" || !Array.isArray(error.details.problems)) {
    return null;
  }
  return error.details.problems.filter(
    (problem: unknown): problem is Problem =>
      typeof problem === "object" && problem !== null && "code" in problem && typeof problem.code === "string",
  );
}

interface CreateReleaseDialogProps {
  tenantId: string;
  product: ProductRead;
  open: boolean;
  onClose: () => void;
}

export function CreateReleaseDialog({ open, onClose, ...props }: CreateReleaseDialogProps) {
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
        {/* A fresh note every time the dialog opens. */}
        {open && <CreateReleaseForm {...props} onClose={onClose} />}
      </DialogContent>
    </Dialog>
  );
}

function CreateReleaseForm({ tenantId, product, onClose }: Omit<CreateReleaseDialogProps, "open">) {
  const { t } = useTranslation();
  const noteId = useId();
  const counterId = useId();
  const [note, setNote] = useState("");
  const createRelease = useCreateProductRelease(tenantId, product.id);
  // The set, for the titles and states of documents that block the release (usually already loaded by the tab).
  const documents = useProductDocuments(tenantId, product.id);
  const length = note.trim().length;
  const tooLong = length > CHANGE_NOTE_MAX_LENGTH;
  const problems = createRelease.isError ? getProblems(createRelease.error) : null;

  function handleRelease() {
    const changeNote = note.trim();
    createRelease.mutate(changeNote ? { change_note: changeNote } : {}, {
      onSuccess: (release) => {
        toast.success(t("products.releases.created", { no: release.release_no }));
        onClose();
      },
      // A blocked release usually means a version is still being processed: show its current state.
      onError: () => void documents.refetch(),
    });
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>{t("products.releases.createTitle", { name: product.name })}</DialogTitle>
        <DialogDescription>
          {t("products.releases.createDescription", { count: product.document_count })}
        </DialogDescription>
      </DialogHeader>

      <div className="flex flex-col gap-2">
        <Label htmlFor={noteId}>{t("products.releases.changeNoteLabel")}</Label>
        <textarea
          id={noteId}
          rows={4}
          value={note}
          aria-invalid={tooLong ? true : undefined}
          aria-describedby={counterId}
          className={cn(
            "border-input placeholder:text-muted-foreground min-h-20 w-full rounded-md border bg-transparent px-3 py-2 text-base shadow-xs outline-none md:text-sm",
            "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] dark:bg-input/30",
            "aria-invalid:border-destructive aria-invalid:ring-destructive/20",
          )}
          placeholder={t("products.releases.changeNotePlaceholder")}
          onChange={(event) => {
            setNote(event.target.value);
          }}
        />
        <p id={counterId} className={cn("self-end text-xs", tooLong ? "text-destructive" : "text-muted-foreground")}>
          {t("products.releases.changeNoteCount", { count: length, max: CHANGE_NOTE_MAX_LENGTH })}
        </p>
      </div>

      {createRelease.isError && (
        <div
          role="alert"
          className="border-destructive/30 bg-destructive/10 text-destructive flex flex-col gap-2 rounded-md border p-3 text-sm"
        >
          {problems ? (
            <BlockedReasons problems={problems} documents={documents.data ?? []} />
          ) : (
            getErrorMessage(createRelease.error)
          )}
        </div>
      )}

      <DialogFooter>
        <Button type="button" variant="outline" disabled={createRelease.isPending} onClick={onClose}>
          {t("common.actions.cancel")}
        </Button>
        <Button type="button" disabled={createRelease.isPending || tooLong} onClick={handleRelease}>
          {t("products.releases.submit")}
        </Button>
      </DialogFooter>
    </>
  );
}

// Why the API refused the release (409 publish_blocked): no documents, or documents whose current version is not
// ready yet (still processing, or failed) — listed by title with a link, so they can be fixed.
function BlockedReasons({ problems, documents }: { problems: Problem[]; documents: DocumentListItem[] }) {
  const { t } = useTranslation();
  const byId = new Map(documents.map((document) => [document.id, document]));
  const notReady = problems.filter((problem) => problem.code === "version_not_ready" && problem.document_id);
  const hasNoItems = problems.some((problem) => problem.code === "no_items");

  return (
    <>
      <p className="font-medium">{t("products.releases.blocked")}</p>
      {hasNoItems && <p>{t("products.releases.problem.noItems")}</p>}
      {notReady.length > 0 && (
        <>
          <p>{t("products.releases.problem.versionNotReady")}</p>
          <ul className="flex flex-col gap-1">
            {notReady.map(({ document_id: documentId = "" }) => {
              const document = byId.get(documentId);
              return (
                <li key={documentId} className="flex flex-wrap items-center gap-2">
                  <Link to={`/documents/${documentId}`} className="underline underline-offset-4">
                    {document?.title ?? t("products.releases.problem.unknownDocument")}
                  </Link>
                  {document?.processing_status && <StatusBadge status={document.processing_status} />}
                </li>
              );
            })}
          </ul>
        </>
      )}
    </>
  );
}
