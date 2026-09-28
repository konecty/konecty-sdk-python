"""
Sessão HTTP do streaming não pode vazar quando o Konecty responde erro.

Com `stream=True` o `request()` abre uma `ClientSession` fora de `async with` e
a entrega ao `StreamResponse`, que a fecha no `__aexit__`. Se o request ou o
`raise_for_status()` falhavam antes disso, ninguém fechava a sessão: o erro
subia para quem chamou e o garbage collector logava `Unclosed client session` e
`Unclosed connector`. Em produção isso aparecia no crm-interativo a cada
fallback do map-stream (filtro de bounds recusado pelo Konecty).

Não há paridade com o SDK TypeScript: lá o `findStream` usa `fetch`, que não
tem sessão para fechar.
"""

from typing import Any, Dict, List

import aiohttp
import pytest

from KonectySdkPython.lib import http
from KonectySdkPython.lib.client import KonectyClient
from KonectySdkPython.lib.filters import KonectyFilter, KonectyFindParams
from KonectySdkPython.lib.http import request


@pytest.fixture
def opened_sessions(monkeypatch) -> List[aiohttp.ClientSession]:
    """Record every ClientSession the SDK opens, so the test can check they were closed."""
    sessions: List[aiohttp.ClientSession] = []
    original = aiohttp.ClientSession

    def tracking_session(*args: Any, **kwargs: Any) -> aiohttp.ClientSession:
        session = original(*args, **kwargs)
        sessions.append(session)
        return session

    monkeypatch.setattr(http.aiohttp, "ClientSession", tracking_session)
    return sessions


def _still_open(sessions: List[aiohttp.ClientSession]) -> List[aiohttp.ClientSession]:
    return [session for session in sessions if not session.closed]


@pytest.mark.asyncio
async def test_stream_request_closes_session_on_http_error(stub_server, opened_sessions) -> None:
    stub_server.route("GET", "/rest/stream/Product/findStream", {"success": False}, status=400)

    class _Client:
        base_url = stub_server.base_url
        headers: Dict[str, str] = {}

    with pytest.raises(aiohttp.ClientResponseError):
        await request(_Client(), "GET", "/rest/stream/Product/findStream", stream=True)

    assert len(opened_sessions) == 1
    assert _still_open(opened_sessions) == []


@pytest.mark.asyncio
async def test_find_stream_closes_session_on_http_error(stub_server, opened_sessions) -> None:
    stub_server.route("GET", "/rest/stream/Product/findStream", {"success": False}, status=400)
    client = KonectyClient(base_url=stub_server.base_url, token="fake-token")

    with pytest.raises(aiohttp.ClientResponseError):
        await client.find_stream("Product", KonectyFindParams(filter=KonectyFilter()))

    assert len(opened_sessions) == 1
    assert _still_open(opened_sessions) == []


@pytest.mark.asyncio
async def test_stream_request_closes_session_on_connection_error(opened_sessions) -> None:
    class _Client:
        # Porta 1 recusa conexão: o `session.request` falha antes de haver resposta.
        base_url = "http://127.0.0.1:1"
        headers: Dict[str, str] = {}

    with pytest.raises(aiohttp.ClientConnectionError):
        await request(_Client(), "GET", "/rest/stream/Product/findStream", stream=True)

    assert len(opened_sessions) == 1
    assert _still_open(opened_sessions) == []
