"""
Todo 400 com corpo chega legível — não só o `find`.

O PR #8 corrigiu a ordem "corpo antes do status" em `find` e `find_sync`, mas
`lookup`, `find_by_id` e `count_documents` ficaram como estavam: chamavam
`response.raise_for_status()` ANTES de ler o JSON, então o envelope do Konecty
(`{success: false, errors: [{message, code}]}`) era descartado e o chamador
recebia `aiohttp.ClientResponseError` — sem mensagem, sem código e sem a saída
que a mensagem do servidor indica.

O defeito nunca foi específico do sort: vale para QUALQUER 400 com corpo. O
`SORT_ABOVE_MAX_PAGE_SIZE` só foi o primeiro a expô-lo, e os três métodos abaixo
aceitam `sort`/`limit`, então alcançam exatamente a mesma recusa.

Paridade com o SDK TypeScript: `src/__test__/api/sortLimit.test.ts` já cobre o
equivalente lá — o `Client.ts` do TS lê o corpo num ponto só, então não tem o
recorte por método que este arquivo precisa cobrir.
"""

import pytest

from KonectySdkPython.lib.client import KonectyClient
from KonectySdkPython.lib.exceptions import (
    SORT_ABOVE_MAX_PAGE_SIZE,
    KonectyAPIError,
    KonectySortLimitError,
)
from KonectySdkPython.lib.filters import KonectyFilter, KonectyFindParams

SORT_REJECTION_MESSAGE = (
    "Sorting by [name] is not supported above 1000 records (requested limit: 5000). "
    "Sort by _id (ascending or descending) and paginate with an _id range filter, "
    "or request at most 1000 records."
)

SORT_REJECTION_BODY = {
    "success": False,
    "errors": [{"message": SORT_REJECTION_MESSAGE, "code": SORT_ABOVE_MAX_PAGE_SIZE}],
}

# Um 400 qualquer, sem `code`: prova que o conserto é da leitura do corpo e não
# de um tratamento especial do sort.
GENERIC_REJECTION_BODY = {
    "success": False,
    "errors": [{"message": "Field [nonexistent] does not exists at [Product]"}],
}


@pytest.mark.asyncio
async def test_lookup_surfaces_sort_rejection_with_code(stub_server) -> None:
    stub_server.route(
        "GET", "/rest/data/Product/lookup/contact", SORT_REJECTION_BODY, status=400
    )
    client = KonectyClient(base_url=stub_server.base_url, token="fake-token")

    with pytest.raises(KonectySortLimitError) as excinfo:
        await client.lookup(
            "Product", "contact", KonectyFindParams(filter=KonectyFilter(), limit=5000)
        )

    assert excinfo.value.code == SORT_ABOVE_MAX_PAGE_SIZE
    assert "_id" in str(excinfo.value)


@pytest.mark.asyncio
async def test_lookup_surfaces_generic_error_message(stub_server) -> None:
    stub_server.route(
        "GET", "/rest/data/Product/lookup/contact", GENERIC_REJECTION_BODY, status=400
    )
    client = KonectyClient(base_url=stub_server.base_url, token="fake-token")

    with pytest.raises(KonectyAPIError) as excinfo:
        await client.lookup(
            "Product", "contact", KonectyFindParams(filter=KonectyFilter())
        )

    assert "nonexistent" in str(excinfo.value)


@pytest.mark.asyncio
async def test_find_by_id_surfaces_error_body(stub_server) -> None:
    stub_server.route(
        "GET", "/rest/data/Product/abc123", GENERIC_REJECTION_BODY, status=400
    )
    client = KonectyClient(base_url=stub_server.base_url, token="fake-token")

    with pytest.raises(KonectyAPIError) as excinfo:
        await client.find_by_id("Product", "abc123")

    assert "nonexistent" in str(excinfo.value)


@pytest.mark.asyncio
async def test_count_documents_surfaces_sort_rejection_with_code(stub_server) -> None:
    stub_server.route("GET", "/rest/data/Product/find", SORT_REJECTION_BODY, status=400)
    client = KonectyClient(base_url=stub_server.base_url, token="fake-token")

    with pytest.raises(KonectySortLimitError) as excinfo:
        await client.count_documents("Product", KonectyFilter())

    assert excinfo.value.code == SORT_ABOVE_MAX_PAGE_SIZE


@pytest.mark.asyncio
async def test_non_json_body_still_raises_by_status(stub_server) -> None:
    """
    Regressão: corpo não-JSON (proxy, gateway, HTML de erro) não pode virar
    `AttributeError` na tentativa de ler `.get`. Cai no tratamento por status,
    como o `find` já faz.
    """
    stub_server.route("GET", "/rest/data/Product/abc123", "<html>502</html>", status=502)
    client = KonectyClient(base_url=stub_server.base_url, token="fake-token")

    with pytest.raises(Exception) as excinfo:
        await client.find_by_id("Product", "abc123")

    assert not isinstance(excinfo.value, AttributeError)


@pytest.mark.asyncio
async def test_success_paths_unchanged(stub_server) -> None:
    """Os três métodos seguem devolvendo dado em 200 — o fix é só do caminho de erro."""
    stub_server.route(
        "GET",
        "/rest/data/Product/lookup/contact",
        {"success": True, "data": [{"_id": "1"}]},
    )
    stub_server.route(
        "GET", "/rest/data/Product/abc123", {"success": True, "data": [{"_id": "abc123"}]}
    )
    stub_server.route(
        "GET", "/rest/data/Product/find", {"success": True, "data": [], "total": 42}
    )
    client = KonectyClient(base_url=stub_server.base_url, token="fake-token")

    assert await client.lookup(
        "Product", "contact", KonectyFindParams(filter=KonectyFilter())
    ) == [{"_id": "1"}]
    assert await client.find_by_id("Product", "abc123") == {"_id": "abc123"}
    assert await client.count_documents("Product", KonectyFilter()) == 42
