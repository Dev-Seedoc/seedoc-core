import type { TFunction } from "i18next";
import { z } from "zod";

// Same limits as `NewPassword` in apps/api/seedoc/schemas/auth.py (BUSINESS_RULES §2: 12–128 characters).
export const NEW_PASSWORD_MIN_LENGTH = 12;
export const NEW_PASSWORD_MAX_LENGTH = 128;

// Fields of every "choose a new password" form. Combine with `passwordsMatch` via `.refine(...)`.
export function newPasswordFields(t: TFunction) {
  const lengthError = { error: t("auth.validation.passwordLength") };
  return {
    password: z.string().min(NEW_PASSWORD_MIN_LENGTH, lengthError).max(NEW_PASSWORD_MAX_LENGTH, lengthError),
    passwordRepeat: z.string(),
  };
}

export function passwordsMatch(values: { password: string; passwordRepeat: string }): boolean {
  return values.password === values.passwordRepeat;
}

export function passwordsMatchMessage(t: TFunction) {
  return { error: t("auth.validation.passwordMismatch"), path: ["passwordRepeat"] };
}
