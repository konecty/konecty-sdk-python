from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, TypedDict, Union

from pydantic import BaseModel, Field


class FilterMatch(str, Enum):
    """Tipo de correspondência do filtro."""

    AND = "and"
    OR = "or"


class FilterOperator(str, Enum):
    """Operadores disponíveis para filtros."""

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    STARTS_WITH = "starts_with"
    END_WITH = "end_with"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    LESS_THAN = "less_than"
    GREATER_THAN = "greater_than"
    LESS_OR_EQUALS = "less_or_equals"
    GREATER_OR_EQUALS = "greater_or_equals"
    BETWEEN = "between"
    IN = "in"
    NOT_IN = "not_in"
    EXISTS = "exists"
    #: Busca por raio geográfico em campo de tipo ``address``. Espelha
    #: ``WITHIN_RADIUS`` no SDK TypeScript — manter os dois em sincronia.
    WITHIN_RADIUS = "within_radius"


#: Referência ao registro de onde tirar o centro, em vez de um par literal:
#: "perto do empreendimento X". O servidor lê o registro sob controle de acesso
#: completo e substitui pelo par antes de compilar a query.
#:
#: ``field`` é obrigatório porque um documento pode ter mais de um campo
#: ``address`` e adivinhar seria escolher em silêncio.
WithinRadiusCenterRef = TypedDict(
    "WithinRadiusCenterRef",
    {"document": str, "_id": str, "field": str},
)

#: Par de coordenadas do centro, na ordem **``[longitude, latitude]``**.
#:
#: Longitude PRIMEIRO. É a ordem do par já gravado em ``address.geolocation`` e a
#: que o Mongo consome, e é o erro nº 1 que se comete aqui. Porto Alegre, por
#: exemplo, é ``(-51.2177, -30.0346)`` — longitude ~ -51, latitude ~ -30.
WithinRadiusCoordinatePair = Union[Tuple[float, float], Sequence[float]]

WithinRadiusCenter = Union[WithinRadiusCoordinatePair, WithinRadiusCenterRef]


def _normalize_within_radius_center(center: WithinRadiusCenter) -> Any:
    """
    Põe o centro na forma que vai para o JSON, sem validar faixa nem tipo.

    Uma referência a registro vira ``dict``; um par vira ``list`` — nesta ordem,
    ``[longitude, latitude]``. Nada é convertido para número: string numérica é
    recusada pelo SERVIDOR, de propósito, e coagir aqui esconderia o erro do
    chamador em vez de reportá-lo.
    """
    if isinstance(center, Mapping):
        return dict(center)
    return list(center)


def within_radius_condition(
    term: str,
    center: WithinRadiusCenter,
    radius: float,
) -> "FilterCondition":
    """
    Monta a condição de filtro do operador ``within_radius``.

    O ``term`` é o campo ``address`` puro: o sufixo ``.geolocation`` é
    acrescentado pelo SERVIDOR, não pelo cliente. O ``radius`` é em **metros**.

    Existe para que a ordem ``[longitude, latitude]`` e o raio em metros
    apareçam uma vez, tipados, em vez de serem redigitados como dicionário
    literal em cada chamada — que é onde a inversão das coordenadas entra.

    .. code-block:: python

        within_radius_condition("address", (-51.2177, -30.0346), 5000)
        # term="address", operator=within_radius,
        # value={"center": [-51.2177, -30.0346], "radius": 5000}

    O SDK **não** valida faixa nem teto de raio: quem decide é o servidor, e um
    teto copiado aqui passaria a mentir assim que o backend mudasse. Valor
    recusado volta como ``WITHIN_RADIUS_INVALID_VALUE``.

    Espelha ``withinRadiusCondition`` no SDK TypeScript — a mesma entrada produz
    a mesma saída (travado por teste: ``tests/test_within_radius.py`` e
    ``src/__test__/api/withinRadius.test.ts``).
    """
    return FilterCondition(
        term=term,
        operator=FilterOperator.WITHIN_RADIUS,
        value={"center": _normalize_within_radius_center(center), "radius": radius},
    )


