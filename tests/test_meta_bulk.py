"""Tests for `apply_meta_bulk` (POST /api/document) and `capabilities` on `create_service_account`.

Backend: `src/server/routes/api/document/index.ts` and `src/imports/meta/applyBulk.ts` in the Konecty
core repo (MBD-06..08). The route answers errors in four shapes (``{errors}``, ``{error}``, Fastify's
413 body and plain text); every case below pins how each one reaches the caller.

Parity: `src/__test__/api/adminMetaBulk.test.ts` in `konecty/konecty-sdk` runs the same table, same
input and same expected output, case by case (``CASE`` names match).
"""

import socket
from typing import Any, Dict

import pytest
from aiohttp import web

from KonectySdkPython.lib.client import KonectyClient
from KonectySdkPython.lib.exceptions import KonectyAPIError, KonectyMetaBulkError

FAKE_AUTH_ID = "fake-admin-auth-id-not-a-real-token"
ITEM: Dict[str, Any] = {"_id": "Product", "type": "document", "name": "Product"}


def _client(stub_server) -> KonectyClient:
    return KonectyClient(base_url=stub_server.base_url, token=FAKE_AUTH_ID)


@pytest.mark.asyncio
async def test_dry_run_sends_only_given_options_and_returns_plan(stub_server) -> None:
    """CASE dry-run: corpo só com items + dryRun; devolve o corpo da rota sem envelope."""
    plan = {"created": ["Product"], "updated": [], "unchanged": 0, "hooksRemoved": {}}
    stub_server.route(
        "POST",
        "/api/document",
        {"applied": 0, "created": 0, "updated": 0, "deleted": 0, "warnings": [], "preservedHooks": {}, "plan": plan},
    )

    result = await _client(stub_server).apply_meta_bulk([ITEM], dry_run=True)

    assert result["plan"] == plan
    assert result["applied"] == 0
    request = stub_server.requests[0]
    assert request["method"] == "POST"
    assert request["path"] == "/api/document"
    assert request["json"] == {"items": [ITEM], "dryRun": True}
    assert request["authorization"] == FAKE_AUTH_ID


@pytest.mark.asyncio
async def test_options_map_to_camel_case_body(stub_server) -> None:
    """CASE options: delete_removed, hook_mode e namespace_patch viram deleteRemoved, hookMode e namespacePatch."""
    stub_server.route(
        "POST",
        "/api/document",
        {"applied": 1, "created": 0, "updated": 1, "deleted": 0, "warnings": [], "preservedHooks": {}},
    )
    patch = {"metadataVersion": {"cliente": "auxiliadora", "versaoCliente": "v1.2.0"}}

    result = await _client(stub_server).apply_meta_bulk(
        [ITEM], delete_removed=False, hook_mode="replace", namespace_patch=patch
    )

    assert result["updated"] == 1
    assert "plan" not in result
    assert stub_server.requests[0]["json"] == {
        "items": [ITEM],
        "deleteRemoved": False,
        "hookMode": "replace",
        "namespacePatch": patch,
    }


@pytest.mark.asyncio
async def test_400_errors_list_is_kept(stub_server) -> None:
    """CASE 400-errors: `{errors: [...]}` chega como está."""
    errors = [{"index": 0, "path": "name", "message": "Required"}]
    stub_server.route("POST", "/api/document", {"errors": errors}, status=400)

    with pytest.raises(KonectyMetaBulkError) as caught:
        await _client(stub_server).apply_meta_bulk([ITEM])

    assert caught.value.status == 400
    assert caught.value.errors == errors


@pytest.mark.asyncio
async def test_400_error_string_becomes_list(stub_server) -> None:
    """CASE 400-error: `{error: '...'}` vira `[{message}]`."""
    stub_server.route("POST", "/api/document", {"error": "dryRun must be a boolean"}, status=400)

    with pytest.raises(KonectyMetaBulkError) as caught:
        await _client(stub_server).apply_meta_bulk([ITEM])

    assert caught.value.status == 400
    assert caught.value.errors == [{"message": "dryRun must be a boolean"}]
    assert str(caught.value) == "dryRun must be a boolean"


