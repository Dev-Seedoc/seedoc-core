import { zodResolver } from "@hookform/resolvers/zod";
import type { TFunction } from "i18next";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
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
import { ApiError, getErrorMessage } from "@/lib/api/errors";
import { useStaffCreateTenant } from "@/lib/api/hooks/staff";

import { SLUG_MAX_LENGTH, SLUG_MIN_LENGTH, SLUG_PATTERN, toSlug } from "./toSlug";

// Limits of StaffTenantCreate in apps/api/seedoc/schemas/staff.py.
const NAME_MAX_LENGTH = 200;

function createTenantSchema(t: TFunction) {
  const slugError = { error: t("staff.createTenant.slugInvalid") };
  return z.object({
    name: z
      .string()
      .trim()
      .min(1, { error: t("staff.createTenant.nameRequired") })
      .max(NAME_MAX_LENGTH, { error: t("staff.createTenant.nameTooLong") }),
    slug: z.string().min(SLUG_MIN_LENGTH, slugError).max(SLUG_MAX_LENGTH, slugError).regex(SLUG_PATTERN, slugError),
    ownerEmail: z.email({ error: t("auth.validation.emailInvalid") }),
  });
}

type CreateTenantValues = z.infer<ReturnType<typeof createTenantSchema>>;

function isSlugTaken(error: unknown): boolean {
  return error instanceof ApiError && error.code === "conflict" && error.details.field === "slug";
}

interface CreateTenantDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateTenantDialog({ open, onOpenChange }: CreateTenantDialogProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const createTenant = useStaffCreateTenant();
  // The slug follows the name until the user edits it.
  const [isSlugEdited, setIsSlugEdited] = useState(false);

  const schema = useMemo(() => createTenantSchema(t), [t]);
  const {
    register,
    handleSubmit,
    reset,
    setError,
    setValue,
    formState: { errors, isSubmitted },
  } = useForm<CreateTenantValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", slug: "", ownerEmail: "" },
  });

  function handleOpenChange(nextOpen: boolean) {
    if (!nextOpen) {
      reset();
      createTenant.reset();
      setIsSlugEdited(false);
    }
    onOpenChange(nextOpen);
  }

  function handleCreate(values: CreateTenantValues) {
    createTenant.mutate(
      { name: values.name, slug: values.slug, owner_email: values.ownerEmail },
      {
        onSuccess: (tenant) => {
          toast.success(t("staff.createTenant.created", { email: values.ownerEmail }));
          handleOpenChange(false);
          void navigate(`/staff/tenants/${tenant.id}`);
        },
        onError: (error) => {
          if (isSlugTaken(error)) {
            setError("slug", { message: t("staff.createTenant.slugTaken") }, { shouldFocus: true });
          }
        },
      },
    );
  }

  const nameField = register("name", {
    onChange: (event: { target: { value: string } }) => {
      if (!isSlugEdited) {
        setValue("slug", toSlug(event.target.value), { shouldValidate: isSubmitted });
      }
    },
  });
  const slugField = register("slug", {
    onChange: () => {
      setIsSlugEdited(true);
    },
  });

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent closeLabel={t("common.actions.close")}>
        <DialogHeader>
          <DialogTitle>{t("staff.createTenant.title")}</DialogTitle>
          <DialogDescription>{t("staff.createTenant.description")}</DialogDescription>
        </DialogHeader>

        <form className="flex flex-col gap-4" noValidate onSubmit={(event) => void handleSubmit(handleCreate)(event)}>
          <div className="flex flex-col gap-2">
            <Label htmlFor="tenant-name">{t("staff.createTenant.name")}</Label>
            <Input
              id="tenant-name"
              autoComplete="organization"
              aria-invalid={errors.name ? true : undefined}
              aria-describedby={errors.name ? "tenant-name-error" : undefined}
              {...nameField}
            />
            {errors.name && (
              <p id="tenant-name-error" className="text-destructive text-sm">
                {errors.name.message}
              </p>
            )}
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="tenant-slug">{t("staff.createTenant.slug")}</Label>
            <Input
              id="tenant-slug"
              autoComplete="off"
              spellCheck={false}
              aria-invalid={errors.slug ? true : undefined}
              aria-describedby="tenant-slug-hint"
              {...slugField}
            />
            <p
              id="tenant-slug-hint"
              className={errors.slug ? "text-destructive text-sm" : "text-muted-foreground text-sm"}
            >
              {errors.slug?.message ?? t("staff.createTenant.slugHint")}
            </p>
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="tenant-owner-email">{t("staff.createTenant.ownerEmail")}</Label>
            <Input
              id="tenant-owner-email"
              type="email"
              autoComplete="off"
              aria-invalid={errors.ownerEmail ? true : undefined}
              aria-describedby={errors.ownerEmail ? "tenant-owner-email-error" : undefined}
              {...register("ownerEmail")}
            />
            {errors.ownerEmail && (
              <p id="tenant-owner-email-error" className="text-destructive text-sm">
                {errors.ownerEmail.message}
              </p>
            )}
          </div>

          {createTenant.isError && !isSlugTaken(createTenant.error) && (
            <p
              role="alert"
              className="border-destructive/30 bg-destructive/10 text-destructive rounded-md border p-3 text-sm"
            >
              {getErrorMessage(createTenant.error)}
            </p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={createTenant.isPending}
              onClick={() => {
                handleOpenChange(false);
              }}
            >
              {t("common.actions.cancel")}
            </Button>
            <Button type="submit" disabled={createTenant.isPending}>
              {t("staff.createTenant.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
