"""Tests for the self-service MCP connection status API on KonectyClient.

Mirrors GET /rest/auth/mcp/status and DELETE /rest/auth/mcp/connections/:id (backend:
`src/server/routes/rest/auth/mcpStatusApi.ts`, Konecty core repo).

Parity with the TypeScript SDK (`konecty/konecty-sdk`, branch `feat/mcp-status`):
`src/__test__/api/mcpStatus.test.ts` asserts the same input and output. The TS SDK
returns the `{success: false, errors}` envelope; this SDK raises KonectyAPIError with
the same errors — same wire, per-repo error surface (see `tests/test_pat.py`).
"""

import pytest

from KonectySdkPython.lib.client import KonectyClient
from KonectySdkPython.lib.exceptions import KonectyAPIError
from KonectySdkPython.lib.services.mcp_status import MCP_STATUS_REQUIRES_SESSION_CODE

FAKE_AUTH_ID = "fake-auth-id-not-a-real-token"

STATUS = {
    "access": "write",
    "connections": [
        {
            "id": "grant-1",
            "clientName": "Claude",
            "agent": "claude",
            "scopes": ["read", "write"],
            "resource": "https://tenant.test/mcp",
            "connectedAt": "2026-10-01T10:00:00.000Z",
            "lastActiveAt": "2026-10-28T12:00:00.000Z",
        }
    ],
}


def _client(stub_server) -> KonectyClient:
    return KonectyClient(base_url=stub_server.base_url, token=FAKE_AUTH_ID)


@pytest.mark.asyncio
async def test_get_mcp_status_returns_access_and_connections(stub_server) -> None:
    """
    Equivalent TS test: src/__test__/api/mcpStatus.test.ts — describe('getMcpStatus'),
    it('Should GET /rest/auth/mcp/status with the session header and return access + connections').
    """
    stub_server.route("GET", "/rest/auth/mcp/status", {"success": True, "data": STATUS})

    result = await _client(stub_server).get_mcp_status()

    assert result == {"success": True, "data": STATUS}
    request = stub_server.requests[0]
    assert request["method"] == "GET"
    assert request["raw_path"] == "/rest/auth/mcp/status"
    assert request["authorization"] == FAKE_AUTH_ID


@pytest.mark.asyncio
async def test_get_mcp_status_forwards_requires_session_error(stub_server) -> None:
    """
    Equivalent TS test: src/__test__/api/mcpStatus.test.ts — describe('getMcpStatus'),
    it('Should return the 403 body with the stable code instead of throwing ...').
    """
    errors = [{"message": "session only", "code": "mcp-status-requires-session"}]
    stub_server.route(
        "GET", "/rest/auth/mcp/status", {"success": False, "errors": errors}, status=403
    )

    with pytest.raises(KonectyAPIError) as raised:
        await _client(stub_server).get_mcp_status()

    assert raised.value.args[0] == errors
    assert MCP_STATUS_REQUIRES_SESSION_CODE == "mcp-status-requires-session"


@pytest.mark.asyncio
async def test_revoke_mcp_connection_encodes_id_in_path(stub_server) -> None:
    """
    Equivalent TS test: src/__test__/api/mcpStatus.test.ts — describe('revokeMcpConnection'),
    it('Should DELETE /rest/auth/mcp/connections/:id with the id percent-encoded byte for byte').
    """
    stub_server.route("DELETE", "/rest/auth/mcp/connections/grant 1/x", {"success": True})

    result = await _client(stub_server).revoke_mcp_connection("grant 1/x")

    assert result == {"success": True}
    request = stub_server.requests[0]
    assert request["method"] == "DELETE"
    assert request["raw_path"] == "/rest/auth/mcp/connections/grant%201%2Fx"


@pytest.mark.asyncio
async def test_revoke_mcp_connection_returns_not_found_body(stub_server) -> None:
    """
    Equivalent TS test: src/__test__/api/mcpStatus.test.ts — describe('revokeMcpConnection'),
    it('Should return the 404 body instead of throwing when the connection is unknown').
    """
    stub_server.route(
        "DELETE",
        "/rest/auth/mcp/connections/nao-existe",
        {"success": False, "errors": [{"message": "MCP connection not found"}]},
        status=404,
    )

    with pytest.raises(KonectyAPIError, match="MCP connection not found"):
        await _client(stub_server).revoke_mcp_connection("nao-existe")

    assert stub_server.requests[0]["raw_path"] == "/rest/auth/mcp/connections/nao-existe"


@pytest.mark.asyncio
async def test_revoke_mcp_connection_keeps_encode_uri_component_safe_chars(stub_server) -> None:
    """
    `encodeURIComponent` leaves !*'() unescaped; plain `quote(safe="")` would not.
    TS gives "/rest/auth/mcp/connections/a!b*c'd(e)%20f" for the same input.
    """
    stub_server.route("DELETE", "/rest/auth/mcp/connections/a!b*c'd(e) f", {"success": True})

    await _client(stub_server).revoke_mcp_connection("a!b*c'd(e) f")

    assert stub_server.requests[0]["raw_path"] == "/rest/auth/mcp/connections/a!b*c'd(e)%20f"
