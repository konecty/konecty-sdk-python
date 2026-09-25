"""Exceptions for the Konecty SDK."""

from typing import Optional


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


#: Códigos do operador de filtro ``within_radius``. Espelham as constantes de
#: mesmo nome no SDK TypeScript (``src/sdk/filters/withinRadius.ts``) e no
#: servidor (``src/imports/data/filters/withinRadius.ts`` no repo Konecty).
#:
#: Recusa de forma ou de faixa do valor: ``center`` ou ``radius`` ausente,
#: coordenada fora da faixa, string numérica no lugar de número, raio não
#: positivo ou acima do teto do servidor.
#: Nome do operador, usado nas mensagens default. Espelha `WITHIN_RADIUS` no SDK TS.
WITHIN_RADIUS_OPERATOR = "within_radius"

WITHIN_RADIUS_INVALID_VALUE = "WITHIN_RADIUS_INVALID_VALUE"

#: O centro por referência a registro não pôde ser resolvido. Um código só para
#: os três casos (registro inexistente, ilegível, ou sem geolocalização) é
#: decisão do servidor: distinguí-los na resposta transformaria o filtro num
#: oráculo de localização para quem não pode ler o registro.
WITHIN_RADIUS_CENTER_UNRESOLVED = "WITHIN_RADIUS_CENTER_UNRESOLVED"


class KonectyWithinRadiusValueError(KonectyAPIError):
    """
    Raised when the server refuses the shape or range of a ``within_radius`` value.

    Carrega o ``code`` legível por máquina e preserva a mensagem do servidor, que
    nomeia o termo e a chave exata que falhou. Subclasse de ``KonectyAPIError``,
    então ``except KonectyAPIError`` existente continua pegando.

    O SDK **não** duplica a validação de faixa nem o teto de raio: quem decide é
    o servidor, e um teto copiado no cliente passa a mentir assim que o backend
    muda. Mesma postura do ``SORT_ABOVE_MAX_PAGE_SIZE``.

    Espelha ``KonectyWithinRadiusValueError`` no SDK TypeScript — manter os dois
    em sincronia.
    """

    #: Default idêntico ao do SDK TS (`message ?? \`Invalid value for operator ${WITHIN_RADIUS}\``
    #: em `src/sdk/filters/withinRadius.ts`), para que um erro sem `message` produza a MESMA
    #: frase nos dois — antes o Python levantava com a string literal "None".
    def __init__(self, message: Optional[str] = None) -> None:
        super().__init__(
            message or f"Invalid value for operator {WITHIN_RADIUS_OPERATOR}"
        )
        self.code = WITHIN_RADIUS_INVALID_VALUE


class KonectyWithinRadiusCenterError(KonectyAPIError):
    """
    Raised when a ``within_radius`` center given as a record reference could not
    be resolved — the record does not exist, is not readable, or has no geolocation.

    Espelha ``KonectyWithinRadiusCenterError`` no SDK TypeScript — manter os dois
    em sincronia.
    """

    #: Mesmo default do SDK TS — ver `KonectyWithinRadiusValueError` acima.
    def __init__(self, message: Optional[str] = None) -> None:
        super().__init__(
            message
            or f"Could not resolve the center record for operator {WITHIN_RADIUS_OPERATOR}"
        )
        self.code = WITHIN_RADIUS_CENTER_UNRESOLVED


#: Códigos que o SDK promove a exceção própria. A tabela existe para que um
#: código novo seja UMA linha em vez de mais um ``if`` no meio do fluxo — e para
#: que a lista de códigos suportados seja legível de uma vez, ao lado da lista
#: equivalente no SDK TypeScript (``ERROR_BY_CODE`` em ``src/sdk/errors.ts``).
#:
#: Todo código ausente daqui continua virando ``KonectyAPIError`` genérico.
_ERROR_BY_CODE = {
    SORT_ABOVE_MAX_PAGE_SIZE: KonectySortLimitError,
    WITHIN_RADIUS_INVALID_VALUE: KonectyWithinRadiusValueError,
    WITHIN_RADIUS_CENTER_UNRESOLVED: KonectyWithinRadiusCenterError,
}


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
        if not isinstance(error, dict):
            continue
        exception_class = _ERROR_BY_CODE.get(error.get("code"))
        if exception_class is not None:
            # `message` ausente OU `None`: cai no default da própria exceção, como o SDK
            # TS faz (`new Klass(message ?? undefined)` usa o default do construtor).
            # `str(None)` produziria a string literal "None" na mensagem do chamador.
            message = error.get("message")
            raise exception_class(message) if message else exception_class()

    raise KonectyAPIError(errors)


class KonectyValidationError(KonectyError):
    """Raised for validation errors."""

    pass


class KonectySerializationError(KonectyError):
    """Raised when a value is not serializable."""

    def __init__(self) -> None:
        super().__init__("Tipo não serializável")
