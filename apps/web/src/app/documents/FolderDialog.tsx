import { zodResolver } from "@hookform/resolvers/zod";
import type { TFunction } from "i18next";
import { useMemo } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { z } from "zod";

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
import { ApiError, getErrorMessage } from "@/lib/api/errors";
import { useCreateFolder, useUpdateFolder } from "@/lib/api/hooks/documents";
import type { FolderRead, FolderUpdate } from "@/lib/api/types";
import { ACCESS_LEVELS, DOC_TYPES } from "@/lib/documentEnums";
import { SUPPORTED_LANGUAGES } from "@/lib/languages";

// Limit of `Name` in apps/api/seedoc/schemas/common.py.
const NAME_MAX_LENGTH = 200;

// What the dialog is open for: a new folder (at the root or below `parent`) or editing `folder`.
export type FolderDialogTarget = { kind: "create"; parent: FolderRead | null } | { kind: "edit"; folder: FolderRead };

function createFolderSchema(t: TFunction) {
  return z.object({
    name: z
      .string()
      .trim()
      .min(1, { error: t("documents.folderDialog.nameRequired") })
      .max(NAME_MAX_LENGTH, { error: t("documents.folderDialog.nameTooLong") }),
    accessLevel: z.enum(ACCESS_LEVELS),
    // "" = no default.
    docType: z.union([z.enum(DOC_TYPES), z.literal("")]),
    language: z.union([z.enum(SUPPORTED_LANGUAGES), z.literal("")]),
  });
}

type FolderValues = z.infer<ReturnType<typeof createFolderSchema>>;

// A new subfolder starts with its parent's defaults; a new top-level folder with "public" and no other default.
function initialValues(target: FolderDialogTarget): FolderValues {
  const source = target.kind === "edit" ? target.folder : target.parent;
  return {
    name: target.kind === "edit" ? target.folder.name : "",
    accessLevel: source?.default_access_level ?? "public",
    docType: source?.default_doc_type ?? "",
    language: (source?.default_language ?? "") as FolderValues["language"],
  };
}

// Only the changed fields (API.md §3.2: a field left out stays; null clears doc type / language).
function changedFields(folder: FolderRead, values: FolderValues): FolderUpdate {
  const body: FolderUpdate = {};
  if (values.name !== folder.name) {
    body.name = values.name;
  }
  if (values.accessLevel !== folder.default_access_level) {
    body.default_access_level = values.accessLevel;
  }
  if ((values.docType || null) !== folder.default_doc_type) {
    body.default_doc_type = values.docType || null;
  }
  if ((values.language || null) !== folder.default_language) {
    body.default_language = values.language || null;
  }
  return body;
}

function isNameTaken(error: unknown): boolean {
  return error instanceof ApiError && error.code === "conflict" && error.details.field === "name";
}

interface FolderDialogProps {
  tenantId: string;
  spaceId: string;
  target: FolderDialogTarget | null;
  onClose: () => void;
  onSaved: (folder: FolderRead) => void;
}

