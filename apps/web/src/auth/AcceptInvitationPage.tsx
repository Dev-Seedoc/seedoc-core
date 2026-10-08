import { zodResolver } from "@hookform/resolvers/zod";
import type { TFunction } from "i18next";
import { Loader2, MailX, UserRoundX } from "lucide-react";
import { useMemo } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getErrorCode, getErrorMessage } from "@/lib/api/errors";
import { useAcceptInvitation, useInvitation, useLogout, useMe } from "@/lib/api/hooks/auth";
import type { InvitationKind, InvitationPreview, MeRead } from "@/lib/api/types";

import { newPasswordFields, passwordsMatch, passwordsMatchMessage } from "./newPasswordSchema";

function createNewAccountSchema(t: TFunction) {
  return z
    .object({ fullName: z.string().trim(), ...newPasswordFields(t) })
    .refine(passwordsMatch, passwordsMatchMessage(t));
}

function createExistingAccountSchema(t: TFunction) {
  return z.object({ password: z.string().min(1, { error: t("auth.validation.passwordRequired") }) });
}

type NewAccountValues = z.infer<ReturnType<typeof createNewAccountSchema>>;
type ExistingAccountValues = z.infer<ReturnType<typeof createExistingAccountSchema>>;

// Team members land in the manufacturer app, operators in their own area.
function homePathFor(kind: InvitationKind): string {
  return kind === "operator" ? "/operator" : "/";
}

function useAcceptAndGoHome(token: string, kind: InvitationKind) {
  const navigate = useNavigate();
  const accept = useAcceptInvitation(token);
  return {
    accept,
    submit: (body: { password?: string; full_name?: string | null }) => {
      accept.mutate(body, { onSuccess: () => void navigate(homePathFor(kind), { replace: true }) });
    },
  };
}

function FormAlert({ error }: { error: unknown }) {
  return (
    <p role="alert" className="border-destructive/30 bg-destructive/10 text-destructive rounded-md border p-3 text-sm">
      {getErrorMessage(error)}
    </p>
  );
}

function NewAccountForm({ token, kind }: { token: string; kind: InvitationKind }) {
  const { t } = useTranslation();
  const { accept, submit } = useAcceptAndGoHome(token, kind);
  const schema = useMemo(() => createNewAccountSchema(t), [t]);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<NewAccountValues>({
    resolver: zodResolver(schema),
    defaultValues: { fullName: "", password: "", passwordRepeat: "" },
  });

  function handleCreateAccount(values: NewAccountValues) {
    submit({ password: values.password, full_name: values.fullName || null });
  }

  return (
    <form
      className="flex flex-col gap-4"
      noValidate
      onSubmit={(event) => void handleSubmit(handleCreateAccount)(event)}
    >
      <div className="flex flex-col gap-2">
        <Label htmlFor="invite-full-name">{t("auth.acceptInvitation.fullName")}</Label>
        <Input id="invite-full-name" autoComplete="name" {...register("fullName")} />
      </div>

      <div className="flex flex-col gap-2">
        <Label htmlFor="invite-password">{t("auth.newPassword.password")}</Label>
        <Input
          id="invite-password"
          type="password"
          autoComplete="new-password"
          aria-invalid={errors.password ? true : undefined}
          aria-describedby="invite-password-hint"
          {...register("password")}
        />
        <p
          id="invite-password-hint"
          className={errors.password ? "text-destructive text-sm" : "text-muted-foreground text-sm"}
        >
          {errors.password?.message ?? t("auth.newPassword.hint")}
        </p>
      </div>

      <div className="flex flex-col gap-2">
        <Label htmlFor="invite-password-repeat">{t("auth.newPassword.passwordRepeat")}</Label>
        <Input
          id="invite-password-repeat"
          type="password"
          autoComplete="new-password"
          aria-invalid={errors.passwordRepeat ? true : undefined}
          aria-describedby={errors.passwordRepeat ? "invite-password-repeat-error" : undefined}
          {...register("passwordRepeat")}
        />
        {errors.passwordRepeat && (
          <p id="invite-password-repeat-error" className="text-destructive text-sm">
            {errors.passwordRepeat.message}
          </p>
        )}
      </div>

      {accept.isError && <FormAlert error={accept.error} />}

      <Button type="submit" disabled={accept.isPending}>
        {t("auth.acceptInvitation.createSubmit")}
      </Button>
    </form>
  );
}

