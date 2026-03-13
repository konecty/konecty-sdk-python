"""Feature-specific types (KPI, Graph, Pivot, CrossModuleQuery, etc.). Re-exported for convenience."""

from .cross_module_query import (
    CrossModuleQuery,
    CrossModuleRelation,
    Aggregator,
    DEFAULT_PRIMARY_LIMIT,
    MAX_RELATION_LIMIT,
    MAX_RELATIONS,
)
from .kpi import KpiConfig, KpiOperation

__all__ = [
    "Aggregator",
    "CrossModuleQuery",
    "CrossModuleRelation",
    "DEFAULT_PRIMARY_LIMIT",
    "KpiConfig",
    "KpiOperation",
    "MAX_RELATION_LIMIT",
    "MAX_RELATIONS",
]
