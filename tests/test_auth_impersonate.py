"""Tests for KonectyClient.impersonate (POST /api/auth/impersonate) and the support-session
fields of GET /rest/auth/info.

Parity with the TypeScript SDK (`konecty/konecty-sdk`): `src/__test__/api/impersonate.test.ts`
and `src/__test__/api/info.test.ts` (describe 'Konecty info (support session fields)') assert the
same inputs and the same outputs as the tests below; each test names its TypeScript twin.
"""

import pytest

from KonectySdkPython.lib.client import KonectyClient
from KonectySdkPython.lib.exceptions import KonectyAPIError, KonectyImpersonateError

FAKE_ADMIN_AUTH_ID = "fake-admin-session-id"
FAKE_SUPPORT_AUTH_ID = "not-a-real-support-auth-id"

SESSION_DATA = {
    "authId": FAKE_SUPPORT_AUTH_ID,
    "expiresAt": "2099-01-01T01:00:00.000Z",
    "user": {"_id": "fake-target-id", "name": "Jane Doe", "username": "jane.doe"},
}

PATH = "/api/auth/impersonate"


def _client(stub_server) -> KonectyClient:
    return KonectyClient(base_url=stub_server.base_url, token=FAKE_ADMIN_AUTH_ID)


@pytest.mark.asyncio
async def test_impersonate_by_user_id_sends_exact_request_and_parses(stub_server) -> None:
    """TS twin: 'Should POST { userId } to /api/auth/impersonate with the admin session and return authId, expiresAt and user'."""
    stub_server.route("POST", PATH, {"success": True, "data": SESSION_DATA})

    result = await _client(stub_server).impersonate(user_id="fake-target-id")

    request = stub_server.requests[0]
    assert request["method"] == "POST"
    assert request["raw_path"] == PATH
    assert request["authorization"] == FAKE_ADMIN_AUTH_ID
    assert request["json"] == {"userId": "fake-target-id"}
    assert result == SESSION_DATA


@pytest.mark.asyncio
async def test_impersonate_by_code_sends_number_in_body(stub_server) -> None:
    """TS twin: 'Should POST { code } as a JSON number'."""
    stub_server.route("POST", PATH, {"success": True, "data": SESSION_DATA})

    result = await _client(stub_server).impersonate(code=6290)

    body = stub_server.requests[0]["json"]
    assert body == {"code": 6290}
    assert isinstance(body["code"], int) and not isinstance(body["code"], bool)
    assert result["authId"] == FAKE_SUPPORT_AUTH_ID


@pytest.mark.asyncio
async def test_impersonate_does_not_adopt_the_support_session(stub_server) -> None:
    """TS twin: 'Should not adopt the support session: the next call still carries the admin session'."""
    stub_server.route("POST", PATH, {"success": True, "data": SESSION_DATA})
    client = _client(stub_server)

    await client.impersonate(user_id="fake-target-id")
    await client.impersonate(user_id="fake-target-id")

    assert [r["authorization"] for r in stub_server.requests] == [
        FAKE_ADMIN_AUTH_ID,
        FAKE_ADMIN_AUTH_ID,
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status, code, message, expected_code",
    [
        (400, "IMPERSONATE_INVALID_TARGET", "Body must contain exactly one of userId or code", "IMPERSONATE_INVALID_TARGET"),
        (401, None, "Unauthorized", "failed"),
        (403, "IMPERSONATE_FORBIDDEN", "Admin access required", "IMPERSONATE_FORBIDDEN"),
        (403, "IMPERSONATE_TARGET_NOT_ALLOWED", "Target not allowed", "IMPERSONATE_TARGET_NOT_ALLOWED"),
        (403, "IMPERSONATED_SESSION_FORBIDDEN", "Support session cannot do this", "IMPERSONATED_SESSION_FORBIDDEN"),
        (403, "admin-credential-routes-require-session", "Requires a first-party session", "admin-credential-routes-require-session"),
        (404, "IMPERSONATE_TARGET_NOT_FOUND", "Target not found", "IMPERSONATE_TARGET_NOT_FOUND"),
        (500, None, "Internal server error", "failed"),
    ],
)
async def test_impersonate_raises_typed_error(
    stub_server, status, code, message, expected_code
) -> None:
    """TS twin: the errorCases table ('Should throw KonectyImpersonateError with code ...'), same rows."""
    error = {"message": message} if code is None else {"message": message, "code": code}
    stub_server.route("POST", PATH, {"success": False, "errors": [error]}, status=status)

    with pytest.raises(KonectyImpersonateError) as raised:
        await _client(stub_server).impersonate(user_id="fake-target-id")

    assert raised.value.code == expected_code
    assert str(raised.value) == message
    assert isinstance(raised.value, KonectyAPIError)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs", [{}, {"user_id": "fake-target-id", "code": 6290}]
)
async def test_impersonate_rejects_zero_or_two_targets_without_request(
    stub_server, kwargs
) -> None:
    """TS twin: 'Should throw IMPERSONATE_INVALID_TARGET without sending a request when the target has zero or two keys'."""
    stub_server.route("POST", PATH, {"success": True, "data": SESSION_DATA})

    with pytest.raises(KonectyImpersonateError) as raised:
        await _client(stub_server).impersonate(**kwargs)

    assert raised.value.code == "IMPERSONATE_INVALID_TARGET"
    assert stub_server.requests == []


@pytest.mark.asyncio
async def test_info_exposes_impersonation_fields(stub_server) -> None:
    """TS twin: info.test.ts 'Should return impersonatedBy and impersonationExpiresAt untouched'."""
    stub_server.route(
        "GET",
        "/rest/auth/info",
        {
            "logged": True,
            "user": {
                "_id": "fake-target-id",
                "impersonatedBy": {"_id": "fake-admin-id", "name": "Admin Fake"},
                "impersonationExpiresAt": "2099-01-01T01:00:00.000Z",
            },
        },
    )

    result = await KonectyClient(
        base_url=stub_server.base_url, token=FAKE_SUPPORT_AUTH_ID
    ).info()

    assert result["user"]["impersonatedBy"] == {"_id": "fake-admin-id", "name": "Admin Fake"}
    assert result["user"]["impersonationExpiresAt"] == "2099-01-01T01:00:00.000Z"
