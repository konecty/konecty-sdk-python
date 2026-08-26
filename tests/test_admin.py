"""Tests for the admin credentials/Service Account API on KonectyClient.

Mirrors GET/DELETE /api/admin/pats, DELETE /api/admin/legacy-tokens/:userId/:fingerprint,
and the /api/admin/service-accounts routes (backend: `src/server/routes/api/admin/
credentials.ts` and `src/server/routes/api/admin/serviceAccounts.ts`, Konecty core repo).
Asserts URL (including path-segment interpolation for `:userId`/`:patId`/`:fingerprint`/
`:id`) and JSON body byte-for-byte, same pattern as `tests/test_pat.py`.

Parity note: at the time these tests were written the TypeScript SDK (`konecty/konecty-sdk`)
had not yet implemented the admin domain — no `src/__test__/api/admin.test.ts` exists there.
Per the repo's parity rule (AGENTS.md "SDKs"), once that test lands it must assert the same
input/output as the tests below (same wire body field names: `name`, `username`, `accessMap`,
`expiresAt`; same path shape for the four id-bearing routes).
"""

import pytest

from KonectySdkPython.lib.client import KonectyClient
from KonectySdkPython.lib.exceptions import KonectyAPIError

FAKE_AUTH_ID = "fake-admin-auth-id-not-a-real-token"


def _client(stub_server) -> KonectyClient:
    return KonectyClient(base_url=stub_server.base_url, token=FAKE_AUTH_ID)


@pytest.mark.asyncio
async def test_admin_list_all_pats_returns_pats_and_legacy_tokens(stub_server) -> None:
    stub_server.route(
        "GET",
        "/api/admin/pats",
        {
            "success": True,
            "data": {
                "pats": [{"userId": "user-1", "userName": "Someone", "patId": "pat-1", "name": "my token"}],
                "legacyTokens": [{"userId": "user-2", "userName": "Legacy", "legacy": True, "fingerprint": "abc123"}],
            },
        },
    )

    result = await _client(stub_server).admin_list_all_pats()

    assert result["data"]["pats"][0]["patId"] == "pat-1"
    assert result["data"]["legacyTokens"][0]["fingerprint"] == "abc123"
    request = stub_server.requests[0]
    assert request["method"] == "GET"
    assert request["path"] == "/api/admin/pats"


@pytest.mark.asyncio
async def test_admin_list_all_pats_raises_forbidden_for_non_admin(stub_server) -> None:
    stub_server.route(
        "GET",
        "/api/admin/pats",
        {"success": False, "errors": [{"message": "Admin access required"}]},
        status=403,
    )

    with pytest.raises(KonectyAPIError):
        await _client(stub_server).admin_list_all_pats()


@pytest.mark.asyncio
async def test_admin_revoke_pat_interpolates_user_and_pat_id(stub_server) -> None:
    stub_server.route("DELETE", "/api/admin/pats/user-1/pat-1", {"success": True, "data": {"success": True}})

    result = await _client(stub_server).admin_revoke_pat("user-1", "pat-1")

    assert result["success"] is True
    request = stub_server.requests[0]
    assert request["method"] == "DELETE"
    assert request["path"] == "/api/admin/pats/user-1/pat-1"


@pytest.mark.asyncio
async def test_admin_revoke_pat_raises_not_found(stub_server) -> None:
    stub_server.route(
        "DELETE",
        "/api/admin/pats/user-1/unknown",
        {"success": False, "errors": [{"message": "PAT not found"}]},
        status=404,
    )

    with pytest.raises(KonectyAPIError):
        await _client(stub_server).admin_revoke_pat("user-1", "unknown")


@pytest.mark.asyncio
async def test_admin_revoke_legacy_token_interpolates_user_id_and_fingerprint(
    stub_server,
) -> None:
    stub_server.route(
        "DELETE", "/api/admin/legacy-tokens/user-2/abc123", {"success": True, "data": {"success": True}}
    )

    result = await _client(stub_server).admin_revoke_legacy_token("user-2", "abc123")

    assert result["success"] is True
    request = stub_server.requests[0]
    assert request["method"] == "DELETE"
    assert request["path"] == "/api/admin/legacy-tokens/user-2/abc123"


@pytest.mark.asyncio
async def test_admin_create_service_account_sends_name_username_and_access_map(
    stub_server,
) -> None:
    stub_server.route(
        "POST",
        "/api/admin/service-accounts",
        {
            "success": True,
            "data": {
                "_id": "sa-1",
                "username": "svc-bot",
                "role": {"_id": "role-1", "name": "Service Account"},
                "access": {"defaults": False, "Contact": "ServiceRead"},
            },
        },
        status=201,
    )

    result = await _client(stub_server).admin_create_service_account(
        "Bot", "svc-bot", {"Contact": "read"}
    )

    assert result["data"]["_id"] == "sa-1"
    request = stub_server.requests[0]
    assert request["method"] == "POST"
    assert request["path"] == "/api/admin/service-accounts"
    assert request["json"] == {
        "name": "Bot",
        "username": "svc-bot",
        "accessMap": {"Contact": "read"},
    }


