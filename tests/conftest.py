"""Shared test fixtures: a local aiohttp stub of the Konecty API."""

from typing import Any, Dict, List, Optional, Tuple

import pytest_asyncio
from aiohttp import web


class StubServer:
    """Local HTTP server that answers canned responses and records the requests it got."""

    def __init__(self) -> None:
        self.app = web.Application()
        self.requests: List[Dict[str, Any]] = []
        self.base_url = ""
        self._responses: Dict[Tuple[str, str], Tuple[Any, int]] = {}
        self.app.router.add_route("*", "/{tail:.*}", self._handle)

    def route(self, method: str, path: str, body: Any, status: int = 200) -> None:
        """Register the response for a method/path pair."""
        self._responses[(method.upper(), path)] = (body, status)

    async def _handle(self, request: web.Request) -> web.Response:
        payload: Optional[Any] = None
        if request.can_read_body:
            payload = await request.json()
        self.requests.append(
            {
                "method": request.method,
                "path": request.path,
                "query": dict(request.query),
                "json": payload,
                "authorization": request.headers.get("Authorization"),
            }
        )
        response = self._responses.get((request.method, request.path))
        if response is None:
            return web.json_response(
                {"success": False, "errors": [{"message": "not stubbed"}]}, status=404
            )
        body, status = response
        return web.json_response(body, status=status)


@pytest_asyncio.fixture
async def stub_server():
    """Start a StubServer on an ephemeral port and expose its base_url."""
    server = StubServer()
    runner = web.AppRunner(server.app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]
    server.base_url = f"http://127.0.0.1:{port}"
    try:
        yield server
    finally:
        await runner.cleanup()
