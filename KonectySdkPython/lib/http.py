"""HTTP helpers for Konecty API requests. Used by KonectyClient and services."""

import logging
from typing import Any, Dict, Optional, Union

import aiohttp

from .exceptions import KonectyAPIError

logger = logging.getLogger(__name__)


class StreamResponse:
    """
    Wrapper for streaming HTTP response. Caller can read headers and iterate body by line.
    Must be used as async context manager so the session and response are closed on exit.
    """

    __slots__ = ("_session", "_response")

    def __init__(self, session: aiohttp.ClientSession, response: aiohttp.ClientResponse) -> None:
        self._session = session
        self._response = response

    @property
    def headers(self) -> Dict[str, str]:
        return dict(self._response.headers)

    async def readline(self) -> bytes:
        """Read one line (including newline). Returns empty bytes when done."""
        return await self._response.content.readline()

    async def __aenter__(self) -> "StreamResponse":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._response.release()
        await self._session.close()


async def request(
    client: Any,
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
    stream: bool = False,
    return_bytes: bool = False,
) -> Union[Dict[str, Any], StreamResponse, bytes]:
    """
    Perform an HTTP request using the client's base_url and headers.

    Args:
        client: KonectyClient (must have base_url and headers).
        method: HTTP method (GET, POST, PUT, DELETE, etc.).
        path: Path (e.g. /rest/data/Contact/find). Must not include base_url.
        params: Optional query parameters.
        json: Optional JSON body.
        stream: If True, return StreamResponse for reading body by line; do not parse JSON.
        return_bytes: If True (and not stream), return response body as bytes; do not parse JSON.

    Returns:
        If stream=True: StreamResponse (use as async with). Has .headers and .readline().
        If return_bytes=True: bytes.
        Else: parsed JSON dict. Raises KonectyAPIError if success is false.
    """
    url = f"{client.base_url.rstrip('/')}{path}"
    kwargs: Dict[str, Any] = {"headers": client.headers}
    if params is not None:
        kwargs["params"] = params
    if json is not None:
        kwargs["json"] = json

    if stream:
        session = aiohttp.ClientSession()
        response = await session.request(method, url, **kwargs)
        response.raise_for_status()
        return StreamResponse(session, response)

    async with aiohttp.ClientSession() as session:
        async with session.request(method, url, **kwargs) as response:
            if return_bytes:
                response.raise_for_status()
                return await response.read()
            body = await response.json()
            if response.status >= 400:
                errors = body.get("errors", []) if isinstance(body, dict) else []
                logger.error("API error %s: %s", response.status, errors)
                raise KonectyAPIError(errors)
            if isinstance(body, dict) and body.get("success") is False:
                errors = body.get("errors", [])
                logger.error(errors)
                raise KonectyAPIError(errors)
            return body
