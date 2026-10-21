import { zodResolver } from "@hookform/resolvers/zod";
import type { TFunction } from "i18next";
import { useMemo } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { z } from "zod";

import { NativeSelect } from "@/components/common/NativeSelect";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, getErrorMessage } from "@/lib/api/errors";
import { useUpdateDocument } from "@/lib/api/hooks/documents";
import type { DocumentRead, DocumentUpdate } from "@/lib/api/types";
import { ACCESS_LEVELS, DOC_TYPES } from "@/lib/documentEnums";
import { SUPPORTED_LANGUAGES } from "@/lib/languages";

import { TITLE_MAX_LENGTH } from "./titleFromFileName";

function createMetadataSchema(t: TFunction) {
  return z.object({
    title: z
      .string()
      .trim()
      .min(1, { error: t("documents.metadata.titleRequired") })
      .max(TITLE_MAX_LENGTH, { error: t("documents.metadata.titleTooLong") }),
    docType: z.enum(DOC_TYPES),
    language: z.enum(SUPPORTED_LANGUAGES),
    accessLevel: z.enum(ACCESS_LEVELS),
  });
}

type MetadataValues = z.infer<ReturnType<typeof createMetadataSchema>>;

function toValues(document: DocumentRead): MetadataValues {
  return {
    title: document.title,
    docType: document.doc_type,
    // The API only stores supported codes (DocumentCreate/Update check them).
    language: document.language as MetadataValues["language"],
    accessLevel: document.access_level,
  };
}

// Only what really changed (API.md §3.3: a field left out stays as it is).
function changedFields(document: DocumentRead, values: MetadataValues): DocumentUpdate {
  const body: DocumentUpdate = {};
  if (values.title !== document.title) {
    body.title = values.title;
  }
  if (values.docType !== document.doc_type) {
    body.doc_type = values.docType;
  }
  if (values.language !== document.language) {
    body.language = values.language;
  }
  if (values.accessLevel !== document.access_level) {
    body.access_level = values.accessLevel;
  }
  return body;
}

// The API answers 409 with details.field "language" when another document of the language group has that language.
function isLanguageTaken(error: unknown): boolean {
  return error instanceof ApiError && error.code === "conflict" && error.details.field === "language";
}

interface DocumentMetadataFormProps {
  tenantId: string;
  document: DocumentRead;
}

// Title, type, language and visibility of a document. Locked while it is in the trash: the API refuses changes
// (409) until it is restored. Moving to another folder is not part of this form.
export function DocumentMetadataForm({ tenantId, document }: DocumentMetadataFormProps) {
  const { t } = useTranslation();
  const update = useUpdateDocument(tenantId, document.id);
  const isTrashed = document.trashed_at !== null;
  const schema = useMemo(() => createMetadataSchema(t), [t]);
  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isDirty },
  } = useForm<MetadataValues>({
    resolver: zodResolver(schema),
    // Follows the document when it is reloaded (polling, another tab), without overwriting what is being typed.
    values: toValues(document),
    resetOptions: { keepDirtyValues: true },
  });

  // react-hook-form applies `resetOptions` to every reset(); ours must drop what was typed, not keep it.
  function resetTo(values: MetadataValues) {
    reset(values, { keepDirtyValues: false });
  }

  function handleSave(values: MetadataValues) {
    const body = changedFields(document, values);
    if (Object.keys(body).length === 0) {
      resetTo(values);
      return;
    }
    update.mutate(body, {
      onSuccess: (saved) => {
        toast.success(t("documents.metadata.saved"));
        resetTo(toValues(saved));
      },
      onError: (error) => {
        if (isLanguageTaken(error)) {
          setError("language", { message: t("documents.metadata.languageTaken") }, { shouldFocus: true });
        }
      },
    });
  }

  return (
    <section aria-labelledby="document-metadata" className="flex flex-col gap-4 rounded-lg border p-4">
      <h2 id="document-metadata" className="text-lg font-semibold">
        {t("documents.metadata.title")}
      </h2>
      <form className="flex flex-col gap-4" noValidate onSubmit={(event) => void handleSubmit(handleSave)(event)}>
        {/* Locked only in the trash. Not while saving: a 409 must be able to move the focus to the language. */}
        <fieldset disabled={isTrashed} className="grid gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-2 sm:col-span-2">
            <Label htmlFor="document-title">{t("documents.metadata.titleLabel")}</Label>
            <Input
              id="document-title"
              aria-invalid={errors.title ? true : undefined}
              aria-describedby={errors.title ? "document-title-error" : undefined}
              {...register("title")}
            />
            {errors.title && (
              <p id="document-title-error" className="text-destructive text-sm">
                {errors.title.message}
              </p>
            )}
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="document-doc-type">{t("documents.table.docType")}</Label>
            <NativeSelect id="document-doc-type" {...register("docType")}>
              {DOC_TYPES.map((docType) => (
                <option key={docType} value={docType}>
                  {t(`common.docType.${docType}`)}
                </option>
              ))}
            </NativeSelect>
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="document-language">{t("documents.table.language")}</Label>
            <NativeSelect
              id="document-language"
              aria-invalid={errors.language ? true : undefined}
              aria-describedby={errors.language ? "document-language-error" : undefined}
              {...register("language")}
            >
              {SUPPORTED_LANGUAGES.map((language) => (
                <option key={language} value={language}>
                  {t(`common.language.${language}`)}
                </option>
              ))}
            </NativeSelect>
            {errors.language && (
              <p id="document-language-error" className="text-destructive text-sm">
                {errors.language.message}
              </p>
            )}
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="document-access-level">{t("documents.table.accessLevel")}</Label>
            <NativeSelect id="document-access-level" {...register("accessLevel")}>
              {ACCESS_LEVELS.map((level) => (
                <option key={level} value={level}>
                  {t(`common.accessLevel.${level}`)}
                </option>
              ))}
            </NativeSelect>
          </div>
        </fieldset>

        {update.isError && !isLanguageTaken(update.error) && (
          <p
            role="alert"
            className="border-destructive/30 bg-destructive/10 text-destructive rounded-md border p-3 text-sm"
          >
            {getErrorMessage(update.error)}
          </p>
        )}

        <div className="flex flex-wrap justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            disabled={!isDirty || update.isPending}
            onClick={() => {
              resetTo(toValues(document));
              update.reset();
            }}
          >
            {t("common.actions.discard")}
          </Button>
          <Button type="submit" disabled={isTrashed || !isDirty || update.isPending}>
            {t("common.actions.save")}
          </Button>
        </div>
      </form>
    </section>
  );
}
