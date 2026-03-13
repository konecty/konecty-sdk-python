"""KPI config for aggregation API."""

from typing import Literal, Optional

from pydantic import BaseModel, model_validator


KpiOperation = Literal["count", "sum", "avg", "min", "max", "countDistinct"]


class KpiConfig(BaseModel):
    """Config for KPI aggregation. Field is required for all operations except count."""

    operation: KpiOperation
    field: Optional[str] = None

    @model_validator(mode="after")
    def count_distinct_requires_field(self) -> "KpiConfig":
        if self.operation == "countDistinct" and not self.field:
            raise ValueError("countDistinct requires field")
        return self
