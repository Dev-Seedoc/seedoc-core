import { zodResolver } from "@hookform/resolvers/zod";
import type { TFunction } from "i18next";
import { useMemo } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Link, Navigate, useLocation, useNavigate } from "react-router";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getErrorMessage } from "@/lib/api/errors";
import { useLogin, useMe } from "@/lib/api/hooks/auth";

function createLoginSchema(t: TFunction) {
  return z.object({
    email: z.email({ error: t("auth.validation.emailInvalid") }),
    password: z.string().min(1, { error: t("auth.validation.passwordRequired") }),
  });
}

type LoginValues = z.infer<ReturnType<typeof createLoginSchema>>;

function stringField(value: object, key: string): string {
  const field: unknown = key in value ? (value as Record<string, unknown>)[key] : undefined;
  return typeof field === "string" ? field : "";
}

// AppLayout sends logged-out users here with `state.from` = the page they wanted. Search and hash are kept, so
// e.g. `/products/42?tab=releases` comes back to the same tab. Only same-app paths are accepted ("/x", not "//x").
function getReturnPath(state: unknown): string {
  if (typeof state === "object" && state !== null && "from" in state) {
    const from = state.from;
    if (typeof from === "object" && from !== null) {
      const pathname = stringField(from, "pathname");
      if (pathname.startsWith("/") && !pathname.startsWith("//") && pathname !== "/login") {
        return pathname + stringField(from, "search") + stringField(from, "hash");
      }
    }
  }
  return "/";
}

export function LoginPage() {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const { data: me } = useMe();
  const login = useLogin();
  const returnPath = getReturnPath(location.state);

  const schema = useMemo(() => createLoginSchema(t), [t]);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginValues>({ resolver: zodResolver(schema), defaultValues: { email: "", password: "" } });

  if (me && !login.isPending) {
    return <Navigate to={returnPath} replace />;
  }

  function handleLogin(values: LoginValues) {
    login.mutate(values, { onSuccess: () => void navigate(returnPath, { replace: true }) });
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1.5">
        <h1 className="text-xl font-semibold">{t("auth.login.title")}</h1>
        <p className="text-muted-foreground text-sm">{t("auth.login.description")}</p>
      </div>

      <form className="flex flex-col gap-4" noValidate onSubmit={(event) => void handleSubmit(handleLogin)(event)}>
        <div className="flex flex-col gap-2">
          <Label htmlFor="login-email">{t("auth.login.email")}</Label>
          <Input
            id="login-email"
            type="email"
            autoComplete="email"
            aria-invalid={errors.email ? true : undefined}
            aria-describedby={errors.email ? "login-email-error" : undefined}
            {...register("email")}
          />
          {errors.email && (
            <p id="login-email-error" className="text-destructive text-sm">
              {errors.email.message}
            </p>
          )}
        </div>

        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <Label htmlFor="login-password">{t("auth.login.password")}</Label>
            <Link
              to="/forgot-password"
              className="text-muted-foreground hover:text-foreground text-sm underline-offset-4 hover:underline"
            >
              {t("auth.login.forgotPassword")}
            </Link>
          </div>
          <Input
            id="login-password"
            type="password"
            autoComplete="current-password"
            aria-invalid={errors.password ? true : undefined}
            aria-describedby={errors.password ? "login-password-error" : undefined}
            {...register("password")}
          />
          {errors.password && (
            <p id="login-password-error" className="text-destructive text-sm">
              {errors.password.message}
            </p>
          )}
        </div>

        {login.isError && (
          <p
            role="alert"
            className="border-destructive/30 bg-destructive/10 text-destructive rounded-md border p-3 text-sm"
          >
            {getErrorMessage(login.error)}
          </p>
        )}

        <Button type="submit" disabled={login.isPending}>
          {t("auth.login.submit")}
        </Button>
      </form>
    </div>
  );
}
