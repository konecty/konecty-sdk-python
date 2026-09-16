"""
Recusa de ordenação acima do teto de página.

Paridade com o SDK TypeScript: `src/__test__/api/sortLimit.test.ts` usa a MESMA
resposta e espera a MESMA saída (exceção dedicada, com `code` legível por
máquina).

Acima do teto o Konecty recusa ordenação arbitrária com HTTP 400 e
`SORT_ABOVE_MAX_PAGE_SIZE` — antes ele trocava o sort por `{_id: 1}` em silêncio
e devolvia 200 com os dados fora de ordem. Os dois SDKs perdiam o corpo do 400:
aqui o `response.raise_for_status()` disparava ANTES de o JSON ser lido, então
nem a mensagem nem o código chegavam a quem chamou.
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


@pytest.mark.asyncio
async def test_find_raises_sort_limit_error_with_code(stub_server) -> None:
    stub_server.route("GET", "/rest/data/Product/find", SORT_REJECTION_BODY, status=400)
    client = KonectyClient(base_url=stub_server.base_url, token="fake-token")

    with pytest.raises(KonectySortLimitError) as excinfo:
        await client.find("Product", KonectyFindParams(filter=KonectyFilter(), limit=5000))

    assert excinfo.value.code == SORT_ABOVE_MAX_PAGE_SIZE
    # A mensagem do servidor diz COMO corrigir a chamada; perdê-la era o pior do bug.
    assert "_id" in str(excinfo.value)
    assert "1000" in str(excinfo.value)


@pytest.mark.asyncio
async def test_sort_limit_error_is_catchable_as_api_error(stub_server) -> None:
    """Quem já tratava KonectyAPIError continua pegando — mesma garantia do Google."""
    stub_server.route("GET", "/rest/data/Product/find", SORT_REJECTION_BODY, status=400)
    client = KonectyClient(base_url=stub_server.base_url, token="fake-token")

    with pytest.raises(KonectyAPIError):
        await client.find("Product", KonectyFindParams(filter=KonectyFilter(), limit=5000))


@pytest.mark.asyncio
async def test_other_errors_stay_generic(stub_server) -> None:
    stub_server.route(
        "GET",
        "/rest/data/Product/find",
        {"success": False, "errors": [{"message": "Some other failure"}]},
        status=400,
    )
    client = KonectyClient(base_url=stub_server.base_url, token="fake-token")

    with pytest.raises(KonectyAPIError) as excinfo:
        await client.find("Product", KonectyFindParams(filter=KonectyFilter(), limit=10))

    assert not isinstance(excinfo.value, KonectySortLimitError)


@pytest.mark.asyncio
async def test_successful_find_is_untouched(stub_server) -> None:
    stub_server.route(
        "GET",
        "/rest/data/Product/find",
        {"success": True, "data": [{"_id": "a"}], "total": 1},
    )
    client = KonectyClient(base_url=stub_server.base_url, token="fake-token")

    data = await client.find("Product", KonectyFindParams(filter=KonectyFilter(), limit=10))

    assert data == [{"_id": "a"}]