// The invitation link alone never logs anyone into an existing account (services/auth.py accept_invitation).
function ExistingAccountForm({ token, kind }: { token: string; kind: InvitationKind }) {
  const { t } = useTranslation();
  const { accept, submit } = useAcceptAndGoHome(token, kind);
  const schema = useMemo(() => createExistingAccountSchema(t), [t]);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ExistingAccountValues>({ resolver: zodResolver(schema), defaultValues: { password: "" } });

  function handleAccept(values: ExistingAccountValues) {
    submit({ password: values.password });
  }

  return (
    <form className="flex flex-col gap-4" noValidate onSubmit={(event) => void handleSubmit(handleAccept)(event)}>
      <p className="text-muted-foreground text-sm">{t("auth.acceptInvitation.existingAccount")}</p>
      <div className="flex flex-col gap-2">
        <Label htmlFor="invite-existing-password">{t("auth.acceptInvitation.password")}</Label>
        <Input
          id="invite-existing-password"
          type="password"
          autoComplete="current-password"
          aria-invalid={errors.password ? true : undefined}
          aria-describedby={errors.password ? "invite-existing-password-error" : undefined}
          {...register("password")}
        />
        {errors.password && (
          <p id="invite-existing-password-error" className="text-destructive text-sm">
            {errors.password.message}
          </p>
        )}
      </div>

      {accept.isError && <FormAlert error={accept.error} />}

      <Button type="submit" disabled={accept.isPending}>
        {t("auth.acceptInvitation.acceptSubmit")}
      </Button>
    </form>
  );
}

function AcceptAsCurrentUser({ token, kind }: { token: string; kind: InvitationKind }) {
  const { t } = useTranslation();
  const { accept, submit } = useAcceptAndGoHome(token, kind);

  return (
    <div className="flex flex-col gap-4">
      {accept.isError && <FormAlert error={accept.error} />}
      <Button
        disabled={accept.isPending}
        onClick={() => {
          submit({});
        }}
      >
        {t("auth.acceptInvitation.acceptSubmit")}
      </Button>
    </div>
  );
}

function WrongUser({ invitedEmail, currentEmail }: { invitedEmail: string; currentEmail: string }) {
  const { t } = useTranslation();
  const logout = useLogout();

  // After logout the cache is cleared, `useMe` answers "not logged in" and the page shows the right form.
  return (
    <div className="flex flex-col items-center gap-4 text-center">
      <UserRoundX className="text-muted-foreground size-10" aria-hidden="true" />
      <h2 className="text-base font-semibold">{t("auth.acceptInvitation.wrongUserTitle")}</h2>
      <p className="text-muted-foreground text-sm">
        {t("auth.acceptInvitation.wrongUserDescription", { invitedEmail, currentEmail })}
      </p>
      <Button
        className="w-full"
        variant="outline"
        disabled={logout.isPending}
        onClick={() => {
          logout.mutate();
        }}
      >
        {t("auth.acceptInvitation.logout")}
      </Button>
    </div>
  );
}

// `me` is passed in (not read with a second useMe) so this part never triggers its own /auth/me request.
function InvitationBody({
  token,
  invitation,
  me,
}: {
  token: string;
  invitation: InvitationPreview;
  me: MeRead | undefined;
}) {
  if (me) {
    const isInvitee = me.user.email.toLowerCase() === invitation.email.toLowerCase();
    return isInvitee ? (
      <AcceptAsCurrentUser token={token} kind={invitation.kind} />
    ) : (
      <WrongUser invitedEmail={invitation.email} currentEmail={me.user.email} />
    );
  }
  return invitation.has_account ? (
    <ExistingAccountForm token={token} kind={invitation.kind} />
  ) : (
    <NewAccountForm token={token} kind={invitation.kind} />
  );
}

export function AcceptInvitationPage() {
  const { t } = useTranslation();
  const { token = "" } = useParams();
  const invitation = useInvitation(token);
  const me = useMe();

  if (invitation.isPending || me.isPending) {
    return (
      <div className="flex justify-center py-8">
        <Loader2 className="text-muted-foreground size-6 animate-spin" aria-hidden="true" />
        <span className="sr-only">{t("shell.loading")}</span>
      </div>
    );
  }

  if (invitation.isError && getErrorCode(invitation.error) !== "invitation_invalid") {
    return (
      <div className="flex flex-col gap-4">
        <FormAlert error={invitation.error} />
        <Button variant="outline" onClick={() => void invitation.refetch()}>
          {t("common.actions.retry")}
        </Button>
      </div>
    );
  }

  if (invitation.isError) {
    return (
      <div className="flex flex-col items-center gap-4 text-center">
        <MailX className="text-muted-foreground size-10" aria-hidden="true" />
        <h1 className="text-xl font-semibold">{t("auth.acceptInvitation.invalidTitle")}</h1>
        <p className="text-muted-foreground text-sm">{t("auth.acceptInvitation.invalidDescription")}</p>
      </div>
    );
  }

  const preview = invitation.data;
  const name = (preview.kind === "operator" ? preview.operator_org_name : preview.tenant_name) ?? t("common.appName");

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1.5">
        <h1 className="text-xl font-semibold">{t("auth.acceptInvitation.title", { name })}</h1>
        <p className="text-muted-foreground text-sm">{t("auth.acceptInvitation.forEmail", { email: preview.email })}</p>
      </div>
      <InvitationBody token={token} invitation={preview} me={me.data} />
    </div>
  );
}
