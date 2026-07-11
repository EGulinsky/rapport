"""Stable error-key scheme for HTTP responses meant for direct human consumption
(e.g. auth errors shown in the UI). The frontend translates by `error_key`; the
`message` field carries a German fallback (for logs, and as a safety net if a
key is ever missing from the frontend catalog) — it must never be relied on
for display once a route's callers are updated to prefer `error_key`.

Flat enum (not per-router sub-enums) so ~40-50 entries stay grep-discoverable.
Only static, translatable error sites get a key — dynamic messages embedding a
third-party exception's own text (e.g. iCloud/Google sync failures) are out of
scope for now; see the i18n plan for the rationale.
"""
from __future__ import annotations

from enum import Enum

from fastapi import HTTPException


class ErrorKey(str, Enum):
    # auth
    AUTH_EMAIL_ALREADY_REGISTERED = "auth.email_already_registered"
    AUTH_CODE_INVALID = "auth.code_invalid"
    AUTH_CODE_EXPIRED = "auth.code_expired"
    AUTH_ACCOUNT_NOT_FOUND = "auth.account_not_found"
    AUTH_ALREADY_VERIFIED = "auth.already_verified"
    AUTH_LOGIN_FAILED = "auth.login_failed"
    AUTH_EMAIL_NOT_VERIFIED = "auth.email_not_verified"
    AUTH_CURRENT_PASSWORD_WRONG = "auth.current_password_wrong"
    AUTH_CV_TYPE_INVALID = "auth.cv_type_invalid"
    AUTH_CV_TOO_LARGE = "auth.cv_too_large"
    AUTH_NO_CV = "auth.no_cv"
    AUTH_CV_FILE_MISSING = "auth.cv_file_missing"
    AUTH_EMAIL_SEND_FAILED = "auth.email_send_failed"


def api_error(status_code: int, key: ErrorKey, message: str) -> HTTPException:
    return HTTPException(status_code, detail={"error_key": key.value, "message": message})
