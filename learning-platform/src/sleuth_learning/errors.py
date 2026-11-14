"""Typed errors with a stable {code, message} envelope, mirroring the API
error shape in proposals/learning-platform/data-contracts.md section 4 even
though this MVP has no HTTP layer -- callers (CLI, tests) can render the same
envelope consistently."""

from __future__ import annotations


class SleuthLearningError(Exception):
    code = "internal-error"

    def __init__(self, message: str, **details):
        super().__init__(message)
        self.message = message
        self.details = details

    def to_dict(self) -> dict:
        d = {"error": {"code": self.code, "message": self.message}}
        if self.details:
            d["error"]["details"] = self.details
        return d


class SchemaError(SleuthLearningError):
    code = "schema-error"


class IntegrityError(SleuthLearningError):
    code = "integrity-error"


class PathSafetyError(SleuthLearningError):
    code = "path-safety-error"


class SourceUnstableError(SleuthLearningError):
    code = "source-unstable"


class NotFoundError(SleuthLearningError):
    code = "not-found"


class DuplicateError(SleuthLearningError):
    """Not fatal by itself -- callers decide whether a duplicate is an error
    (e.g. a test asserting idempotency) or an informational short-circuit."""
    code = "duplicate"


class AuthorizationError(SleuthLearningError):
    code = "authorization-required"


class ValidationBlockedError(SleuthLearningError):
    """Raised when an action (e.g. publish) is attempted while blocking
    validation findings exist."""
    code = "validation-blocked"


class ModelUnavailableError(SleuthLearningError):
    code = "model-unavailable"
