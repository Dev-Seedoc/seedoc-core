import type { TFunction } from "i18next";
import { z } from "zod";

// Limit of `Name` in apps/api/seedoc/schemas/common.py.
export const PRODUCT_NAME_MAX_LENGTH = 200;
// API.md §3.4: a new product requires German unless other languages are chosen.
export const DEFAULT_LANGUAGES = ["de"];

export function createProductSchema(t: TFunction) {
  return z.object({
    name: z
      .string()
      .trim()
      .min(1, { error: t("products.form.nameRequired") })
      .max(PRODUCT_NAME_MAX_LENGTH, { error: t("products.form.nameTooLong") }),
    // "" = no space.
    spaceId: z.string(),
    languages: z.array(z.string()).min(1, { error: t("products.form.languagesRequired") }),
  });
}

export type ProductValues = z.infer<ReturnType<typeof createProductSchema>>;
