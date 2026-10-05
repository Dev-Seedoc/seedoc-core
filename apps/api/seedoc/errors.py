"""AppError and all error codes. Codes and HTTP status: docs/NAMING.md §11."""

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    UNAUTHENTICATED = "unauthenticated"
    MFA_REQUIRED = "mfa_required"
    FRESH_AUTH_REQUIRED = "fresh_auth_required"
    INVALID_CREDENTIALS = "invalid_credentials"
    FORBIDDEN = "forbidden"
    CSRF_FAILED = "csrf_failed"
    NOT_FOUND = "not_found"
    FEATURE_DISABLED = "feature_disabled"
    VALIDATION_FAILED = "validation_failed"
    CONFLICT = "conflict"
    RELEASE_IMMUTABLE = "release_immutable"
    PUBLISH_BLOCKED = "publish_blocked"
    DRAFT_EXISTS = "draft_exists"
    NO_DRAFT = "no_draft"
    UPLOAD_INCOMPLETE = "upload_incomplete"
    DOCUMENT_IN_RELEASE = "document_in_release"
    DOMAIN_NOT_READY = "domain_not_ready"
    INVITATION_INVALID = "invitation_invalid"
    FILE_TOO_LARGE = "file_too_large"
    UNSUPPORTED_FILE_TYPE = "unsupported_file_type"
    PIN_REJECTED = "pin_rejected"
    PIN_LOCKED = "pin_locked"
    RATE_LIMITED = "rate_limited"
    AI_UNAVAILABLE = "ai_unavailable"
    INTERNAL_ERROR = "internal_error"


ERROR_STATUS: dict[ErrorCode, int] = {
    ErrorCode.UNAUTHENTICATED: 401,
    ErrorCode.MFA_REQUIRED: 401,
    ErrorCode.FRESH_AUTH_REQUIRED: 401,
    ErrorCode.INVALID_CREDENTIALS: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.CSRF_FAILED: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.FEATURE_DISABLED: 404,
    ErrorCode.VALIDATION_FAILED: 422,
    ErrorCode.CONFLICT: 409,
    ErrorCode.RELEASE_IMMUTABLE: 409,
    ErrorCode.PUBLISH_BLOCKED: 409,
    ErrorCode.DRAFT_EXISTS: 409,
    ErrorCode.NO_DRAFT: 409,
    ErrorCode.UPLOAD_INCOMPLETE: 409,
    ErrorCode.DOCUMENT_IN_RELEASE: 409,
    ErrorCode.DOMAIN_NOT_READY: 409,
    ErrorCode.INVITATION_INVALID: 410,
    ErrorCode.FILE_TOO_LARGE: 413,
    ErrorCode.UNSUPPORTED_FILE_TYPE: 415,
    ErrorCode.PIN_REJECTED: 403,
    ErrorCode.PIN_LOCKED: 429,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.AI_UNAVAILABLE: 503,
    ErrorCode.INTERNAL_ERROR: 500,
}


class AppError(Exception):
    """Raised by services. Routers never raise HTTPException; the handler in main.py renders this."""

    def __init__(self, code: ErrorCode, message: str | None = None, details: dict[str, Any] | None = None) -> None:
        self.code = code
        self.message = message or code.value.replace("_", " ")
        self.details = details or {}
        super().__init__(self.message)

    @property
    def status_code(self) -> int:
        return ERROR_STATUS[self.code]

    def to_body(self) -> dict[str, Any]:
        return {"error": {"code": self.code.value, "message": self.message, "details": self.details}}
