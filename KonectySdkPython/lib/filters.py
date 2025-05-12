from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

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
