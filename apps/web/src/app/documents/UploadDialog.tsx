import { CircleAlert, CircleCheck, FileUp, Loader2, X } from "lucide-react";
import { type DragEvent, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { toast } from "sonner";

import { NativeSelect } from "@/components/common/NativeSelect";
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
import { Label } from "@/components/ui/label";
import type { AccessLevel, DocType, FolderRead } from "@/lib/api/types";
import { ACCESS_LEVELS, DOC_TYPES } from "@/lib/documentEnums";
import { formatBytes } from "@/lib/formatNumber";
import { SUPPORTED_LANGUAGES } from "@/lib/languages";
import { checkPdf, type PdfProblem } from "@/lib/pdfCheck";

import { TITLE_MAX_LENGTH, titleFromFileName } from "./titleFromFileName";
import { type UploadJob, type UploadPhase, useUploadQueue } from "./useUploadQueue";

type Language = (typeof SUPPORTED_LANGUAGES)[number];

// One chosen file. `problem` = rejected before upload (shown, never sent).
interface UploadItem {
  key: string;
  file: File;
  title: string;
  problem: PdfProblem | null;
}

// Values for every file of this upload; "" = not chosen yet (only possible without a folder default).
interface SharedValues {
  docType: DocType | "";
  language: Language | "";
  accessLevel: AccessLevel;
}

function folderLanguage(folder: FolderRead): Language | "" {
  return SUPPORTED_LANGUAGES.find((language) => language === folder.default_language) ?? "";
}

interface UploadDialogProps {
  tenantId: string;
  folder: FolderRead;
  open: boolean;
  onClose: () => void;
}

export function UploadDialog({ tenantId, folder, open, onClose }: UploadDialogProps) {
  const { t } = useTranslation();
  // While files are on their way the dialog stays open: closing would hide their progress and errors.
  const [isBusy, setIsBusy] = useState(false);
  return (
    <Dialog
      open={open}
      onOpenChange={(isOpen) => {
        if (!isOpen && !isBusy) {
          onClose();
        }
      }}
    >
      <DialogContent className="sm:max-w-2xl" closeLabel={t("common.actions.close")}>
        {/* Fresh files and values every time the dialog opens (or opens for another folder). */}
        {open && (
          <UploadForm key={folder.id} tenantId={tenantId} folder={folder} onClose={onClose} onBusyChange={setIsBusy} />
        )}
      </DialogContent>
    </Dialog>
  );
}

interface UploadFormProps extends Omit<UploadDialogProps, "open"> {
  onBusyChange: (isBusy: boolean) => void;
}

function UploadForm({ tenantId, folder, onClose, onBusyChange }: UploadFormProps) {
  const { t } = useTranslation();
  const queue = useUploadQueue(tenantId);
  const inputId = useId();
  const [items, setItems] = useState<UploadItem[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);
  // New documents get these; missing ones fall back to the folder's defaults in the API, so they start from there.
  const [shared, setShared] = useState<SharedValues>({
    docType: folder.default_doc_type ?? "",
    language: folderLanguage(folder),
    accessLevel: folder.default_access_level,
  });

  async function addFiles(files: Iterable<File>) {
    const added = await Promise.all(
      Array.from(files, async (file) => ({
        key: crypto.randomUUID(),
        file,
        title: titleFromFileName(file.name),
        problem: await checkPdf(file),
      })),
    );
    setItems((current) => [...current, ...added]);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
    void addFiles(event.dataTransfer.files);
  }

  function setTitle(key: string, title: string) {
    setItems((current) => current.map((item) => (item.key === key ? { ...item, title } : item)));
  }

  function remove(key: string) {
    setItems((current) => current.filter((item) => item.key !== key));
  }

  const uploadable = items.filter((item) => item.problem === null);
  const errors = {
    docType: shared.docType === "" ? t("documents.upload.docTypeRequired") : undefined,
    language: shared.language === "" ? t("documents.upload.languageRequired") : undefined,
  };
  const hasEmptyTitle = uploadable.some((item) => item.title.trim() === "");
  const isValid = uploadable.length > 0 && !errors.docType && !errors.language && !hasEmptyTitle;

  async function runUpload(run: () => Promise<UploadPhase[]>) {
    onBusyChange(true);
    const outcomes = await run();
    onBusyChange(false);
    const done = outcomes.filter((outcome) => outcome.name === "done");
    const failed = outcomes.length - done.length;
    const hasDuplicates = done.some((outcome) => outcome.document.duplicate_of_document_id !== null);
    if (failed > 0) {
      toast.error(t("documents.upload.partlyDone", { done: done.length, failed }));
    } else {
      toast.success(t("documents.upload.done", { count: done.length }));
    }
    // Everything fine: nothing left to read in the dialog. Failures and duplicates stay visible.
    if (failed === 0 && !hasDuplicates) {
      onClose();
    }
  }

  function handleSubmit() {
    setIsSubmitted(true);
    if (!isValid || shared.docType === "" || shared.language === "") {
      return;
    }
    const values = {
      folderId: folder.id,
      docType: shared.docType,
      language: shared.language,
      accessLevel: shared.accessLevel,
    };
    void runUpload(() =>
      queue.start(
        uploadable.map(({ key, file, title }) => ({ key, file, title })),
        values,
      ),
    );
  }

  if (queue.jobs.length > 0) {
    const failedCount = queue.jobs.filter((job) => job.phase.name === "failed").length;
    return (
      <>
        <DialogHeader>
          <DialogTitle>{t("documents.upload.title", { folder: folder.path })}</DialogTitle>
          <DialogDescription>
            {queue.isBusy ? t("documents.upload.busyHint") : t("documents.upload.finishedHint")}
          </DialogDescription>
        </DialogHeader>
        <ul className="flex max-h-80 flex-col gap-2 overflow-y-auto" aria-label={t("documents.upload.progressList")}>
          {queue.jobs.map((job) => (
            <UploadJobRow key={job.key} job={job} />
          ))}
        </ul>
        <DialogFooter>
          {failedCount > 0 && !queue.isBusy && (
            <Button variant="outline" onClick={() => void runUpload(queue.retryFailed)}>
              {t("documents.upload.retryFailed", { count: failedCount })}
            </Button>
          )}
          <Button disabled={queue.isBusy} onClick={onClose}>
            {t("common.actions.close")}
          </Button>
        </DialogFooter>
      </>
    );
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>{t("documents.upload.title", { folder: folder.path })}</DialogTitle>
        <DialogDescription>{t("documents.upload.description")}</DialogDescription>
      </DialogHeader>

      <div
        className={
          isDragging
            ? "border-primary bg-primary/5 flex flex-col items-center gap-2 rounded-lg border-2 border-dashed p-6 text-center"
            : "flex flex-col items-center gap-2 rounded-lg border-2 border-dashed p-6 text-center"
        }
        onDragOver={(event) => {
          event.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => {
          setIsDragging(false);
        }}
        onDrop={handleDrop}
      >
        <FileUp className="text-muted-foreground size-8" aria-hidden="true" />
        <p className="text-muted-foreground text-sm">{t("documents.upload.dropHint")}</p>
        <Button variant="outline" size="sm" asChild>
          <label htmlFor={inputId} className="cursor-pointer">
            {t("documents.upload.chooseFiles")}
          </label>
        </Button>
        <input
          id={inputId}
          type="file"
          accept="application/pdf,.pdf"
          multiple
          className="sr-only"
          onChange={(event) => {
            if (event.target.files) {
              void addFiles(event.target.files);
            }
            // The same file can be chosen again after removing it.
            event.target.value = "";
          }}
        />
      </div>

      {items.length > 0 && (
        <ul className="flex max-h-64 flex-col gap-2 overflow-y-auto" aria-label={t("documents.upload.fileList")}>
          {items.map((item) => (
            <li key={item.key} className="flex items-start gap-2 rounded-md border p-2">
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <span className="text-muted-foreground truncate text-xs">
                  {item.file.name} · {formatBytes(item.file.size)}
                </span>
                {item.problem ? (
                  <span className="text-destructive text-sm">{t(`documents.upload.problem.${item.problem}`)}</span>
                ) : (
                  <Input
                    aria-label={t("documents.upload.titleFor", { file: item.file.name })}
                    aria-invalid={isSubmitted && item.title.trim() === "" ? true : undefined}
                    maxLength={TITLE_MAX_LENGTH}
                    value={item.title}
                    onChange={(event) => {
                      setTitle(item.key, event.target.value);
                    }}
                  />
                )}
              </div>
              <Button
                variant="ghost"
                size="icon"
                aria-label={t("documents.upload.remove", { file: item.file.name })}
                onClick={() => {
                  remove(item.key);
                }}
              >
                <X aria-hidden="true" />
              </Button>
            </li>
          ))}
        </ul>
      )}

      <fieldset className="grid gap-4 sm:grid-cols-3">
        <legend className="mb-2 text-sm font-medium">{t("documents.upload.sharedValues")}</legend>
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${inputId}-doc-type`}>{t("documents.upload.docType")}</Label>
          <NativeSelect
            id={`${inputId}-doc-type`}
            value={shared.docType}
            aria-invalid={isSubmitted && errors.docType ? true : undefined}
            onChange={(event) => {
              setShared({ ...shared, docType: DOC_TYPES.find((v) => v === event.target.value) ?? "" });
            }}
          >
            <option value="">{t("documents.upload.choose")}</option>
            {DOC_TYPES.map((docType) => (
              <option key={docType} value={docType}>
                {t(`common.docType.${docType}`)}
              </option>
            ))}
          </NativeSelect>
          {isSubmitted && errors.docType && <p className="text-destructive text-sm">{errors.docType}</p>}
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${inputId}-language`}>{t("documents.upload.language")}</Label>
          <NativeSelect
            id={`${inputId}-language`}
            value={shared.language}
            aria-invalid={isSubmitted && errors.language ? true : undefined}
            onChange={(event) => {
              setShared({ ...shared, language: SUPPORTED_LANGUAGES.find((v) => v === event.target.value) ?? "" });
            }}
          >
            <option value="">{t("documents.upload.choose")}</option>
            {SUPPORTED_LANGUAGES.map((language) => (
              <option key={language} value={language}>
                {t(`common.language.${language}`)}
              </option>
            ))}
          </NativeSelect>
          {isSubmitted && errors.language && <p className="text-destructive text-sm">{errors.language}</p>}
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${inputId}-access-level`}>{t("documents.upload.accessLevel")}</Label>
          <NativeSelect
            id={`${inputId}-access-level`}
            value={shared.accessLevel}
            onChange={(event) => {
              setShared({
                ...shared,
                accessLevel: ACCESS_LEVELS.find((v) => v === event.target.value) ?? shared.accessLevel,
              });
            }}
          >
            {ACCESS_LEVELS.map((level) => (
              <option key={level} value={level}>
                {t(`common.accessLevel.${level}`)}
              </option>
            ))}
          </NativeSelect>
        </div>
      </fieldset>

      {isSubmitted && hasEmptyTitle && (
        <p role="alert" className="text-destructive text-sm">
          {t("documents.upload.titleRequired")}
        </p>
      )}

      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose}>
          {t("common.actions.cancel")}
        </Button>
        <Button type="button" disabled={uploadable.length === 0} onClick={handleSubmit}>
          {t("documents.upload.submit", { count: uploadable.length })}
        </Button>
      </DialogFooter>
    </>
  );
}

// One file of a running upload: its phase in words, a progress bar while uploading, the result at the end.
function UploadJobRow({ job }: { job: UploadJob }) {
  const { t } = useTranslation();
  const { phase } = job;
  let status;
  if (phase.name === "done") {
    const duplicateId = phase.document.duplicate_of_document_id;
    status = (
      <span className="flex flex-wrap items-center gap-x-2 text-sm">
        <CircleCheck className="size-4 text-emerald-600" aria-hidden="true" />
        {t("documents.upload.phase.done")}
        {duplicateId && (
          <span className="text-amber-700 dark:text-amber-400">
            {t("documents.upload.duplicateHint")}{" "}
            <Link to={`/documents/${duplicateId}`} className="underline underline-offset-4">
              {t("documents.upload.openDuplicate")}
            </Link>
          </span>
        )}
      </span>
    );
  } else if (phase.name === "failed") {
    status = (
      <span className="text-destructive flex items-center gap-2 text-sm">
        <CircleAlert className="size-4" aria-hidden="true" />
        {phase.message}
      </span>
    );
  } else {
    const percent = phase.name === "uploading" ? Math.round(phase.progress * 100) : null;
    status = (
      <span className="text-muted-foreground flex items-center gap-2 text-sm">
        <Loader2 className="size-4 animate-spin" aria-hidden="true" />
        {percent === null
          ? t(`documents.upload.phase.${phase.name}`)
          : t("documents.upload.phase.uploading", { percent })}
      </span>
    );
  }
  return (
    <li className="flex flex-col gap-1.5 rounded-md border p-2">
      <span className="truncate text-sm font-medium">{job.title}</span>
      {phase.name === "uploading" && (
        <progress
          className="accent-primary h-1.5 w-full"
          max={1}
          value={phase.progress}
          aria-label={t("documents.upload.progressFor", { title: job.title })}
        />
      )}
      {status}
    </li>
  );
}
