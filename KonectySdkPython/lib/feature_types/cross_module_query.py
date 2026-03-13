"""Types for cross-module query (query/json and query/sql). Mirrors Konecty crossModuleQuery schema."""

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

MAX_RELATIONS = 10
MAX_NESTING_DEPTH = 2
MAX_RELATION_LIMIT = 100_000
DEFAULT_RELATION_LIMIT = 1000
DEFAULT_PRIMARY_LIMIT = 1000

AggregatorName = (
    str  # count, countDistinct, sum, avg, min, max, first, last, push, addToSet
)


class Aggregator(BaseModel):
    """Aggregator in a relation or root. Field required for some (e.g. countDistinct)."""

    aggregator: str
    field: Optional[str] = None


class SortItem(BaseModel):
    """Sort item: property and direction."""

    property: str
    direction: str = "ASC"  # ASC | DESC


class ExplicitJoinCondition(BaseModel):
    """Explicit join condition: left and right keys."""

    left: str
    right: str


class CrossModuleRelation(BaseModel):
    """Relation in a cross-module query. At least one aggregator required."""

    document: str
    lookup: str
    on: Optional[ExplicitJoinCondition] = None
    filter: Optional[Dict[str, Any]] = None
    fields: Optional[str] = None
    sort: Optional[Union[str, List[SortItem]]] = None
    limit: int = Field(default=DEFAULT_RELATION_LIMIT, ge=1, le=MAX_RELATION_LIMIT)
    start: int = Field(default=0, ge=0)
    aggregators: Dict[str, Aggregator] = Field(..., min_length=1)
    relations: Optional[List["CrossModuleRelation"]] = Field(
        default=None, max_length=MAX_RELATIONS
    )

    model_config = {"extra": "allow"}


CrossModuleRelation.model_rebuild()


class CrossModuleQuery(BaseModel):
    """Body for POST /rest/query/json. Primary document + optional relations, groupBy, aggregators."""

    document: str
    filter: Optional[Dict[str, Any]] = None
    fields: Optional[str] = None
    sort: Optional[Union[str, List[SortItem]]] = None
    limit: int = Field(default=DEFAULT_PRIMARY_LIMIT, ge=1, le=MAX_RELATION_LIMIT)
    start: int = Field(default=0, ge=0)
    relations: List[CrossModuleRelation] = Field(
        default_factory=list, max_length=MAX_RELATIONS
    )
    groupBy: List[str] = Field(default_factory=list, alias="groupBy")
    aggregators: Dict[str, Aggregator] = Field(default_factory=dict)
    includeTotal: bool = Field(default=True, alias="includeTotal")
    includeMeta: bool = Field(default=False, alias="includeMeta")

    model_config = {"extra": "allow", "populate_by_name": True}