@pytest.mark.asyncio
async def test_admin_create_service_account_defaults_access_map_to_empty_dict(
    stub_server,
) -> None:
    stub_server.route(
        "POST",
        "/api/admin/service-accounts",
        {"success": True, "data": {"_id": "sa-2", "username": "svc-bot-2", "role": {}, "access": {}}},
        status=201,
    )

    await _client(stub_server).admin_create_service_account("Bot 2", "svc-bot-2")

    assert stub_server.requests[0]["json"] == {
        "name": "Bot 2",
        "username": "svc-bot-2",
        "accessMap": {},
    }


@pytest.mark.asyncio
async def test_admin_create_service_account_raises_conflict_on_duplicate_username(
    stub_server,
) -> None:
    stub_server.route(
        "POST",
        "/api/admin/service-accounts",
        {"success": False, "errors": [{"message": "Username already in use"}]},
        status=409,
    )

    with pytest.raises(KonectyAPIError):
        await _client(stub_server).admin_create_service_account("Bot", "taken")


@pytest.mark.asyncio
async def test_admin_list_service_accounts_returns_accounts_with_pats(stub_server) -> None:
    stub_server.route(
        "GET",
        "/api/admin/service-accounts",
        {
            "success": True,
            "data": [
                {
                    "_id": "sa-1",
                    "name": "Bot",
                    "username": "svc-bot",
                    "active": True,
                    "access": {"defaults": False},
                    "pats": [],
                }
            ],
        },
    )

    result = await _client(stub_server).admin_list_service_accounts()

    assert result["data"][0]["username"] == "svc-bot"
    request = stub_server.requests[0]
    assert request["method"] == "GET"
    assert request["path"] == "/api/admin/service-accounts"


@pytest.mark.asyncio
async def test_admin_update_service_account_access_interpolates_id_and_sends_access_map(
    stub_server,
) -> None:
    stub_server.route(
        "PUT",
        "/api/admin/service-accounts/sa-1/access",
        {"success": True, "data": {"_id": "sa-1", "access": {"defaults": False, "Contact": "ServiceReadWrite"}}},
    )

    result = await _client(stub_server).admin_update_service_account_access(
        "sa-1", {"Contact": "readWrite"}
    )

    assert result["data"]["_id"] == "sa-1"
    request = stub_server.requests[0]
    assert request["method"] == "PUT"
    assert request["path"] == "/api/admin/service-accounts/sa-1/access"
    assert request["json"] == {"accessMap": {"Contact": "readWrite"}}


@pytest.mark.asyncio
async def test_admin_update_service_account_access_raises_not_found(stub_server) -> None:
    stub_server.route(
        "PUT",
        "/api/admin/service-accounts/unknown/access",
        {"success": False, "errors": [{"message": "Service account not found"}]},
        status=404,
    )

    with pytest.raises(KonectyAPIError):
        await _client(stub_server).admin_update_service_account_access("unknown", {})


@pytest.mark.asyncio
async def test_admin_create_service_account_pat_sends_name_only_when_no_expiry(
    stub_server,
) -> None:
    stub_server.route(
        "POST",
        "/api/admin/service-accounts/sa-1/pats",
        {"success": True, "data": {"_id": "pat-3", "token": "kpat_svc"}},
        status=201,
    )

    result = await _client(stub_server).admin_create_service_account_pat("sa-1", "svc token")

    assert result["data"]["token"] == "kpat_svc"
    request = stub_server.requests[0]
    assert request["method"] == "POST"
    assert request["path"] == "/api/admin/service-accounts/sa-1/pats"
    assert request["json"] == {"name": "svc token"}


@pytest.mark.asyncio
async def test_admin_create_service_account_pat_sends_expires_at_when_given(
    stub_server,
) -> None:
    stub_server.route(
        "POST",
        "/api/admin/service-accounts/sa-1/pats",
        {"success": True, "data": {"_id": "pat-4", "token": "kpat_svc2"}},
        status=201,
    )

    await _client(stub_server).admin_create_service_account_pat(
        "sa-1", "svc token", expires_at="2027-06-01T00:00:00.000Z"
    )

    assert stub_server.requests[0]["json"] == {
        "name": "svc token",
        "expiresAt": "2027-06-01T00:00:00.000Z",
    }


@pytest.mark.asyncio
async def test_admin_create_service_account_pat_raises_for_non_service_account_target(
    stub_server,
) -> None:
    stub_server.route(
        "POST",
        "/api/admin/service-accounts/human-1/pats",
        {
            "success": False,
            "errors": [
                {
                    "message": "Admin cannot create a Personal Access Token for a human user — target is not a service account (ADM-02)"
                }
            ],
        },
        status=403,
    )

    with pytest.raises(KonectyAPIError):
        await _client(stub_server).admin_create_service_account_pat("human-1", "nope")
