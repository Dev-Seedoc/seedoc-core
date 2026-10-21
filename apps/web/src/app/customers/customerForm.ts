import type { TFunction } from "i18next";
import { z } from "zod";

import { ApiError } from "@/lib/api/errors";

// Limits of `Name` and `ContactEmail` in apps/api/seedoc/schemas (common.py, deliveries.py).
const NAME_MAX_LENGTH = 200;
const EMAIL_MAX_LENGTH = 320;
// The API's own check (deliveries.py `_EMAIL_PATTERN`): "must look like an address".
const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

// Contact fields are optional: "" in the form, `null` in the API (null clears them on update).
export function createCustomerSchema(t: TFunction) {
  return z.object({
    name: z
      .string()
      .trim()
      .min(1, { error: t("customers.form.nameRequired") })
      .max(NAME_MAX_LENGTH, { error: t("customers.form.nameTooLong") }),
    contactName: z
      .string()
      .trim()
      .max(NAME_MAX_LENGTH, { error: t("customers.form.nameTooLong") }),
    contactEmail: z
      .string()
      .trim()
      .max(EMAIL_MAX_LENGTH, { error: t("customers.form.emailInvalid") })
      .refine((value) => value === "" || EMAIL_PATTERN.test(value), { error: t("customers.form.emailInvalid") }),
  });
}

export type CustomerValues = z.infer<ReturnType<typeof createCustomerSchema>>;

export function emptyToNull(value: string): string | null {
  return value === "" ? null : value;
}

// A 422 whose details name this body field (`details.fields[].loc` = ["body", field]).
export function isFieldRejected(error: unknown, field: string): boolean {
  if (!(error instanceof ApiError) || error.code !== "validation_failed" || !Array.isArray(error.details.fields)) {
    return false;
  }
  return error.details.fields.some(
    (entry: unknown) =>
      typeof entry === "object" &&
      entry !== null &&
      "loc" in entry &&
      Array.isArray(entry.loc) &&
      entry.loc[0] === "body" &&
      entry.loc[1] === field,
  );
}
