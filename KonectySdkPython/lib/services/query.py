"""Custom query (query/json, query/sql) and Saved Queries CRUD."""

import json
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

from ..types import KonectyDict
from ..exceptions import KonectyAPIError
from ..http import StreamResponse
from .base import BaseService


class QueryResult:
    """Result of execute_query_json or execute_query_sql. Stream of records + optional total and meta."""

    __slots__ = ("stream", "total", "meta")

    def __init__(
        self,
        stream: AsyncGenerator[KonectyDict, None],
        total: Optional[int] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.stream = stream
        self.total = total
        self.meta = meta


async def _build_query_result(
    raw: StreamResponse,
    include_meta: bool,
    include_total: bool,
) -> QueryResult:
    """Read first line (maybe _meta), then return QueryResult. Generator consumes the rest."""
    total: Optional[int] = None
    meta: Optional[Dict[str, Any]] = None
    if include_total:
        tc = raw.headers.get("X-Total-Count")
        if tc is not None:
            try:
                total = int(tc)
            except ValueError:
                pass

    first_record: Optional[KonectyDict] = None
    while True:
        line = await raw.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line.decode("utf-8"))
        if isinstance(obj, dict) and "_meta" in obj:
            m = obj["_meta"]
            if m.get("success") is False:
                errors = m.get("errors", [])
                raise KonectyAPIError(errors)
            if include_meta:
                meta = m
                if total is None and "total" in m:
                    total = m["total"]
            continue
        first_record = obj
        break

    async def gen() -> AsyncGenerator[KonectyDict, None]:
        if first_record is not None:
            yield first_record
        async with raw:
            while True:
                line = await raw.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line.decode("utf-8"))

    return QueryResult(stream=gen(), total=total, meta=meta)


class QueryService(BaseService):
    """Service for custom query (JSON/SQL) and saved queries."""

    async def execute_query_json(
        self,
        body: Union[Dict[str, Any], Any],
        *,
        include_total: bool = True,
        include_meta: bool = False,
    ) -> QueryResult:
        """
        Execute a cross-module query. POST /rest/query/json. Body is CrossModuleQuery (dict or model).
        Returns QueryResult with .stream (async generator), .total, .meta.
        """
        if hasattr(body, "to_dict"):
            payload = body.to_dict()
        elif hasattr(body, "model_dump"):
            payload = body.model_dump(by_alias=True, exclude_none=True)
        else:
            payload = dict(body)
        path = "/rest/query/json"
        raw = await self._post(path, json=payload, stream=True)
        if not isinstance(raw, StreamResponse):
            raise KonectyAPIError(["Unexpected non-stream response"])
        return await _build_query_result(
            raw, include_meta=include_meta, include_total=include_total
        )

    async def execute_query_sql(
        self,
        sql: str,
        *,
        include_total: bool = True,
        include_meta: bool = False,
    ) -> QueryResult:
        """
        Execute SQL (converted to cross-module query server-side). POST /rest/query/sql.
        Returns QueryResult. On SQL parse error the server returns 400 with _meta.errors.
        """
        payload: Dict[str, Any] = {"sql": sql}
        if include_total is not None:
            payload["includeTotal"] = include_total
        if include_meta is not None:
            payload["includeMeta"] = include_meta
        path = "/rest/query/sql"
        raw = await self._post(path, json=payload, stream=True)
        if not isinstance(raw, StreamResponse):
            raise KonectyAPIError(["Unexpected non-stream response"])
        return await _build_query_result(
            raw, include_meta=include_meta, include_total=include_total
        )

    # --- Saved queries ---

    async def list_saved_queries(self) -> Dict[str, Any]:
        """GET /rest/query/saved."""
        return await self._get("/rest/query/saved")

    async def get_saved_query(self, query_id: str) -> Dict[str, Any]:
        """GET /rest/query/saved/{id}."""
        path = f"/rest/query/saved/{query_id}"
        return await self._get(path)

    async def create_saved_query(
        self,
        name: str,
        query: Dict[str, Any],
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /rest/query/saved. Body: name, query (CrossModuleQuery), description?."""
        body: Dict[str, Any] = {"name": name, "query": query}
        if description is not None:
            body["description"] = description
        return await self._post("/rest/query/saved", json=body)

    async def update_saved_query(
        self,
        query_id: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        query: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """PUT /rest/query/saved/{id}. Body: name?, description?, query?."""
        body: Dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if query is not None:
            body["query"] = query
        path = f"/rest/query/saved/{query_id}"
        return await self._put(path, json=body)

    async def delete_saved_query(self, query_id: str) -> Dict[str, Any]:
        """DELETE /rest/query/saved/{id}."""
        path = f"/rest/query/saved/{query_id}"
        return await self._delete(path)

    async def share_saved_query(
        self,
        query_id: str,
        shared_with: List[Dict[str, Any]],
        is_public: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """PATCH /rest/query/saved/{id}/share. Body: sharedWith (array of { type, _id, name }), isPublic?."""
        body: Dict[str, Any] = {"sharedWith": shared_with}
        if is_public is not None:
            body["isPublic"] = is_public
        path = f"/rest/query/saved/{query_id}/share"
        return await self._patch(path, json=body)