export function FolderDialog({ tenantId, spaceId, target, onClose, onSaved }: FolderDialogProps) {
  const { t } = useTranslation();
  return (
    <Dialog
      open={target !== null}
      onOpenChange={(open) => {
        if (!open) {
          onClose();
        }
      }}
    >
      <DialogContent closeLabel={t("common.actions.close")}>
        {target && (
          <FolderForm
            // A fresh form (values, errors, request state) every time the dialog opens for something else.
            key={target.kind === "edit" ? target.folder.id : `new-${target.parent?.id ?? "root"}`}
            tenantId={tenantId}
            spaceId={spaceId}
            target={target}
            onClose={onClose}
            onSaved={onSaved}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

interface FolderFormProps extends Omit<FolderDialogProps, "target"> {
  target: FolderDialogTarget;
}

function FolderForm({ tenantId, spaceId, target, onClose, onSaved }: FolderFormProps) {
  const { t } = useTranslation();
  const createFolder = useCreateFolder(tenantId);
  const updateFolder = useUpdateFolder(tenantId);
  const mutation = target.kind === "edit" ? updateFolder : createFolder;

  const schema = useMemo(() => createFolderSchema(t), [t]);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<FolderValues>({ resolver: zodResolver(schema), defaultValues: initialValues(target) });

  const callbacks = {
    onSuccess: (folder: FolderRead) => {
      toast.success(t(target.kind === "edit" ? "documents.folderDialog.saved" : "documents.folderDialog.created"));
      onSaved(folder);
      onClose();
    },
    onError: (error: unknown) => {
      if (isNameTaken(error)) {
        setError("name", { message: t("documents.folderDialog.nameTaken") }, { shouldFocus: true });
      }
    },
  };

  function handleSave(values: FolderValues) {
    if (target.kind === "create") {
      createFolder.mutate(
        {
          space_id: spaceId,
          parent_id: target.parent?.id ?? null,
          name: values.name,
          default_access_level: values.accessLevel,
          default_doc_type: values.docType || null,
          default_language: values.language || null,
        },
        callbacks,
      );
      return;
    }
    const body = changedFields(target.folder, values);
    if (Object.keys(body).length === 0) {
      onClose();
      return;
    }
    updateFolder.mutate({ folderId: target.folder.id, body }, callbacks);
  }

  let title: string;
  if (target.kind === "edit") {
    title = t("documents.folderDialog.editTitle");
  } else if (target.parent) {
    title = t("documents.folderDialog.createSubfolderTitle", { parent: target.parent.name });
  } else {
    title = t("documents.folderDialog.createTitle");
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>{t("documents.folderDialog.description")}</DialogDescription>
      </DialogHeader>

      <form className="flex flex-col gap-4" noValidate onSubmit={(event) => void handleSubmit(handleSave)(event)}>
        <div className="flex flex-col gap-2">
          <Label htmlFor="folder-name">{t("documents.folderDialog.name")}</Label>
          <Input
            id="folder-name"
            autoComplete="off"
            aria-invalid={errors.name ? true : undefined}
            aria-describedby={errors.name ? "folder-name-error" : undefined}
            {...register("name")}
          />
          {errors.name && (
            <p id="folder-name-error" className="text-destructive text-sm">
              {errors.name.message}
            </p>
          )}
        </div>

        <div className="flex flex-col gap-2">
          <Label htmlFor="folder-access-level">{t("documents.folderDialog.accessLevel")}</Label>
          <NativeSelect id="folder-access-level" {...register("accessLevel")}>
            {ACCESS_LEVELS.map((level) => (
              <option key={level} value={level}>
                {t(`common.accessLevel.${level}`)}
              </option>
            ))}
          </NativeSelect>
        </div>

        <div className="flex flex-col gap-2">
          <Label htmlFor="folder-doc-type">{t("documents.folderDialog.docType")}</Label>
          <NativeSelect id="folder-doc-type" {...register("docType")}>
            <option value="">{t("documents.folderDialog.noDefault")}</option>
            {DOC_TYPES.map((docType) => (
              <option key={docType} value={docType}>
                {t(`common.docType.${docType}`)}
              </option>
            ))}
          </NativeSelect>
        </div>

        <div className="flex flex-col gap-2">
          <Label htmlFor="folder-language">{t("documents.folderDialog.language")}</Label>
          <NativeSelect id="folder-language" {...register("language")}>
            <option value="">{t("documents.folderDialog.noDefault")}</option>
            {SUPPORTED_LANGUAGES.map((language) => (
              <option key={language} value={language}>
                {t(`common.language.${language}`)}
              </option>
            ))}
          </NativeSelect>
        </div>

        {mutation.isError && !isNameTaken(mutation.error) && (
          <p
            role="alert"
            className="border-destructive/30 bg-destructive/10 text-destructive rounded-md border p-3 text-sm"
          >
            {getErrorMessage(mutation.error)}
          </p>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" disabled={mutation.isPending} onClick={onClose}>
            {t("common.actions.cancel")}
          </Button>
          <Button type="submit" disabled={mutation.isPending}>
            {target.kind === "edit" ? t("common.actions.save") : t("documents.folderDialog.submitCreate")}
          </Button>
        </DialogFooter>
      </form>
    </>
  );
}
