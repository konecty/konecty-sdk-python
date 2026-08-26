"""Tests for the admin credentials/Service Account API on KonectyClient.

Mirrors GET/DELETE /api/admin/pats, DELETE /api/admin/legacy-tokens/:userId/:fingerprint,
and the /api/admin/service-accounts routes (backend: `src/server/routes/api/admin/
credentials.ts` and `src/server/routes/api/admin/serviceAccounts.ts`, Konecty core repo).
Asserts URL (including path-segment interpolation for `:userId`/`:patId`/`:fingerprint`/
`:id`) and JSON body byte-for-byte, same pattern as `tests/test_pat.py`.

Naming: every method here matches its `docs/features.json` sdk.python id with the
`admin.` prefix dropped (`list_all_pats`, `revoke_legacy_token`, `create_service_account`,
`list_service_accounts`, `update_service_account_access`, `create_service_account_pat`),
same convention as the self-service PAT methods in `tests/test_pat.py`. The one exception
is `revoke_user_pat`: flattening `admin.revoke_pat` straight to `revoke_pat` would collide
with the self-service `KonectyClient.revoke_pat` (different resource — `user_id` + `pat_id`
here vs. a caller-scoped `pat_id` there) — so it keeps a disambiguating name, per the
cross-SDK parity decision.

Parity with the TypeScript SDK (`konecty/konecty-sdk`, branch `feat/pat-service-accounts`):
- `src/__test__/api/pat.test.ts` — self-service PAT (see `tests/test_pat.py` instead).
- `src/__test__/api/adminCredentials.test.ts` — `listAllPats`, `revokeLegacyToken`, and the
  admin PAT-revoke describe block (see note below).
- `src/__test__/api/adminServiceAccounts.test.ts` — `createServiceAccount`,
  `listServiceAccounts`, `updateServiceAccountAccess`, `createServiceAccountPat`.

Cross-SDK naming: `docs/features.json` maps `admin.pats.revoke` to
`admin.revokeUserPat` / `admin.revoke_user_pat`, and both SDKs now implement it —
this file's `revoke_user_pat` and the TS SDK's `revokeUserPat` (konecty-sdk branch
feat/pat-service-accounts, `describe('revokeUserPat')` in
`src/__test__/api/adminCredentials.test.ts`) — closing the divergence flagged
during the parallel implementation.
"""

import pytest

from KonectySdkPython.lib.client import KonectyClient
from KonectySdkPython.lib.exceptions import KonectyAPIError

FAKE_AUTH_ID = "fake-admin-auth-id-not-a-real-token"


def _client(stub_server) -> KonectyClient:
    return KonectyClient(base_url=stub_server.base_url, token=FAKE_AUTH_ID)


@pytest.mark.asyncio
async def test_list_all_pats_returns_pats_and_legacy_tokens(stub_server) -> None:
    """Equivalent TS test: src/__test__/api/adminCredentials.test.ts:12 (describe('listAllPats', ...))."""
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

    result = await _client(stub_server).list_all_pats()

    assert result["data"]["pats"][0]["patId"] == "pat-1"
    assert result["data"]["legacyTokens"][0]["fingerprint"] == "abc123"
    request = stub_server.requests[0]
    assert request["method"] == "GET"
    assert request["path"] == "/api/admin/pats"


@pytest.mark.asyncio
async def test_list_all_pats_raises_forbidden_for_non_admin(stub_server) -> None:
    """Equivalent TS test: src/__test__/api/adminCredentials.test.ts:48 (403 'Admin access required')."""
    stub_server.route(
        "GET",
        "/api/admin/pats",
        {"success": False, "errors": [{"message": "Admin access required"}]},
        status=403,
    )

    with pytest.raises(KonectyAPIError):
        await _client(stub_server).list_all_pats()


@pytest.mark.asyncio
async def test_revoke_user_pat_interpolates_user_and_pat_id(stub_server) -> None:
    """
    Equivalent TS test: src/__test__/api/adminCredentials.test.ts —
    describe('revokeUserPat').
    """
    stub_server.route("DELETE", "/api/admin/pats/user-1/pat-1", {"success": True, "data": {"success": True}})

    result = await _client(stub_server).revoke_user_pat("user-1", "pat-1")

    assert result["success"] is True
    request = stub_server.requests[0]
    assert request["method"] == "DELETE"
    assert request["path"] == "/api/admin/pats/user-1/pat-1"


@pytest.mark.asyncio
async def test_revoke_user_pat_raises_not_found(stub_server) -> None:
    """Equivalent TS test: src/__test__/api/adminCredentials.test.ts:91 (404 'PAT not found')."""
    stub_server.route(
        "DELETE",
        "/api/admin/pats/user-1/unknown",
        {"success": False, "errors": [{"message": "PAT not found"}]},
        status=404,
    )

    with pytest.raises(KonectyAPIError):
        await _client(stub_server).revoke_user_pat("user-1", "unknown")


@pytest.mark.asyncio
async def test_revoke_legacy_token_interpolates_user_id_and_fingerprint(
    stub_server,
) -> None:
    """Equivalent TS test: src/__test__/api/adminCredentials.test.ts:109 (describe('revokeLegacyToken', ...))."""
    stub_server.route(
        "DELETE", "/api/admin/legacy-tokens/user-2/abc123", {"success": True, "data": {"success": True}}
    )

    result = await _client(stub_server).revoke_legacy_token("user-2", "abc123")

    assert result["success"] is True
    request = stub_server.requests[0]
    assert request["method"] == "DELETE"
    assert request["path"] == "/api/admin/legacy-tokens/user-2/abc123"


