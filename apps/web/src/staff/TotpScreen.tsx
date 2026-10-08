import { zodResolver } from "@hookform/resolvers/zod";
import type { TFunction } from "i18next";
import { Copy, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getErrorCode, getErrorMessage } from "@/lib/api/errors";
import { useSetupTotp, useVerifyTotp } from "@/lib/api/hooks/auth";
import type { MeRead } from "@/lib/api/types";

type TotpMode = "verify" | "setup";

// Staff who finished TOTP setup enter a code; everyone else sets it up first (MeRead.has_totp).
function getInitialTotpMode(me: MeRead): TotpMode {
  return me.has_totp ? "verify" : "setup";
}

function removeSpaces(value: string): string {
  return value.replace(/\s/g, "");
}

function createCodeSchema(t: TFunction) {
  return z.object({
    code: z.string().refine((value) => /^\d{6}$/.test(removeSpaces(value)), { error: t("staff.totp.codeInvalid") }),
  });
}

type CodeValues = z.infer<ReturnType<typeof createCodeSchema>>;

// The secret of `otpauth://totp/SeeDoc:name?secret=ABCD...&issuer=SeeDoc`, grouped in blocks of 4 for typing.
function readSecret(otpauthUri: string): string {
  const secret = new URL(otpauthUri).searchParams.get("secret") ?? "";
  return secret.match(/.{1,4}/g)?.join(" ") ?? secret;
}

// The API answers a wrong code with `invalid_credentials`, whose general text is about e-mail and password.
function getVerifyErrorMessage(error: unknown, t: TFunction): string {
  return getErrorCode(error) === "invalid_credentials" ? t("staff.totp.codeWrong") : getErrorMessage(error);
}

function FormAlert({ children }: { children: string }) {
  return (
    <p role="alert" className="border-destructive/30 bg-destructive/10 text-destructive rounded-md border p-3 text-sm">
      {children}
    </p>
  );
}

function CodeForm({ onNotSetUp }: { onNotSetUp: () => void }) {
  const { t } = useTranslation();
  const verify = useVerifyTotp();
  const schema = useMemo(() => createCodeSchema(t), [t]);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<CodeValues>({ resolver: zodResolver(schema), defaultValues: { code: "" } });

  function handleVerify(values: CodeValues) {
    verify.mutate(
      { code: removeSpaces(values.code) },
      {
        onError: (error) => {
          // The API answers `conflict` when this account has no TOTP yet.
          if (getErrorCode(error) === "conflict") {
            onNotSetUp();
          }
        },
      },
    );
  }

  return (
    <form className="flex flex-col gap-4" noValidate onSubmit={(event) => void handleSubmit(handleVerify)(event)}>
      <div className="flex flex-col gap-2">
        <Label htmlFor="totp-code">{t("staff.totp.code")}</Label>
        <Input
          id="totp-code"
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={7}
          aria-invalid={errors.code ? true : undefined}
          aria-describedby={errors.code ? "totp-code-error" : undefined}
          {...register("code")}
        />
        {errors.code && (
          <p id="totp-code-error" className="text-destructive text-sm">
            {errors.code.message}
          </p>
        )}
      </div>

      {verify.isError && getErrorCode(verify.error) !== "conflict" && (
        <FormAlert>{getVerifyErrorMessage(verify.error, t)}</FormAlert>
      )}

      <Button type="submit" disabled={verify.isPending}>
        {t("staff.totp.submit")}
      </Button>
    </form>
  );
}

function SetupSteps({ onAlreadySetUp }: { onAlreadySetUp: () => void }) {
  const { t } = useTranslation();
  const setup = useSetupTotp();

  function handleStartSetup() {
    setup.mutate(undefined, {
      onError: (error) => {
        if (getErrorCode(error) === "conflict") {
          onAlreadySetUp();
        }
      },
    });
  }

  if (!setup.data) {
    return (
      <div className="flex flex-col gap-4">
        {setup.isError && getErrorCode(setup.error) !== "conflict" && (
          <FormAlert>{getErrorMessage(setup.error)}</FormAlert>
        )}
        <Button disabled={setup.isPending} onClick={handleStartSetup}>
          {t("staff.totp.setupStart")}
        </Button>
      </div>
    );
  }

  const otpauthUri = setup.data.otpauth_uri;
  const secret = readSecret(otpauthUri);

  function handleCopy() {
    void navigator.clipboard.writeText(removeSpaces(secret)).then(() => toast.success(t("staff.totp.copied")));
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <span className="text-sm font-medium">{t("staff.totp.secretLabel")}</span>
        <div className="bg-muted flex items-center justify-between gap-2 rounded-md px-3 py-2">
          <code className="font-mono text-sm tracking-wider break-all">{secret}</code>
          <Button variant="ghost" size="icon" aria-label={t("common.actions.copy")} onClick={handleCopy}>
            <Copy aria-hidden="true" />
          </Button>
        </div>
        <a href={otpauthUri} className="text-sm underline underline-offset-4">
          {t("staff.totp.openInApp")}
        </a>
      </div>
      <CodeForm onNotSetUp={() => undefined} />
    </div>
  );
}

// Shown instead of a staff page until this session is confirmed with a TOTP code (BUSINESS_RULES §2).
export function TotpScreen({ me }: { me: MeRead }) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<TotpMode>(() => getInitialTotpMode(me));
  const [isAlreadySetUp, setIsAlreadySetUp] = useState(false);

  function handleAlreadySetUp() {
    setIsAlreadySetUp(true);
    setMode("verify");
  }

  return (
    <div className="flex min-h-svh items-center justify-center p-6">
      <main className="bg-background flex w-full max-w-sm flex-col gap-6 rounded-lg border p-6 shadow-sm">
        <div className="flex flex-col gap-1.5">
          <ShieldCheck className="text-muted-foreground mb-2 size-8" aria-hidden="true" />
          <h1 className="text-xl font-semibold">
            {mode === "setup" ? t("staff.totp.setupTitle") : t("staff.totp.verifyTitle")}
          </h1>
          <p className="text-muted-foreground text-sm">
            {mode === "setup" ? t("staff.totp.setupDescription") : t("staff.totp.verifyDescription")}
          </p>
          {isAlreadySetUp && <p className="text-sm">{t("staff.totp.alreadySetUp")}</p>}
        </div>

        {mode === "setup" ? (
          <SetupSteps onAlreadySetUp={handleAlreadySetUp} />
        ) : (
          <CodeForm
            onNotSetUp={() => {
              setMode("setup");
            }}
          />
        )}
      </main>
    </div>
  );
}
