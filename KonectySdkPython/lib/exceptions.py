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


#: Código devolvido pelo Konecty quando a requisição pede ordenação arbitrária
#: acima do teto de página. Espelha ``SORT_ABOVE_MAX_PAGE_SIZE`` no SDK
#: TypeScript — manter os dois em sincronia.
SORT_ABOVE_MAX_PAGE_SIZE = "SORT_ABOVE_MAX_PAGE_SIZE"

#: Teto do servidor. Informativo: quem decide é a API, este valor só evita adivinhação.
MAX_SORTED_PAGE_SIZE = 1000


class KonectySortLimitError(KonectyAPIError):
    """
    Raised when the request asks for arbitrary ordering above the page cap.

    Acima de ``MAX_SORTED_PAGE_SIZE`` registros — e no caso sem limite
    (``limit=-1``) — o ``$sort`` teria de terminar antes de o primeiro documento
    sair do cursor, então a API recusa com HTTP 400 em vez de trocar a ordenação
    em silêncio, como fazia antes.

    Carrega o ``code`` legível por máquina para o chamador ramificar sem
    inspecionar a mensagem, como ``KonectyGoogleSessionError``. Subclasse de
    ``KonectyAPIError``, então ``except KonectyAPIError`` existente continua
    pegando.

    A saída é ordenar por ``_id`` (ascendente ou descendente) e paginar por faixa
    de ``_id``, ou pedir no máximo ``MAX_SORTED_PAGE_SIZE`` registros.

    Espelha ``KonectySortLimitError`` no SDK TypeScript — manter os dois em sincronia.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = SORT_ABOVE_MAX_PAGE_SIZE


def raise_for_konecty_errors(errors: object) -> None:
    """
    Lança a exceção mais específica que a lista de ``errors`` da API permitir.

    Existe porque os caminhos de find liam o corpo só para logar e lançavam
    ``KonectyAPIError`` genérico — e, no caso de HTTP 400, o
    ``response.raise_for_status()`` disparava ANTES de o corpo ser lido, então
    nem a mensagem nem o código chegavam a quem chamou.
    """
    items = errors if isinstance(errors, list) else []
    for error in items:
        if isinstance(error, dict) and error.get("code") == SORT_ABOVE_MAX_PAGE_SIZE:
            raise KonectySortLimitError(str(error.get("message", SORT_ABOVE_MAX_PAGE_SIZE)))

    raise KonectyAPIError(errors)


class KonectyValidationError(KonectyError):
    """Raised for validation errors."""

    pass


class KonectySerializationError(KonectyError):
    """Raised when a value is not serializable."""

    def __init__(self) -> None:
        super().__init__("Tipo não serializável")
