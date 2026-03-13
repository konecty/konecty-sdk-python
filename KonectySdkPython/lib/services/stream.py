"""Stream API: find_stream (NDJSON) and count_stream."""

import json
from typing import Any, AsyncGenerator, Dict, Optional

from ..client import KonectyDict, json_serial
from ..filters import KonectyFilter, KonectyFindParams
from ..http import StreamResponse
from .base import BaseService


def _find_params_to_query(options: KonectyFindParams) -> Dict[str, str]:
    """Build query params dict from KonectyFindParams (same as client.find)."""
    params: Dict[str, str] = {}
    for key, value in options.model_dump(exclude_none=True).items():
        params[key] = (
            json.dumps(value, default=json_serial)
            if key != "fields"
            else ",".join(str(f) for f in value)
        )
    return params


class FindStreamResult:
    """Result of find_stream. Has .stream (async generator of records) and .total (int | None)."""

    __slots__ = ("stream", "total")

    def __init__(
        self,
        stream: AsyncGenerator[KonectyDict, None],
        total: Optional[int],
    ) -> None:
        self.stream = stream
        self.total = total


class StreamService(BaseService):
    """Service for stream endpoints: findStream and count."""

    async def find_stream(
        self,
        module: str,
        options: KonectyFindParams,
        *,
        include_total: bool = False,
    ) -> FindStreamResult:
        """
        Stream records as NDJSON (one JSON object per line). Uses GET /rest/stream/{module}/findStream.

        Args:
            module: Document/module name.
            options: Find params (filter, sort, limit, start, fields).
            include_total: If True, request total count; it will be in result.total and X-Total-Count header.

        Returns:
            FindStreamResult with .stream (async generator of dicts) and .total (int | None when include_total).
        """
        params = _find_params_to_query(options)
        if include_total:
            params["includeTotal"] = "1"
        path = f"/rest/stream/{module}/findStream"
        raw = await self._get(path, params=params, stream=True)
        assert isinstance(raw, StreamResponse)
        total: Optional[int] = None
        if include_total:
            tc = raw.headers.get("X-Total-Count")
            if tc is not None:
                try:
                    total = int(tc)
                except ValueError:
                    pass

        async def gen() -> AsyncGenerator[KonectyDict, None]:
            async with raw:
                while True:
                    line = await raw.readline()
                    if not line:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    yield json.loads(line.decode("utf-8"))

        return FindStreamResult(stream=gen(), total=total)

    async def count_stream(
        self,
        module: str,
        filter_params: Optional[KonectyFilter] = None,
        *,
        display_name: Optional[str] = None,
        display_type: Optional[str] = None,
        sort: Optional[Any] = None,
        with_detail_fields: Optional[bool] = None,
    ) -> int:
        """
        Return total count for the module matching the filter. GET /rest/stream/{module}/count.

        Args:
            module: Document/module name.
            filter_params: Optional filter. If None, uses empty filter (count all, subject to permissions).
            display_name: Optional.
            display_type: Optional.
            sort: Optional sort (string or list).
            with_detail_fields: Optional.

        Returns:
            Total count.
        """
        filter_obj = filter_params or KonectyFilter.create()
        options = KonectyFindParams(filter=filter_obj)
        params: Dict[str, str] = {}
        for key, value in options.model_dump(exclude_none=True).items():
            params[key] = (
                json.dumps(value, default=json_serial)
                if key != "fields"
                else ",".join(str(f) for f in value)
            )
        if display_name is not None:
            params["displayName"] = str(display_name)
        if display_type is not None:
            params["displayType"] = str(display_type)
        if sort is not None:
            params["sort"] = json.dumps(sort, default=json_serial) if not isinstance(sort, str) else sort
        if with_detail_fields is not None:
            params["withDetailFields"] = "1" if with_detail_fields else "0"
        path = f"/rest/stream/{module}/count"
        result = await self._get(path, params=params)
        if isinstance(result, dict) and "total" in result:
            return int(result["total"])
        return 0
