"""Export list as CSV, XLSX, or JSON (bytes)."""

import json
from typing import Any, Dict, List, Literal, Optional, Union

from ..serialization import json_serial
from ..filters import KonectyFilter
from .base import BaseService

ExportFormat = Literal["csv", "xlsx", "json", "xls"]


class ExportService(BaseService):
    """Service for exporting lists (GET returns file bytes)."""

    async def export_list(
        self,
        module: str,
        list_name: str,
        format: ExportFormat,
        *,
        filter_params: Optional[KonectyFilter] = None,
        sort: Optional[Any] = None,
        fields: Optional[List[Union[str, int]]] = None,
        start: Optional[int] = None,
        limit: Optional[int] = None,
        display_name: Optional[str] = None,
        display_type: Optional[str] = None,
    ) -> bytes:
        """
        Export list as file. GET /rest/data/{module}/list/{list_name}/{type}.
        type is csv, xlsx, or json (xls is normalized to xlsx).
        Returns file content as bytes.
        """
        export_type = "xlsx" if format == "xls" else format
        if export_type not in ("csv", "xlsx", "json"):
            raise ValueError("format must be csv, xlsx, json, or xls")
        params: Dict[str, str] = {}
        if filter_params is not None:
            params["filter"] = json.dumps(filter_params.to_json(), default=json_serial)
        if sort is not None:
            params["sort"] = json.dumps(sort, default=json_serial) if not isinstance(sort, str) else sort
        if fields is not None:
            params["fields"] = ",".join(str(f) for f in fields)
        if start is not None:
            params["start"] = str(start)
        if limit is not None:
            params["limit"] = str(limit)
        if display_name is not None:
            params["displayName"] = display_name
        if display_type is not None:
            params["displayType"] = display_type
        path = f"/rest/data/{module}/list/{list_name}/{export_type}"
        return await self._get(path, params=params, return_bytes=True)
