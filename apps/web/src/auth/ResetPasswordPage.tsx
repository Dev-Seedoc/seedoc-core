import { zodResolver } from "@hookform/resolvers/zod";
import type { TFunction } from "i18next";
import { CircleCheck, LinkIcon } from "lucide-react";
import { useMemo } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getErrorCode, getErrorMessage } from "@/lib/api/errors";
import { useConfirmPasswordReset } from "@/lib/api/hooks/auth";

import { newPasswordFields, passwordsMatch, passwordsMatchMessage } from "./newPasswordSchema";

function createResetPasswordSchema(t: TFunction) {
  return z.object(newPasswordFields(t)).refine(passwordsMatch, passwordsMatchMessage(t));
}

type ResetPasswordValues = z.infer<ReturnType<typeof createResetPasswordSchema>>;

export function ResetPasswordPage() {
  const { t } = useTranslation();
  const { token = "" } = useParams();
  const confirmReset = useConfirmPasswordReset();

  const schema = useMemo(() => createResetPasswordSchema(t), [t]);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ResetPasswordValues>({
    resolver: zodResolver(schema),
    defaultValues: { password: "", passwordRepeat: "" },
  });

  function handleResetPassword(values: ResetPasswordValues) {
    confirmReset.mutate({ token, password: values.password });
  }

  if (confirmReset.isSuccess) {
    return (
      <div className="flex flex-col items-center gap-4 text-center">
        <CircleCheck className="size-10 text-emerald-600" aria-hidden="true" />
        <h1 className="text-xl font-semibold">{t("auth.resetPassword.successTitle")}</h1>
        <p className="text-muted-foreground text-sm">{t("auth.resetPassword.successDescription")}</p>
        <Button asChild className="w-full">
          <Link to="/login">{t("auth.resetPassword.toLogin")}</Link>
        </Button>
      </div>
    );
  }

  // Expired, already used or unknown token: the only way forward is a new link.
  if (getErrorCode(confirmReset.error) === "invitation_invalid") {
    return (
      <div className="flex flex-col items-center gap-4 text-center">
        <LinkIcon className="text-muted-foreground size-10" aria-hidden="true" />
        <h1 className="text-xl font-semibold">{t("auth.resetPassword.invalidTitle")}</h1>
        <p className="text-muted-foreground text-sm">{t("auth.resetPassword.invalidDescription")}</p>
        <Button asChild className="w-full">
          <Link to="/forgot-password">{t("auth.resetPassword.requestNew")}</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1.5">
        <h1 className="text-xl font-semibold">{t("auth.resetPassword.title")}</h1>
        <p className="text-muted-foreground text-sm">{t("auth.resetPassword.description")}</p>
      </div>

      <form
        className="flex flex-col gap-4"
        noValidate
        onSubmit={(event) => void handleSubmit(handleResetPassword)(event)}
      >
        <div className="flex flex-col gap-2">
          <Label htmlFor="reset-password">{t("auth.newPassword.password")}</Label>
          <Input
            id="reset-password"
            type="password"
            autoComplete="new-password"
            aria-invalid={errors.password ? true : undefined}
            aria-describedby="reset-password-hint"
            {...register("password")}
          />
          <p
            id="reset-password-hint"
            className={errors.password ? "text-destructive text-sm" : "text-muted-foreground text-sm"}
          >
            {errors.password?.message ?? t("auth.newPassword.hint")}
          </p>
        </div>

        <div className="flex flex-col gap-2">
          <Label htmlFor="reset-password-repeat">{t("auth.newPassword.passwordRepeat")}</Label>
          <Input
            id="reset-password-repeat"
            type="password"
            autoComplete="new-password"
            aria-invalid={errors.passwordRepeat ? true : undefined}
            aria-describedby={errors.passwordRepeat ? "reset-password-repeat-error" : undefined}
            {...register("passwordRepeat")}
          />
          {errors.passwordRepeat && (
            <p id="reset-password-repeat-error" className="text-destructive text-sm">
              {errors.passwordRepeat.message}
            </p>
          )}
        </div>

        {confirmReset.isError && (
          <p
            role="alert"
            className="border-destructive/30 bg-destructive/10 text-destructive rounded-md border p-3 text-sm"
          >
            {getErrorMessage(confirmReset.error)}
          </p>
        )}

        <Button type="submit" disabled={confirmReset.isPending}>
          {t("auth.resetPassword.submit")}
        </Button>
      </form>
    </div>
  );
}
