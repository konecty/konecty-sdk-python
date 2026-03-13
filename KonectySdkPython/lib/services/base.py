"""Base service class. All domain services inherit from it and delegate HTTP to the client."""

from typing import Any, Dict, Optional, TypeVar

Client = TypeVar("Client", bound=Any)


class BaseService:
    """Base for all Konecty API services. Exposes _get, _post, _put, _delete via client._request."""

    def __init__(self, client: Client) -> None:
        self._client = client

    async def _get(
        self,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        stream: bool = False,
        return_bytes: bool = False,
    ) -> Any:
        return await self._client._request(
            "GET", path, params=params, stream=stream, return_bytes=return_bytes
        )

    async def _post(
        self,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        stream: bool = False,
    ) -> Any:
        return await self._client._request(
            "POST", path, params=params, json=json, stream=stream
        )

    async def _put(
        self,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Any:
        return await self._client._request("PUT", path, params=params, json=json)

    async def _delete(
        self,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Any:
        return await self._client._request("DELETE", path, params=params, json=json)

    async def _patch(
        self,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Any:
        return await self._client._request("PATCH", path, params=params, json=json)
