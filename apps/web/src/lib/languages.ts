import type { TFunction } from "i18next";

// Document languages, the same codes and order as apps/api/seedoc/languages.py (SUPPORTED_LANGUAGES). Labels come
// from `common.language.<code>`. The API rejects any other code with 422.
export const SUPPORTED_LANGUAGES = [
  "de",
  "en",
  "fr",
  "es",
  "it",
  "nl",
  "pl",
  "cs",
  "pt",
  "sv",
  "da",
  "fi",
  "nb",
  "hu",
  "ro",
  "sk",
  "sl",
  "hr",
  "tr",
  "ru",
  "uk",
  "el",
  "bg",
  "ja",
  "zh",
] as const;

// A language code from the API as its German name (`common.language.<code>`); an unknown code is shown as it is.
export function getLanguageLabel(code: string, t: TFunction): string {
  const known = SUPPORTED_LANGUAGES.find((language) => language === code);
  return known ? t(`common.language.${known}`) : code;
}
