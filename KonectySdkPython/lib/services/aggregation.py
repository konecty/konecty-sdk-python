"""Aggregation API: KPI, Graph, Pivot."""

import json
from typing import Any, Dict, Optional, Union

from ..client import json_serial
from ..filters import KonectyFilter
from ..feature_types.kpi import KpiConfig
from .base import BaseService


class AggregationService(BaseService):
    """Service for KPI, Graph, and Pivot aggregations."""

    async def get_kpi(
        self,
        module: str,
        kpi_config: KpiConfig,
        *,
        filter_params: Optional[KonectyFilter] = None,
        display_name: Optional[str] = None,
        display_type: Optional[str] = None,
        sort: Optional[Any] = None,
        limit: Optional[int] = None,
        start: Optional[int] = None,
        with_detail_fields: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Run KPI aggregation. GET /rest/data/{module}/kpi. Returns { value, count }.
        """
        params: Dict[str, str] = {
            "kpiConfig": json.dumps(kpi_config.model_dump(exclude_none=True)),
        }
        if filter_params is not None:
            params["filter"] = json.dumps(filter_params.to_json(), default=json_serial)
        if display_name is not None:
            params["displayName"] = display_name
        if display_type is not None:
            params["displayType"] = display_type
        if sort is not None:
            params["sort"] = json.dumps(sort, default=json_serial) if not isinstance(sort, str) else sort
        if limit is not None:
            params["limit"] = str(limit)
        if start is not None:
            params["start"] = str(start)
        if with_detail_fields is not None:
            params["withDetailFields"] = "1" if with_detail_fields else "0"
        path = f"/rest/data/{module}/kpi"
        result = await self._get(path, params=params)
        if isinstance(result, dict) and result.get("success"):
            return {"value": result.get("value", 0), "count": result.get("count", 0)}
        return {"value": 0, "count": 0}

    async def get_graph(
        self,
        module: str,
        graph_config: Union[Dict[str, Any], Any],
        *,
        filter_params: Optional[KonectyFilter] = None,
        display_name: Optional[str] = None,
        display_type: Optional[str] = None,
        sort: Optional[Any] = None,
        limit: Optional[int] = None,
        start: Optional[int] = None,
        with_detail_fields: Optional[bool] = None,
        lang: Optional[str] = None,
    ) -> str:
        """
        Get graph as SVG. GET /rest/data/{module}/graph. graphConfig: type, xAxis, yAxis, series, etc.
        """
        payload = (
            graph_config.model_dump(by_alias=True, exclude_none=True)
            if hasattr(graph_config, "model_dump")
            else graph_config
        )
        params: Dict[str, str] = {"graphConfig": json.dumps(payload)}
        if filter_params is not None:
            params["filter"] = json.dumps(filter_params.to_json(), default=json_serial)
        if display_name is not None:
            params["displayName"] = display_name
        if display_type is not None:
            params["displayType"] = display_type
        if sort is not None:
            params["sort"] = json.dumps(sort, default=json_serial) if not isinstance(sort, str) else sort
        if limit is not None:
            params["limit"] = str(limit)
        if start is not None:
            params["start"] = str(start)
        if with_detail_fields is not None:
            params["withDetailFields"] = "1" if with_detail_fields else "0"
        if lang is not None:
            params["lang"] = lang
        path = f"/rest/data/{module}/graph"
        raw = await self._get(path, params=params, return_bytes=True)
        if isinstance(raw, bytes):
            return raw.decode("utf-8")
        return str(raw)

    async def get_pivot(
        self,
        module: str,
        pivot_config: Union[Dict[str, Any], Any],
        *,
        filter_params: Optional[KonectyFilter] = None,
        display_name: Optional[str] = None,
        display_type: Optional[str] = None,
        sort: Optional[Any] = None,
        limit: Optional[int] = None,
        start: Optional[int] = None,
        with_detail_fields: Optional[bool] = None,
        lang: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get pivot table result. GET /rest/data/{module}/pivot. pivotConfig: rows, columns, values.
        """
        payload = (
            pivot_config.model_dump(by_alias=True, exclude_none=True)
            if hasattr(pivot_config, "model_dump")
            else pivot_config
        )
        params: Dict[str, str] = {"pivotConfig": json.dumps(payload)}
        if filter_params is not None:
            params["filter"] = json.dumps(filter_params.to_json(), default=json_serial)
        if display_name is not None:
            params["displayName"] = display_name
        if display_type is not None:
            params["displayType"] = display_type
        if sort is not None:
            params["sort"] = json.dumps(sort, default=json_serial) if not isinstance(sort, str) else sort
        if limit is not None:
            params["limit"] = str(limit)
        if start is not None:
            params["start"] = str(start)
        if with_detail_fields is not None:
            params["withDetailFields"] = "1" if with_detail_fields else "0"
        if lang is not None:
            params["lang"] = lang
        path = f"/rest/data/{module}/pivot"
        result = await self._get(path, params=params)
        if isinstance(result, dict):
            return result
        return {}
