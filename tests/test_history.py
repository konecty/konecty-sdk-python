"""Histórico de alterações de um registro: GET /rest/data/{module}/{id}/history.

Backend: `historyFind` em `src/imports/data/data.js` (repo konecty/Konecty). A rota nega
o histórico com `{success: false, errors}` e HTTP 200: FORBIDDEN sem permissão de leitura
e NOT_FOUND com o registro fora do `readFilter` do perfil (konecty/Konecty#892, #893).

Paridade com o SDK TypeScript (`konecty/konecty-sdk`): `src/__test__/api/KonectyClient.test.ts`
("should return module history", "should propagate success:false from history", "should keep
the error code from a history 4xx body") usa a mesma entrada. O TS devolve o envelope
`{success: false, errors}`; este SDK lança KonectyAPIError com os mesmos `errors` — mesmo
fio, superfície de erro de cada repo (ver `tests/test_mcp_status.py`).
"""

import pytest

from KonectySdkPython.lib.client import KonectyClient
from KonectySdkPython.lib.exceptions import KonectyAPIError

HISTORY_PATH = "/rest/data/Product/productId/history"

NOT_FOUND_ERRORS = [{"message": "[Product] Record not found", "code": "NOT_FOUND"}]
FORBIDDEN_ERRORS = [
    {
        "message": "[Product] You don't have permission to read records",
        "code": "FORBIDDEN",
    }
]


def _client(stub_server) -> KonectyClient:
    return KonectyClient(base_url=stub_server.base_url, token="fake-token")


@pytest.mark.asyncio
async def test_get_history_returns_records(stub_server) -> None:
    record = {"_id": 167604757100001, "dataId": "productId", "type": "update"}
    stub_server.route("GET", HISTORY_PATH, {"success": True, "data": [record]})

    result = await _client(stub_server).get_history("Product", "productId")

    assert result == [record]
    request = stub_server.requests[0]
    assert request["raw_path"] == HISTORY_PATH
    assert request["authorization"] == "fake-token"


@pytest.mark.asyncio
async def test_get_history_raises_on_success_false_with_http_200(stub_server) -> None:
    stub_server.route(
        "GET", HISTORY_PATH, {"success": False, "errors": NOT_FOUND_ERRORS}
    )

    with pytest.raises(KonectyAPIError) as excinfo:
        await _client(stub_server).get_history("Product", "productId")

    assert excinfo.value.args[0] == NOT_FOUND_ERRORS


@pytest.mark.asyncio
async def test_get_history_keeps_error_code_from_4xx_body(stub_server) -> None:
    stub_server.route(
        "GET", HISTORY_PATH, {"success": False, "errors": FORBIDDEN_ERRORS}, status=403
    )

    with pytest.raises(KonectyAPIError) as excinfo:
        await _client(stub_server).get_history("Product", "productId")

    assert excinfo.value.args[0] == FORBIDDEN_ERRORS
