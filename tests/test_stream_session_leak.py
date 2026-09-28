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

from typing import Any, List

import aiohttp
import pytest
from aiohttp import web

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


def _assert_single_session_closed(sessions: List[aiohttp.ClientSession]) -> None:
    assert len(sessions) == 1
    assert _still_open(sessions) == []


@pytest.mark.asyncio
async def test_stream_request_closes_session_on_http_error(stub_server, opened_sessions) -> None:
    stub_server.route("GET", "/rest/stream/Product/findStream", {"success": False}, status=400)
    client = KonectyClient(base_url=stub_server.base_url, token="fake-token")

    with pytest.raises(aiohttp.ClientResponseError):
        await request(client, "GET", "/rest/stream/Product/findStream", stream=True)

    _assert_single_session_closed(opened_sessions)


@pytest.mark.asyncio
async def test_find_stream_closes_session_on_http_error(stub_server, opened_sessions) -> None:
    stub_server.route("GET", "/rest/stream/Product/findStream", {"success": False}, status=400)
    client = KonectyClient(base_url=stub_server.base_url, token="fake-token")

    with pytest.raises(aiohttp.ClientResponseError):
        await client.find_stream("Product", KonectyFindParams(filter=KonectyFilter()))

    _assert_single_session_closed(opened_sessions)


@pytest.mark.asyncio
async def test_stream_request_closes_session_on_connection_error(opened_sessions) -> None:
    # Porta 1 recusa conexão: o `session.request` falha antes de haver resposta.
    client = KonectyClient(base_url="http://127.0.0.1:1", token="fake-token")

    with pytest.raises(aiohttp.ClientConnectionError):
        await request(client, "GET", "/rest/stream/Product/findStream", stream=True)

    _assert_single_session_closed(opened_sessions)


@pytest.mark.asyncio
async def test_find_stream_keeps_session_open_until_stream_is_consumed(
    stub_server, opened_sessions
) -> None:
    # No caminho feliz o `StreamResponse` é o dono da sessão: fechá-la antes (num `finally`, por
    # exemplo) cortaria o stream antes de quem chamou ler o corpo.
    ndjson = b'{"_id": "1", "code": 1}\n{"_id": "2", "code": 2}\n'
    stub_server.route(
        "GET",
        "/rest/stream/Product/findStream",
        web.Response(body=ndjson, content_type="application/x-ndjson"),
    )
    client = KonectyClient(base_url=stub_server.base_url, token="fake-token")

    result = await client.find_stream("Product", KonectyFindParams(filter=KonectyFilter()))

    assert len(opened_sessions) == 1
    assert _still_open(opened_sessions) == opened_sessions

    records = [record async for record in result.stream]

    assert records == [{"_id": "1", "code": 1}, {"_id": "2", "code": 2}]
    assert _still_open(opened_sessions) == []
