"""Tests for the self-service Personal Access Token (PAT) API on KonectyClient.

Mirrors POST/GET/DELETE /rest/auth/pat (backend: `src/server/routes/rest/auth/patApi.ts`,
Konecty core repo). Asserts URL and JSON body byte-for-byte, same as the other services'
tests in this repo (see `tests/test_auth_google.py`).

Parity with the TypeScript SDK (`konecty/konecty-sdk`, branch `feat/pat-service-accounts`):
`src/__test__/api/pat.test.ts` (`createPat`, `listPats`, `revokePat` describe blocks) asserts
the same input/output as the tests below — same wire body field names (`name`, `expiresAt`).
"""

import pytest

from KonectySdkPython.lib.client import KonectyClient
from KonectySdkPython.lib.exceptions import KonectyAPIError

FAKE_AUTH_ID = "fake-auth-id-not-a-real-token"


def _client(stub_server) -> KonectyClient:
    return KonectyClient(base_url=stub_server.base_url, token=FAKE_AUTH_ID)


@pytest.mark.asyncio
async def test_create_pat_sends_name_only_when_no_expiry(stub_server) -> None:
    """
    Equivalent TS test: src/__test__/api/pat.test.ts:46 — describe('createPat'),
    it('Should omit expiresAt from the body when not given').
    """
    stub_server.route(
        "POST",
        "/rest/auth/pat",
        {"success": True, "data": {"_id": "pat-1", "token": "kpat_fake"}},
    )

    result = await _client(stub_server).create_pat("my token")

    assert result["data"]["_id"] == "pat-1"
    assert result["data"]["token"] == "kpat_fake"
    request = stub_server.requests[0]
    assert request["method"] == "POST"
    assert request["path"] == "/rest/auth/pat"
    assert request["json"] == {"name": "my token"}


@pytest.mark.asyncio
async def test_create_pat_sends_expires_at_when_given(stub_server) -> None:
    """
    Equivalent TS test: src/__test__/api/pat.test.ts:13 — describe('createPat'),
    it('Should POST to /rest/auth/pat with name and expiresAt, and return the
    show-once token').
    """
    stub_server.route(
        "POST",
        "/rest/auth/pat",
        {"success": True, "data": {"_id": "pat-2", "token": "kpat_fake2"}},
    )

    await _client(stub_server).create_pat(
        "expiring token", expires_at="2027-01-01T00:00:00.000Z"
    )

    assert stub_server.requests[0]["json"] == {
        "name": "expiring token",
        "expiresAt": "2027-01-01T00:00:00.000Z",
    }


@pytest.mark.asyncio
async def test_create_pat_raises_on_forbidden_role(stub_server) -> None:
    """
    Equivalent TS test: src/__test__/api/pat.test.ts:66 — describe('createPat'),
    it('Should return the server errors verbatim on a 403 (role not allowed)').
    """
    stub_server.route(
        "POST",
        "/rest/auth/pat",
        {
            "success": False,
            "errors": [{"message": "User role is not allowed to create Personal Access Tokens"}],
        },
        status=403,
    )

    with pytest.raises(KonectyAPIError):
        await _client(stub_server).create_pat("blocked")


@pytest.mark.asyncio
async def test_list_pats_returns_data_without_hashed_token(stub_server) -> None:
    """
    Equivalent TS test: src/__test__/api/pat.test.ts:95 — describe('listPats'),
    it('Should GET /rest/auth/pat and return the list without hashedToken').
    """
    stub_server.route(
        "GET",
        "/rest/auth/pat",
        {
            "success": True,
            "data": [
                {
                    "_id": "pat-1",
                    "name": "my token",
                    "createdAt": "2026-01-01T00:00:00.000Z",
                    "expiresAt": None,
                    "lastUsedAt": None,
                }
            ],
        },
    )

    result = await _client(stub_server).list_pats()

    assert result["data"][0]["_id"] == "pat-1"
    assert "hashedToken" not in result["data"][0]
    request = stub_server.requests[0]
    assert request["method"] == "GET"
    assert request["path"] == "/rest/auth/pat"


@pytest.mark.asyncio
async def test_revoke_pat_builds_path_with_id(stub_server) -> None:
    """
    Equivalent TS test: src/__test__/api/pat.test.ts:135 — describe('revokePat'),
    it('Should DELETE /rest/auth/pat/:id').
    """
    stub_server.route("DELETE", "/rest/auth/pat/pat-1", {"success": True})

    result = await _client(stub_server).revoke_pat("pat-1")

    assert result["success"] is True
    request = stub_server.requests[0]
    assert request["method"] == "DELETE"
    assert request["path"] == "/rest/auth/pat/pat-1"


@pytest.mark.asyncio
async def test_revoke_pat_raises_not_found_for_unknown_id(stub_server) -> None:
    """
    Equivalent TS test: src/__test__/api/pat.test.ts:159 — describe('revokePat'),
    it('Should return the 404 not-found error verbatim when the PAT does not
    belong to the caller').
    """
    stub_server.route(
        "DELETE",
        "/rest/auth/pat/unknown",
        {"success": False, "errors": [{"message": "Personal Access Token not found"}]},
        status=404,
    )

    with pytest.raises(KonectyAPIError):
        await _client(stub_server).revoke_pat("unknown")
