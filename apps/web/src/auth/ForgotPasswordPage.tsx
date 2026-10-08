import { zodResolver } from "@hookform/resolvers/zod";
import type { TFunction } from "i18next";
import { MailCheck } from "lucide-react";
import { useMemo } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getErrorMessage } from "@/lib/api/errors";
import { useRequestPasswordReset } from "@/lib/api/hooks/auth";

function createForgotPasswordSchema(t: TFunction) {
  return z.object({
    email: z.email({ error: t("auth.validation.emailInvalid") }),
  });
}

type ForgotPasswordValues = z.infer<ReturnType<typeof createForgotPasswordSchema>>;

function BackToLogin() {
  const { t } = useTranslation();

  return (
    <Link
      to="/login"
      className="text-muted-foreground hover:text-foreground text-sm underline-offset-4 hover:underline"
    >
      {t("auth.forgotPassword.backToLogin")}
    </Link>
  );
}

export function ForgotPasswordPage() {
  const { t } = useTranslation();
  const requestReset = useRequestPasswordReset();

  const schema = useMemo(() => createForgotPasswordSchema(t), [t]);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ForgotPasswordValues>({ resolver: zodResolver(schema), defaultValues: { email: "" } });

  function handleRequestReset(values: ForgotPasswordValues) {
    requestReset.mutate(values);
  }

  // The API answers 202 for every address, so this text never reveals whether an account exists.
  if (requestReset.isSuccess) {
    return (
      <div className="flex flex-col items-center gap-4 text-center">
        <MailCheck className="text-muted-foreground size-10" aria-hidden="true" />
        <h1 className="text-xl font-semibold">{t("auth.forgotPassword.sentTitle")}</h1>
        <p className="text-muted-foreground text-sm">{t("auth.forgotPassword.sentDescription")}</p>
        <BackToLogin />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1.5">
        <h1 className="text-xl font-semibold">{t("auth.forgotPassword.title")}</h1>
        <p className="text-muted-foreground text-sm">{t("auth.forgotPassword.description")}</p>
      </div>

      <form
        className="flex flex-col gap-4"
        noValidate
        onSubmit={(event) => void handleSubmit(handleRequestReset)(event)}
      >
        <div className="flex flex-col gap-2">
          <Label htmlFor="forgot-password-email">{t("auth.login.email")}</Label>
          <Input
            id="forgot-password-email"
            type="email"
            autoComplete="email"
            aria-invalid={errors.email ? true : undefined}
            aria-describedby={errors.email ? "forgot-password-email-error" : undefined}
            {...register("email")}
          />
          {errors.email && (
            <p id="forgot-password-email-error" className="text-destructive text-sm">
              {errors.email.message}
            </p>
          )}
        </div>

        {requestReset.isError && (
          <p
            role="alert"
            className="border-destructive/30 bg-destructive/10 text-destructive rounded-md border p-3 text-sm"
          >
            {getErrorMessage(requestReset.error)}
          </p>
        )}

        <Button type="submit" disabled={requestReset.isPending}>
          {t("auth.forgotPassword.submit")}
        </Button>
      </form>

      <div className="text-center">
        <BackToLogin />
      </div>
    </div>
  );
}
