import { zodResolver } from "@hookform/resolvers/zod";
import type { TFunction } from "i18next";
import { useMemo } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { z } from "zod";

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
import { getErrorMessage } from "@/lib/api/errors";
import { useCreateSpace, useUpdateSpace } from "@/lib/api/hooks/documents";
import type { SpaceRead } from "@/lib/api/types";

// Limit of `Name` in apps/api/seedoc/schemas/common.py.
const NAME_MAX_LENGTH = 200;

// A new space, or renaming `space`. Spaces are admin/owner only (BUSINESS_RULES §1); the caller shows the buttons.
export type SpaceDialogTarget = { kind: "create" } | { kind: "rename"; space: SpaceRead };

function createSpaceSchema(t: TFunction) {
  return z.object({
    name: z
      .string()
      .trim()
      .min(1, { error: t("documents.spaceDialog.nameRequired") })
      .max(NAME_MAX_LENGTH, { error: t("documents.spaceDialog.nameTooLong") }),
  });
}

type SpaceValues = z.infer<ReturnType<typeof createSpaceSchema>>;

interface SpaceDialogProps {
  tenantId: string;
  target: SpaceDialogTarget | null;
  onClose: () => void;
  onSaved: (space: SpaceRead) => void;
}

export function SpaceDialog({ tenantId, target, onClose, onSaved }: SpaceDialogProps) {
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
          <SpaceForm
            key={target.kind === "rename" ? target.space.id : "new"}
            tenantId={tenantId}
            target={target}
            onClose={onClose}
            onSaved={onSaved}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function SpaceForm({ tenantId, target, onClose, onSaved }: SpaceDialogProps & { target: SpaceDialogTarget }) {
  const { t } = useTranslation();
  const createSpace = useCreateSpace(tenantId);
  const updateSpace = useUpdateSpace(tenantId);
  const mutation = target.kind === "rename" ? updateSpace : createSpace;

  const schema = useMemo(() => createSpaceSchema(t), [t]);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<SpaceValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: target.kind === "rename" ? target.space.name : "" },
  });

  const callbacks = {
    onSuccess: (space: SpaceRead) => {
      toast.success(t(target.kind === "rename" ? "documents.spaceDialog.renamed" : "documents.spaceDialog.created"));
      onSaved(space);
      onClose();
    },
  };

  function handleSave({ name }: SpaceValues) {
    if (target.kind === "create") {
      createSpace.mutate({ name }, callbacks);
    } else if (name === target.space.name) {
      onClose();
    } else {
      updateSpace.mutate({ spaceId: target.space.id, body: { name } }, callbacks);
    }
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>
          {target.kind === "rename" ? t("documents.spaceDialog.renameTitle") : t("documents.spaceDialog.createTitle")}
        </DialogTitle>
        <DialogDescription>{t("documents.spaceDialog.description")}</DialogDescription>
      </DialogHeader>

      <form className="flex flex-col gap-4" noValidate onSubmit={(event) => void handleSubmit(handleSave)(event)}>
        <div className="flex flex-col gap-2">
          <Label htmlFor="space-name">{t("documents.spaceDialog.name")}</Label>
          <Input
            id="space-name"
            autoComplete="off"
            aria-invalid={errors.name ? true : undefined}
            aria-describedby={errors.name ? "space-name-error" : undefined}
            {...register("name")}
          />
          {errors.name && (
            <p id="space-name-error" className="text-destructive text-sm">
              {errors.name.message}
            </p>
          )}
        </div>

        {mutation.isError && (
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
            {target.kind === "rename" ? t("common.actions.save") : t("documents.spaceDialog.submitCreate")}
          </Button>
        </DialogFooter>
      </form>
    </>
  );
}