@pytest.mark.asyncio
async def test_create_service_account_sends_name_username_and_access_map(
    stub_server,
) -> None:
    """Equivalent TS test: src/__test__/api/adminServiceAccounts.test.ts:12 (describe('createServiceAccount', ...))."""
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

    result = await _client(stub_server).create_service_account(
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
async def test_create_service_account_defaults_access_map_to_empty_dict(
    stub_server,
) -> None:
    stub_server.route(
        "POST",
        "/api/admin/service-accounts",
        {"success": True, "data": {"_id": "sa-2", "username": "svc-bot-2", "role": {}, "access": {}}},
        status=201,
    )

    await _client(stub_server).create_service_account("Bot 2", "svc-bot-2")

    assert stub_server.requests[0]["json"] == {
        "name": "Bot 2",
        "username": "svc-bot-2",
        "accessMap": {},
    }


@pytest.mark.asyncio
async def test_create_service_account_raises_conflict_on_duplicate_username(
    stub_server,
) -> None:
    """Equivalent TS test: src/__test__/api/adminServiceAccounts.test.ts:51 (409 'Username already in use')."""
    stub_server.route(
        "POST",
        "/api/admin/service-accounts",
        {"success": False, "errors": [{"message": "Username already in use"}]},
        status=409,
    )

    with pytest.raises(KonectyAPIError):
        await _client(stub_server).create_service_account("Bot", "taken")


@pytest.mark.asyncio
async def test_list_service_accounts_returns_accounts_with_pats(stub_server) -> None:
    """Equivalent TS test: src/__test__/api/adminServiceAccounts.test.ts:69 (describe('listServiceAccounts', ...))."""
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

    result = await _client(stub_server).list_service_accounts()

    assert result["data"][0]["username"] == "svc-bot"
    request = stub_server.requests[0]
    assert request["method"] == "GET"
    assert request["path"] == "/api/admin/service-accounts"


@pytest.mark.asyncio
async def test_update_service_account_access_interpolates_id_and_sends_access_map(
    stub_server,
) -> None:
    """Equivalent TS test: src/__test__/api/adminServiceAccounts.test.ts:109 (describe('updateServiceAccountAccess', ...))."""
    stub_server.route(
        "PUT",
        "/api/admin/service-accounts/sa-1/access",
        {"success": True, "data": {"_id": "sa-1", "access": {"defaults": False, "Contact": "ServiceReadWrite"}}},
    )

    result = await _client(stub_server).update_service_account_access(
        "sa-1", {"Contact": "readWrite"}
    )

    assert result["data"]["_id"] == "sa-1"
    request = stub_server.requests[0]
    assert request["method"] == "PUT"
    assert request["path"] == "/api/admin/service-accounts/sa-1/access"
    assert request["json"] == {"accessMap": {"Contact": "readWrite"}}


@pytest.mark.asyncio
async def test_update_service_account_access_raises_not_found(stub_server) -> None:
    """Equivalent TS test: src/__test__/api/adminServiceAccounts.test.ts:140 (404 'Service account not found')."""
    stub_server.route(
        "PUT",
        "/api/admin/service-accounts/unknown/access",
        {"success": False, "errors": [{"message": "Service account not found"}]},
        status=404,
    )

    with pytest.raises(KonectyAPIError):
        await _client(stub_server).update_service_account_access("unknown", {})


@pytest.mark.asyncio
async def test_create_service_account_pat_sends_name_only_when_no_expiry(
    stub_server,
) -> None:
    """Equivalent TS test: src/__test__/api/adminServiceAccounts.test.ts:158 (describe('createServiceAccountPat', ...))."""
    stub_server.route(
        "POST",
        "/api/admin/service-accounts/sa-1/pats",
        {"success": True, "data": {"_id": "pat-3", "token": "kpat_svc"}},
        status=201,
    )

    result = await _client(stub_server).create_service_account_pat("sa-1", "svc token")

    assert result["data"]["token"] == "kpat_svc"
    request = stub_server.requests[0]
    assert request["method"] == "POST"
    assert request["path"] == "/api/admin/service-accounts/sa-1/pats"
    assert request["json"] == {"name": "svc token"}


@pytest.mark.asyncio
async def test_create_service_account_pat_sends_expires_at_when_given(
    stub_server,
) -> None:
    """Equivalent TS test: src/__test__/api/adminServiceAccounts.test.ts:160 (name + expiresAt, show-once token)."""
    stub_server.route(
        "POST",
        "/api/admin/service-accounts/sa-1/pats",
        {"success": True, "data": {"_id": "pat-4", "token": "kpat_svc2"}},
        status=201,
    )

    await _client(stub_server).create_service_account_pat(
        "sa-1", "svc token", expires_at="2027-06-01T00:00:00.000Z"
    )

    assert stub_server.requests[0]["json"] == {
        "name": "svc token",
        "expiresAt": "2027-06-01T00:00:00.000Z",
    }


@pytest.mark.asyncio
async def test_create_service_account_pat_raises_for_non_service_account_target(
    stub_server,
) -> None:
    """Equivalent TS test: src/__test__/api/adminServiceAccounts.test.ts:186 (403 ADM-02)."""
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
        await _client(stub_server).create_service_account_pat("human-1", "nope")
