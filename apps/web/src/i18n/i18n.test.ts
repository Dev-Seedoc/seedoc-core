import { describe, expect, it } from "vitest";

import de from "./de.json";
import en from "./en.json";
import i18n from "./index";

const EXPECTED_ERROR_CODES = [
  "unauthenticated",
  "mfa_required",
  "fresh_auth_required",
  "invalid_credentials",
  "forbidden",
  "csrf_failed",
  "not_found",
  "feature_disabled",
  "validation_failed",
  "conflict",
  "release_immutable",
  "publish_blocked",
  "draft_exists",
  "no_draft",
  "upload_incomplete",
  "document_in_release",
  "domain_not_ready",
  "invitation_invalid",
  "file_too_large",
  "unsupported_file_type",
  "pin_rejected",
  "pin_locked",
  "rate_limited",
  "ai_unavailable",
  "internal_error",
] as const;

const EXPECTED_STATUS_VALUES = [
  "draft",
  "pending",
  "processing",
  "ready",
  "published",
  "archived",
  "failed",
  "active",
  "disabled",
  "inactive",
  "locked",
  "running",
  "expired",
] as const;

const EXPECTED_ACCESS_LEVELS = ["public", "customer", "internal"] as const;

const EXPECTED_DOC_TYPES = [
  "operating_manual",
  "installation_manual",
  "maintenance_manual",
  "safety_instruction",
  "datasheet",
  "spare_parts_list",
  "wiring_diagram",
  "declaration_of_conformity",
  "certificate",
  "test_report",
  "training_material",
  "other",
] as const;

const EXPECTED_LANGUAGES = [
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

function getLeafKeys(obj: Record<string, unknown>, prefix = ""): string[] {
  const keys: string[] = [];
  for (const [key, value] of Object.entries(obj)) {
    const fullPath = prefix ? `${prefix}.${key}` : key;
    if (value !== null && typeof value === "object" && !Array.isArray(value)) {
      keys.push(...getLeafKeys(value as Record<string, unknown>, fullPath));
    } else {
      keys.push(fullPath);
    }
  }
  return keys.sort();
}

describe("i18n setup", () => {
  it("initializes with German as default language", () => {
    expect(i18n.language).toBe("de");
    expect(i18n.t("common.actions.save")).toBe("Speichern");
  });

  it("translates to English when language is changed", async () => {
    await i18n.changeLanguage("en");
    expect(i18n.t("common.actions.save")).toBe("Save");
    await i18n.changeLanguage("de");
  });

  it("has exact key parity between de.json and en.json", () => {
    const deKeys = getLeafKeys(de);
    const enKeys = getLeafKeys(en);
    expect(deKeys).toEqual(enKeys);
  });

  it("contains all 25 backend error codes in de.json and en.json", () => {
    for (const code of EXPECTED_ERROR_CODES) {
      expect(de.errors).toHaveProperty(code);
      expect(en.errors).toHaveProperty(code);
      expect(de.errors[code]).toBeTruthy();
      expect(en.errors[code]).toBeTruthy();
    }
  });

  it("contains all status values in common.status", () => {
    for (const status of EXPECTED_STATUS_VALUES) {
      expect(de.common.status).toHaveProperty(status);
      expect(en.common.status).toHaveProperty(status);
    }
  });

  it("contains all accessLevel values in common.accessLevel", () => {
    for (const level of EXPECTED_ACCESS_LEVELS) {
      expect(de.common.accessLevel).toHaveProperty(level);
      expect(en.common.accessLevel).toHaveProperty(level);
    }
  });

  it("contains all docType values in common.docType", () => {
    for (const type of EXPECTED_DOC_TYPES) {
      expect(de.common.docType).toHaveProperty(type);
      expect(en.common.docType).toHaveProperty(type);
    }
  });

  it("contains all 25 ISO languages in common.language", () => {
    for (const lang of EXPECTED_LANGUAGES) {
      expect(de.common.language).toHaveProperty(lang);
      expect(en.common.language).toHaveProperty(lang);
    }
  });
});
