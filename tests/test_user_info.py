"""Tests for KonectyClient.info (GET /rest/auth/info).

Backend: `src/imports/auth/info/index.ts` (Konecty core repo). `user.redirectURL` (string or
null) is part of the payload since konecty/Konecty#426; the new UI takes the user there when the
interface opens (konecty/Konecty#759).

Parity with the TypeScript SDK (`konecty/konecty-sdk`): `src/__test__/api/info.test.ts`
(describe 'Konecty User Infos — redirectURL') asserts the same input and the same output as
`test_info_exposes_redirect_url`; 'Should return false to not logged user' and 'Should still
short-circuit in Node, where there is no ambient cookie' match the other two tests.
"""

import pytest
from aiohttp import web

from KonectySdkPython.lib.client import KonectyClient

FAKE_AUTH_ID = "fake-auth-id-not-a-real-token"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "wire, expected",
    [("/ui/Contact/view/abc123", "/ui/Contact/view/abc123"), (None, None)],
)
async def test_info_exposes_redirect_url(stub_server, wire, expected) -> None:
    stub_server.route(
        "GET",
        "/rest/auth/info",
        {"logged": True, "user": {"_id": "user-1", "name": "Ana", "redirectURL": wire}},
    )

    result = await KonectyClient(base_url=stub_server.base_url, token=FAKE_AUTH_ID).info()

    assert result["logged"] is True
    assert "redirectURL" in result["user"]
    assert result["user"]["redirectURL"] == expected
    request = stub_server.requests[0]
    assert request["method"] == "GET"
    assert request["path"] == "/rest/auth/info"
    assert request["authorization"] == FAKE_AUTH_ID


@pytest.mark.asyncio
async def test_info_returns_not_logged_on_401_without_json(stub_server) -> None:
    stub_server.route("GET", "/rest/auth/info", web.Response(status=401, text=""))

    result = await KonectyClient(base_url=stub_server.base_url, token=FAKE_AUTH_ID).info()

    assert result == {"logged": False}


@pytest.mark.asyncio
async def test_info_without_token_does_not_ask_the_server(stub_server) -> None:
    result = await KonectyClient(base_url=stub_server.base_url).info()

    assert result == {"logged": False}
    assert stub_server.requests == []