@pytest.mark.asyncio
async def test_403_plain_text(stub_server) -> None:
    """CASE 403-text: `Forbidden` em texto puro, com espaço em volta, vira `[{message: 'Forbidden'}]`."""
    stub_server.route("POST", "/api/document", web.Response(text="  Forbidden\n", status=403))

    with pytest.raises(KonectyMetaBulkError) as caught:
        await _client(stub_server).apply_meta_bulk([ITEM])

    assert caught.value.status == 403
    assert caught.value.errors == [{"message": "Forbidden"}]


@pytest.mark.asyncio
async def test_413_fastify_body_keeps_message_and_code(stub_server) -> None:
    """CASE 413-fastify: o corpo do Fastify traz `error` e `message`; vale `message` com `code`."""
    stub_server.route(
        "POST",
        "/api/document",
        {
            "statusCode": 413,
            "code": "FST_ERR_CTP_BODY_TOO_LARGE",
            "error": "Payload Too Large",
            "message": "Request body is too large",
        },
        status=413,
    )

    with pytest.raises(KonectyMetaBulkError) as caught:
        await _client(stub_server).apply_meta_bulk([ITEM])

    assert caught.value.status == 413
    assert caught.value.errors == [{"message": "Request body is too large", "code": "FST_ERR_CTP_BODY_TOO_LARGE"}]


@pytest.mark.asyncio
async def test_500_plain_text_is_a_konecty_api_error(stub_server) -> None:
    """CASE 500-text: texto puro no 5xx; a exceção também é um KonectyAPIError."""
    stub_server.route("POST", "/api/document", web.Response(text="Internal server error", status=500))

    with pytest.raises(KonectyAPIError) as caught:
        await _client(stub_server).apply_meta_bulk([ITEM])

    assert isinstance(caught.value, KonectyMetaBulkError)
    assert caught.value.status == 500
    assert caught.value.errors == [{"message": "Internal server error"}]


@pytest.mark.asyncio
async def test_empty_error_body_uses_status(stub_server) -> None:
    """CASE empty: sem corpo, a mensagem é o status."""
    stub_server.route("POST", "/api/document", web.Response(text="", status=502))

    with pytest.raises(KonectyMetaBulkError) as caught:
        await _client(stub_server).apply_meta_bulk([ITEM])

    assert caught.value.status == 502
    assert caught.value.errors == [{"message": "502"}]


@pytest.mark.asyncio
async def test_create_service_account_sends_capabilities(stub_server) -> None:
    """CASE sa-capabilities: `capabilities` vai no corpo quando informado."""
    stub_server.route(
        "POST",
        "/api/admin/service-accounts",
        {"success": True, "data": {"_id": "sa-1", "username": "metas-aux", "role": {"_id": "r", "name": "r"}, "access": {}}},
        status=201,
    )

    await _client(stub_server).create_service_account("Metas Aux", "metas-aux", capabilities=["metaApply"])

    assert stub_server.requests[0]["json"] == {
        "name": "Metas Aux",
        "username": "metas-aux",
        "capabilities": ["metaApply"],
    }


@pytest.mark.asyncio
async def test_create_service_account_omits_capabilities_when_not_given(stub_server) -> None:
    """CASE sa-no-capabilities: sem `capabilities`, a chave não vai no corpo."""
    stub_server.route(
        "POST",
        "/api/admin/service-accounts",
        {"success": True, "data": {"_id": "sa-1", "username": "x", "role": {"_id": "r", "name": "r"}, "access": {}}},
        status=201,
    )

    await _client(stub_server).create_service_account("X", "x")

    assert "capabilities" not in stub_server.requests[0]["json"]


@pytest.mark.asyncio
async def test_401_plain_text(stub_server) -> None:
    """CASE 401-text: `Unauthorized` em texto puro."""
    stub_server.route("POST", "/api/document", web.Response(text="Unauthorized", status=401))

    with pytest.raises(KonectyMetaBulkError) as caught:
        await _client(stub_server).apply_meta_bulk([ITEM])

    assert caught.value.status == 401
    assert caught.value.errors == [{"message": "Unauthorized"}]


@pytest.mark.asyncio
async def test_network_error_has_status_zero() -> None:
    """CASE network: sem resposta (conexão recusada), a exceção é a mesma, com status 0."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    client = KonectyClient(base_url=f"http://127.0.0.1:{port}", token=FAKE_AUTH_ID)

    with pytest.raises(KonectyMetaBulkError) as caught:
        await client.apply_meta_bulk([ITEM])

    assert caught.value.status == 0
    assert caught.value.errors[0]["message"] != ""
