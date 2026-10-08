import { toast } from "sonner";

import de from "@/i18n/de.json";
import i18n from "@/i18n";

// Error codes = keys of `errors.*` in de.json, which i18n.test.ts keeps equal to seedoc/errors.py (NAMING §11).
export type ErrorCode = keyof (typeof de)["errors"];

const ERROR_CODES = new Set<string>(Object.keys(de.errors));

function isErrorCode(value: unknown): value is ErrorCode {
  return typeof value === "string" && ERROR_CODES.has(value);
}

// Every API error body is {"error": {"code", "message", "details"}}. `message` is for developers only.
export class ApiError extends Error {
  readonly status: number;
  readonly code: ErrorCode;
  readonly details: Record<string, unknown>;

  constructor(status: number, code: ErrorCode, details: Record<string, unknown> = {}) {
    super(code);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function toApiError(status: number, body: unknown): ApiError {
  const error = isRecord(body) ? body.error : undefined;
  if (isRecord(error) && isErrorCode(error.code)) {
    const details = isRecord(error.details) ? error.details : {};
    return new ApiError(status, error.code, details);
  }
  return new ApiError(status, "internal_error");
}

export function getErrorCode(error: unknown): ErrorCode {
  return error instanceof ApiError ? error.code : "internal_error";
}

export function getErrorMessage(error: unknown): string {
  return i18n.t(`errors.${getErrorCode(error)}`);
}

export function showErrorToast(error: unknown): void {
  toast.error(getErrorMessage(error));
}
