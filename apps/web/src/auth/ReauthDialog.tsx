import { zodResolver } from "@hookform/resolvers/zod";
import type { TFunction } from "i18next";
import { useMemo } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { z } from "zod";

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getErrorMessage } from "@/lib/api/errors";
import { useReauthenticate } from "@/lib/api/hooks/auth";

function createReauthSchema(t: TFunction) {
  return z.object({ password: z.string().min(1, { error: t("auth.validation.passwordRequired") }) });
}

type ReauthValues = z.infer<ReturnType<typeof createReauthSchema>>;

// Asks for the password again before a sensitive action (BUSINESS_RULES §1: fresh auth, valid 30 min).
// A screen opens it when the API answers `fresh_auth_required`, then retries its action in `onSuccess`.
interface ReauthDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess: () => void;
}

export function ReauthDialog({ open, onOpenChange, onSuccess }: ReauthDialogProps) {
  const { t } = useTranslation();
  const reauthenticate = useReauthenticate();

  const schema = useMemo(() => createReauthSchema(t), [t]);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ReauthValues>({ resolver: zodResolver(schema), defaultValues: { password: "" } });

  // Every opening starts clean: no old password, no old error.
  function handleOpenChange(nextOpen: boolean) {
    if (!nextOpen) {
      reset();
      reauthenticate.reset();
    }
    onOpenChange(nextOpen);
  }

  function handleReauthenticate(values: ReauthValues) {
    reauthenticate.mutate(values, {
      onSuccess: () => {
        handleOpenChange(false);
        onSuccess();
      },
    });
  }

  return (
    <AlertDialog open={open} onOpenChange={handleOpenChange}>
      <AlertDialogContent>
        <form
          className="flex flex-col gap-4"
          noValidate
          onSubmit={(event) => void handleSubmit(handleReauthenticate)(event)}
        >
          <AlertDialogHeader>
            <AlertDialogTitle>{t("auth.reauth.title")}</AlertDialogTitle>
            <AlertDialogDescription>{t("auth.reauth.description")}</AlertDialogDescription>
          </AlertDialogHeader>

          <div className="flex flex-col gap-2">
            <Label htmlFor="reauth-password">{t("auth.reauth.password")}</Label>
            <Input
              id="reauth-password"
              type="password"
              autoComplete="current-password"
              aria-invalid={errors.password ? true : undefined}
              aria-describedby={errors.password ? "reauth-password-error" : undefined}
              {...register("password")}
            />
            {errors.password && (
              <p id="reauth-password-error" className="text-destructive text-sm">
                {errors.password.message}
              </p>
            )}
          </div>

          {reauthenticate.isError && (
            <p
              role="alert"
              className="border-destructive/30 bg-destructive/10 text-destructive rounded-md border p-3 text-sm"
            >
              {getErrorMessage(reauthenticate.error)}
            </p>
          )}

          <AlertDialogFooter>
            <AlertDialogCancel type="button" disabled={reauthenticate.isPending}>
              {t("common.actions.cancel")}
            </AlertDialogCancel>
            <Button type="submit" disabled={reauthenticate.isPending}>
              {t("auth.reauth.submit")}
            </Button>
          </AlertDialogFooter>
        </form>
      </AlertDialogContent>
    </AlertDialog>
  );
}