class DateValue(BaseModel):
    """Valor de data para filtros."""

    date: datetime


class BetweenValue(BaseModel):
    """Valor para filtros do tipo between."""

    greater_or_equals: Union[int, float, DateValue, datetime, None]
    less_or_equals: Union[int, float, DateValue, datetime, None]


class FilterCondition(BaseModel):
    """Condição de filtro."""

    term: str = Field(..., description="Campo a ser filtrado")
    operator: FilterOperator = Field(..., description="Operador de comparação")
    value: Any = Field(..., description="Valor para comparação")
    disabled: bool = Field(False, description="Se a condição está desativada")


class KonectyFilter(BaseModel):
    """Filtro Konecty."""

    match: FilterMatch = Field(FilterMatch.AND, description="Tipo de correspondência")
    conditions: List[FilterCondition] = Field(default_factory=list, description="Lista de condições")
    filters: List["KonectyFilter"] = Field(default_factory=list, description="Lista de filtros aninhados")

    def to_json(self) -> Dict[str, Any]:
        """Converte o filtro para formato JSON."""
        return self.model_dump(mode="json")
    
    def is_empty(self) -> bool:
        """Verifica se o filtro está vazio."""
        return len(self.conditions) == 0 and len(self.filters) == 0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KonectyFilter":
        """Converte dicionário para filtro."""
        return cls(**data)

    @classmethod
    def create(cls, match: Union[FilterMatch, str] = FilterMatch.AND) -> "KonectyFilter":
        """Cria uma nova instância de filtro.

        Args:
            match: Tipo de correspondência ("and" ou "or")

        Returns:
            Nova instância de KonectyFilter
        """
        if isinstance(match, str):
            match = FilterMatch(match.lower())
        return cls(match=match)

    def add_condition(
        self, term: str, operator: Union[FilterOperator, str], value: Any, disabled: bool = False
    ) -> "KonectyFilter":
        """Adiciona uma condição ao filtro.

        Args:
            term: Campo a ser filtrado
            operator: Operador de comparação
            value: Valor para comparação
            disabled: Se a condição está desativada

        Returns:
            Self para encadeamento
        """
        if isinstance(operator, str):
            operator = FilterOperator(operator.lower())

        self.conditions.append(
            FilterCondition(
                term=term,
                operator=operator,
                value=value,
                disabled=disabled,
            )
        )
        return self

    def add_within_radius(
        self, term: str, center: WithinRadiusCenter, radius: float
    ) -> "KonectyFilter":
        """Adiciona uma condição ``within_radius`` ao filtro.

        Args:
            term: Campo de tipo ``address`` (sem o sufixo ``.geolocation``)
            center: ``(longitude, latitude)`` — longitude PRIMEIRO — ou a
                referência ``{"document", "_id", "field"}`` a outro registro
            radius: Raio em **metros**

        Returns:
            Self para encadeamento
        """
        self.conditions.append(within_radius_condition(term, center, radius))
        return self

    def add_filter(self, match: Union[FilterMatch, str] = FilterMatch.AND) -> "KonectyFilter":
        """Adiciona um filtro aninhado.

        Args:
            match: Tipo de correspondência do filtro aninhado

        Returns:
            Novo filtro aninhado
        """
        if isinstance(match, str):
            match = FilterMatch(match.lower())

        nested_filter = KonectyFilter(match=match)
        self.filters.append(nested_filter)
        return nested_filter


class SortDirection(str, Enum):
    """Direção da ordenação."""

    ASC = "ASC"
    DESC = "DESC"


class SortOrder(BaseModel):
    """Ordenação de resultados."""

    property: str = Field(..., description="Campo para ordenação")
    direction: SortDirection = Field(..., description="Direção da ordenação")


class KonectyFindParams(BaseModel):
    """Parâmetros para busca no Konecty."""

    filter: KonectyFilter
    start: Optional[int] = None
    limit: Optional[int] = None
    sort: Optional[List[SortOrder]] = None
    fields: Optional[List[Union[str, int]]] = None
