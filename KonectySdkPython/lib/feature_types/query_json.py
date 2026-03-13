"""
Strongly-typed query creator for POST /rest/query/json (Konecty cross-module query).
Use classes/dataclasses with properties for full intellisense; no builder pattern.
Serializes to the exact payload Konecty expects via to_dict().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Union

# ---------------------------------------------------------------------------
# Literal types (Konecty schema)
# ---------------------------------------------------------------------------

AggregatorName = Literal[
    "count",
    "countDistinct",
    "sum",
    "avg",
    "min",
    "max",
    "first",
    "last",
    "push",
    "addToSet",
]
"""Allowed aggregator names for relations (Konecty schema)."""

FilterMatch = Literal["and", "or"]
SortDirection = Literal["ASC", "DESC"]

# Value in a filter condition: scalar or list (e.g. for "in" operator)
ConditionValue = Union[str, int, float, bool, None, List[Union[str, int, float, bool]]]


# ---------------------------------------------------------------------------
# Filter (KonFilter)
# ---------------------------------------------------------------------------


@dataclass(frozen=False)
class QueryFilterCondition:
    """Single condition: term, operator, optional value. Mirrors Konecty Condition."""

    term: str
    operator: str
    value: Optional[ConditionValue] = None
    editable: Optional[bool] = None
    disabled: Optional[bool] = None
    sort: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"term": self.term, "operator": self.operator}
        if self.value is not None:
            out["value"] = self.value
        if self.editable is not None:
            out["editable"] = self.editable
        if self.disabled is not None:
            out["disabled"] = self.disabled
        if self.sort is not None:
            out["sort"] = self.sort
        return out


@dataclass(frozen=False)
class QueryFilter:
    """Filter for query or relation. match + conditions; optional textSearch and nested filters."""

    match: FilterMatch = "and"
    conditions: List[QueryFilterCondition] = field(default_factory=list)
    text_search: Optional[str] = None
    filters: Optional[List["QueryFilter"]] = None

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"match": self.match}
        if self.conditions:
            out["conditions"] = [c.to_dict() for c in self.conditions]
        if self.text_search is not None:
            out["textSearch"] = self.text_search
        if self.filters:
            out["filters"] = [f.to_dict() for f in self.filters]
        return out


# ---------------------------------------------------------------------------
# Sort
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QuerySortItem:
    """Sort item: property and direction. Konecty sort element."""

    property: str
    direction: SortDirection = "ASC"

    def to_dict(self) -> Dict[str, Any]:
        return {"property": self.property, "direction": self.direction}


# ---------------------------------------------------------------------------
# Join (explicit on)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExplicitJoinCondition:
    """Explicit join: left and right keys. Optional in relation."""

    left: str
    right: str

    def to_dict(self) -> Dict[str, Any]:
        return {"left": self.left, "right": self.right}


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AggregatorSpec:
    """Aggregator in a relation. aggregator (name); field required for countDistinct and similar."""

    aggregator: AggregatorName
    field: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"aggregator": self.aggregator}
        if self.field is not None:
            out["field"] = self.field
        return out


# ---------------------------------------------------------------------------
# Relation (nested)
# ---------------------------------------------------------------------------

# Sort in relation: list of QuerySortItem or single string (e.g. "_createdAt DESC")
RelationSort = Union[List[QuerySortItem], str]


@dataclass(frozen=False)
class QueryRelation:
    """
    Relation in a cross-module query. document + lookup; at least one aggregator required.
    Optional: on, filter, fields, sort, limit, start; optional nested relations.
    """

    document: str
    lookup: str
    aggregators: Dict[str, AggregatorSpec]
    on: Optional[ExplicitJoinCondition] = None
    filter: Optional[QueryFilter] = None
    fields: Optional[str] = None
    sort: Optional[RelationSort] = None
    limit: int = 1000
    start: int = 0
    relations: Optional[List["QueryRelation"]] = None

    def to_dict(self) -> Dict[str, Any]:
        if not self.aggregators:
            raise ValueError("At least one aggregator is required per relation")
        out: Dict[str, Any] = {
            "document": self.document,
            "lookup": self.lookup,
            "aggregators": {k: v.to_dict() for k, v in self.aggregators.items()},
            "limit": self.limit,
            "start": self.start,
        }
        if self.on is not None:
            out["on"] = self.on.to_dict()
        if self.filter is not None:
            out["filter"] = self.filter.to_dict()
        if self.fields is not None:
            out["fields"] = self.fields
        if self.sort is not None:
            if isinstance(self.sort, str):
                out["sort"] = self.sort
            else:
                out["sort"] = [s.to_dict() for s in self.sort]
        if self.relations:
            out["relations"] = [r.to_dict() for r in self.relations]
        return out


# ---------------------------------------------------------------------------
# Root query (CrossModuleQuery)
# ---------------------------------------------------------------------------

# Sort at root: list of QuerySortItem or string
QuerySort = Union[List[QuerySortItem], str]

# Limits (Konecty constants)
MAX_RELATION_LIMIT_QUERY = 100_000
DEFAULT_PRIMARY_LIMIT_QUERY = 1000


@dataclass(frozen=False)
class QueryJson:
    """
    Fully-typed body for POST /rest/query/json. Primary document + optional filter,
    fields, sort, limit, start, relations, groupBy, aggregators, includeTotal, includeMeta.
    Use to_dict() to get the API payload (camelCase where required).
    """

    document: str
    filter: Optional[QueryFilter] = None
    fields: Optional[str] = None
    sort: Optional[QuerySort] = None
    limit: int = DEFAULT_PRIMARY_LIMIT_QUERY
    start: int = 0
    relations: List[QueryRelation] = field(default_factory=list)
    group_by: List[str] = field(default_factory=list)
    aggregators: Dict[str, AggregatorSpec] = field(default_factory=dict)
    include_total: bool = True
    include_meta: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Payload for POST /rest/query/json (camelCase for includeTotal, includeMeta, groupBy)."""
        out: Dict[str, Any] = {
            "document": self.document,
            "limit": max(1, min(self.limit, MAX_RELATION_LIMIT_QUERY)),
            "start": max(0, self.start),
            "relations": [r.to_dict() for r in self.relations],
            "groupBy": self.group_by,
            "aggregators": {k: v.to_dict() for k, v in self.aggregators.items()},
            "includeTotal": self.include_total,
            "includeMeta": self.include_meta,
        }
        if self.filter is not None:
            out["filter"] = self.filter.to_dict()
        if self.fields is not None:
            out["fields"] = self.fields
        if self.sort is not None:
            if isinstance(self.sort, str):
                out["sort"] = self.sort
            else:
                out["sort"] = [s.to_dict() for s in self.sort]
        return out
