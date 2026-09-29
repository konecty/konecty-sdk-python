"""
Busca sem contagem total (`get_total=False`).

Paridade com o SDK TypeScript: `src/__test__/api/findGetTotal.test.ts` usa a
MESMA entrada (filtro `{match: 'and', conditions: [], filters: []}`, `limit` 10),
as MESMAS respostas e espera a MESMA saída.

Com `getTotal=false` o Konecty não conta os registros e a resposta vem sem
`total`. A opção só vai para a rede quando desligada: com o padrão a URL continua
idêntica à de antes, byte a byte.

Sobre a comparação de query string entre os SDKs: o valor de `filter` já é
codificado de forma diferente por cada linguagem (`json.dumps` com espaços + yarl
aqui, JSON sem espaços + URLSearchParams lá), divergência anterior a esta opção e
inócua porque o servidor faz parse do JSON. Por isso o que é comparado entre os
dois lados é o conjunto de parâmetros decodificados (com `filter` comparado como
JSON) e o trecho cru `&getTotal=false` no fim da query.
"""

import asyncio
import json

import pytest

from KonectySdkPython.lib.client import KonectyClient
from KonectySdkPython.lib.filters import KonectyFilter, KonectyFindParams

FILTER = {"match": "and", "conditions": [], "filters": []}
# Query que o `find` monta hoje para a entrada acima, sem a opção.
QUERY_TODAY = (
    "filter=%7B%22match%22:+%22and%22,+%22conditions%22:+%5B%5D,+%22filters%22:+%5B%5D%7D"
    "&limit=10"
)

BODY_WITHOUT_TOTAL = {"success": True, "data": [{"_id": "a"}]}
BODY_WITH_TOTAL = {"success": True, "data": [{"_id": "a"}], "total": 1}


def _params() -> KonectyFindParams:
    return KonectyFindParams(filter=KonectyFilter(), limit=10)


def _raw_query(stub_server) -> str:
    raw_path = stub_server.requests[-1]["raw_path"]
    return raw_path.split("?", 1)[1] if "?" in raw_path else ""


def _decoded(stub_server) -> dict:
    query = dict(stub_server.requests[-1]["query"])
    query["filter"] = json.loads(query["filter"])
    return query


@pytest.mark.asyncio
async def test_get_total_false_sends_flag_and_accepts_body_without_total(
    stub_server,
) -> None:
    stub_server.route("GET", "/rest/data/Product/find", BODY_WITHOUT_TOTAL)
    client = KonectyClient(base_url=stub_server.base_url, token="fake-token")

    data = await client.find("Product", _params(), get_total=False)

    raw = _raw_query(stub_server)
    assert raw.endswith("&getTotal=false")
    assert raw.count("getTotal=") == 1
    assert _decoded(stub_server) == {
        "filter": FILTER,
        "limit": "10",
        "getTotal": "false",
    }
    assert data == [{"_id": "a"}]


@pytest.mark.asyncio
async def test_default_keeps_today_query(stub_server) -> None:
    stub_server.route("GET", "/rest/data/Product/find", BODY_WITH_TOTAL)
    client = KonectyClient(base_url=stub_server.base_url, token="fake-token")

    data = await client.find("Product", _params())

    assert _raw_query(stub_server) == QUERY_TODAY
    assert _decoded(stub_server) == {"filter": FILTER, "limit": "10"}
    assert data == [{"_id": "a"}]


@pytest.mark.asyncio
async def test_get_total_true_sends_nothing(stub_server) -> None:
    stub_server.route("GET", "/rest/data/Product/find", BODY_WITH_TOTAL)
    client = KonectyClient(base_url=stub_server.base_url, token="fake-token")

    await client.find("Product", _params(), get_total=True)

    assert _raw_query(stub_server) == QUERY_TODAY


@pytest.mark.asyncio
async def test_find_sync_get_total_false(stub_server) -> None:
    stub_server.route("GET", "/rest/data/Product/find", BODY_WITHOUT_TOTAL)
    client = KonectyClient(base_url=stub_server.base_url, token="fake-token")

    # `find_sync` bloqueia; roda em thread para o stub (no loop) poder responder.
    data = await asyncio.to_thread(client.find_sync, "Product", _params(), False)

    assert _raw_query(stub_server).endswith("&getTotal=false")
    assert _decoded(stub_server) == {
        "filter": FILTER,
        "limit": "10",
        "getTotal": "false",
    }
    assert data == [{"_id": "a"}]


@pytest.mark.asyncio
async def test_find_sync_default_sends_no_flag(stub_server) -> None:
    stub_server.route("GET", "/rest/data/Product/find", BODY_WITH_TOTAL)
    client = KonectyClient(base_url=stub_server.base_url, token="fake-token")

    await asyncio.to_thread(client.find_sync, "Product", _params())

    assert "getTotal" not in stub_server.requests[-1]["query"]
