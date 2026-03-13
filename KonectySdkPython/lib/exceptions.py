"""Exceptions for the Konecty SDK."""


class KonectyError(Exception):
    """Base exception for Konecty errors."""

    pass


class KonectyAPIError(KonectyError):
    """Raised when the API returns success=false or a non-2xx status."""

    pass


class KonectyValidationError(KonectyError):
    """Raised for validation errors."""

    pass


class KonectySerializationError(KonectyError):
    """Raised when a value is not serializable."""

    def __init__(self) -> None:
        super().__init__("Tipo não serializável")
