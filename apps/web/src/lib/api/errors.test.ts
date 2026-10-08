import { describe, expect, it } from "vitest";

import { ApiError, getErrorCode, getErrorMessage, toApiError } from "./errors";

describe("toApiError", () => {
  it("reads code and details from the API error body", () => {
    const error = toApiError(429, {
      error: { code: "rate_limited", message: "rate limited", details: { retry_after_seconds: 900 } },
    });

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(429);
    expect(error.code).toBe("rate_limited");
    expect(error.details).toEqual({ retry_after_seconds: 900 });
  });

  it("falls back to internal_error for an unknown code", () => {
    expect(toApiError(500, { error: { code: "something_new" } }).code).toBe("internal_error");
  });

  it("falls back to internal_error for a body without an error envelope", () => {
    expect(toApiError(502, "<html>Bad Gateway</html>").code).toBe("internal_error");
    expect(toApiError(500, undefined).details).toEqual({});
  });
});

describe("getErrorMessage", () => {
  it("shows the German i18n text, never the server message", () => {
    const error = toApiError(401, { error: { code: "invalid_credentials", message: "login failed", details: {} } });

    expect(getErrorMessage(error)).toBe("Ungültige E-Mail-Adresse oder falsches Passwort.");
  });

  it("treats a network failure as internal_error", () => {
    const networkError = new TypeError("Failed to fetch");

    expect(getErrorCode(networkError)).toBe("internal_error");
    expect(getErrorMessage(networkError)).toBe(
      "Ein unerwarteter Fehler ist aufgetreten. Bitte versuchen Sie es später erneut.",
    );
  });
});
