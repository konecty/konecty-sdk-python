"""Exceptions for the Konecty SDK."""


class KonectyError(Exception):
    """Base exception for Konecty errors."""

    pass


class KonectyAPIError(KonectyError):
    """Raised when the API returns success=false or a non-2xx status."""

    pass


class KonectyGoogleSessionError(KonectyAPIError):
    """
    Raised by exchange_google_code. Carries the machine-readable ``code`` from
    ``errors[0].code`` so callers can branch or translate without parsing the
    message; ``failed`` covers unreadable or unrecognised bodies.

    Subclasses KonectyAPIError so existing ``except KonectyAPIError`` keeps working.

    Mirrors KonectyGoogleSessionError in the TypeScript SDK — keep both in sync.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class KonectyValidationError(KonectyError):
    """Raised for validation errors."""

    pass


class KonectySerializationError(KonectyError):
    """Raised when a value is not serializable."""

    def __init__(self) -> None:
        super().__init__("Tipo não serializável")
