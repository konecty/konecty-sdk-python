from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, TypedDict, Union

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


#: Campo calculado que o servidor acrescenta a cada registro devolvido por ``find``
#: quando o filtro tem **um** centro de distância: a única condição ``within_radius``
#: habilitada no caminho AND do filtro da requisição. Valor em **metros**, inteiro.
#: Com zero ou duas+ condições nessa posição, ou quando o usuário não pode ler o campo
#: ``address`` do centro, o campo simplesmente não vem — não é erro.
#:
#: É também o ``property`` de ordenação por distância:
#: ``SortOrder(property=DISTANCE_FIELD, direction=SortDirection.ASC)``.
#:
#: Nunca é gravado: devolver o registro inteiro num ``update`` com ``_distance``
#: dentro é recusado pelo servidor como campo inexistente.
#:
#: Espelha ``DISTANCE_FIELD`` no SDK TypeScript (``src/sdk/filters/withinRadius.ts``).
DISTANCE_FIELD = "_distance"

#: Referência ao registro de onde tirar o centro, em vez de coordenadas literais:
#: "perto do empreendimento X". O servidor lê o registro sob controle de acesso
#: completo e substitui pelas coordenadas antes de compilar a query.
#:
#: ``field`` é obrigatório porque um documento pode ter mais de um campo
#: ``address`` e adivinhar seria escolher em silêncio.
WithinRadiusCenterRef = TypedDict(
    "WithinRadiusCenterRef",
    {"document": str, "_id": str, "field": str},
)


def within_radius_condition(
    term: str,
    *,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    record: Optional[WithinRadiusCenterRef] = None,
    radius: float,
) -> "FilterCondition":
    """
    Monta a condição de filtro do operador ``within_radius``.

    O ``term`` é o campo ``address`` puro: o sufixo ``.geolocation`` é
    acrescentado pelo SERVIDOR, não pelo cliente. O ``radius`` é em **metros**.
    O centro é ``lat``/``lng`` **ou** ``record`` — exatamente uma das duas formas.

    .. code-block:: python

        within_radius_condition("address", lat=-30.0346, lng=-51.2177, radius=5000)
        # value={"lat": -30.0346, "lng": -51.2177, "radius": 5000}

        within_radius_condition(
            "address",
            record={"document": "Development", "_id": "<id>", "field": "address"},
            radius=2000,
        )

    Todos os parâmetros depois de ``term`` são nomeados: a forma antiga
    ``within_radius_condition(term, (lng, lat), radius)`` deixou de existir e
    levanta ``TypeError``.

    O SDK **não** valida faixa, teto de raio nem a exclusão mútua das formas:
    quem decide é o servidor, e um teto copiado aqui passaria a mentir assim que
    o backend mudasse. O que o chamador passou vai para a requisição — as duas
    formas juntas inclusive, para o servidor recusar nomeando o problema — e
    nada é convertido para número. Valor recusado volta como
    ``WITHIN_RADIUS_INVALID_VALUE``.

    Espelha ``withinRadiusCondition`` no SDK TypeScript — a mesma entrada produz
    a mesma saída (travado por teste: ``tests/test_within_radius.py`` e
    ``src/__test__/api/withinRadius.test.ts``).

    A ARIDADE difere de propósito: lá é ``withinRadiusCondition(term, {lat, lng,
    radius})``, porque o SDK TypeScript passa objeto de opções em todo lugar;
    aqui são parâmetros nomeados, que é a convenção deste SDK. A paridade que
    importa é mesma entrada → mesma saída, não a forma de chamar.
    """
    value: Dict[str, Any] = {}
    if lat is not None:
        value["lat"] = lat
    if lng is not None:
        value["lng"] = lng
    if record is not None:
        value["record"] = dict(record) if isinstance(record, Mapping) else record
    value["radius"] = radius
    return FilterCondition(
        term=term,
        operator=FilterOperator.WITHIN_RADIUS,
        value=value,
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
    conditions: List[FilterCondition] = Field(
        default_factory=list, description="Lista de condições"
    )
    filters: List["KonectyFilter"] = Field(
        default_factory=list, description="Lista de filtros aninhados"
    )

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
    def create(
        cls, match: Union[FilterMatch, str] = FilterMatch.AND
    ) -> "KonectyFilter":
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
        self,
        term: str,
        operator: Union[FilterOperator, str],
        value: Any,
        disabled: bool = False,
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
        self,
        term: str,
        *,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        record: Optional[WithinRadiusCenterRef] = None,
        radius: float,
    ) -> "KonectyFilter":
        """Adiciona uma condição ``within_radius`` ao filtro.

        Args:
            term: Campo de tipo ``address`` (sem o sufixo ``.geolocation``)
            lat: Latitude do centro, em ``[-90, 90]``
            lng: Longitude do centro, em ``[-180, 180]``
            record: Ou, no lugar de ``lat``/``lng``, a referência
                ``{"document", "_id", "field"}`` a outro registro
            radius: Raio em **metros**

        Returns:
            Self para encadeamento

        Nota: o SDK TypeScript **não** tem equivalente disto, e é escolha: lá o
        filtro é objeto literal, não há classe de builder nenhuma, e criar uma só
        para este operador seria superfície pública nova sem caso de uso.
        """
        self.conditions.append(
            within_radius_condition(
                term, lat=lat, lng=lng, record=record, radius=radius
            )
        )
        return self

    def add_filter(
        self, match: Union[FilterMatch, str] = FilterMatch.AND
    ) -> "KonectyFilter":
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
