"""Tests for the Google login flow on KonectyClient."""

import pytest

from KonectySdkPython.lib.client import KonectyClient
from KonectySdkPython.lib.exceptions import KonectyAPIError, KonectyGoogleSessionError

FAKE_AUTH_ID = "fake-auth-id-not-a-real-token"
FAKE_CODE = "fake-single-use-code"

LOGIN_OPTIONS = {
    "passwordEnabled": True,
    "emailOtpEnabled": False,
    "whatsAppOtpEnabled": False,
    "webauthnEnabled": False,
    "webauthnRequired": False,
    "googleEnabled": True,
}

SESSION_OK = {
    "success": True,
    "logged": True,
    "authId": FAKE_AUTH_ID,
    "user": {
        "_id": "user-1",
        "access": {"defaults": ["Default"]},
        "admin": False,
        "email": "someone@example.com",
        "group": {"_id": "group-1", "name": "Group"},
        "locale": "pt_BR",
        "login": "someone",
        "name": "Someone",
        "namespace": "example",
        "role": {"_id": "role-1", "name": "Role"},
    },
}


def test_google_login_url_builds_encoded_absolute_url() -> None:
    client = KonectyClient("https://example.konecty.com/")

    url = client.google_login_url(
        client_id="my-app",
        redirect_uri="https://app.example.com/callback",
        state="a b&c=d/é?",
    )

    assert url == (
        "https://example.konecty.com/api/auth/google/start"
        "?client_id=my-app"
        "&redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback"
        "&state=a%20b%26c%3Dd%2F%C3%A9%3F"
    )


def test_google_login_url_encoding_matches_the_typescript_sdk() -> None:
    """
    Byte-for-byte parity with `getGoogleLoginUrl` do @konecty/sdk.

    Mesma entrada e mesma saída esperada do teste
    `src/__test__/api/googleLogin.test.ts` no SDK TypeScript. O ponto sensível é
    o espaço: `urlencode` usa `quote_plus` por padrão e o transformaria em `+`,
    enquanto `encodeURIComponent` produz `%20`. Os dois decodificam para o mesmo
    valor num query string, mas a spec pede URLs idênticas entre os SDKs — e um
    `state` comparado como string crua em qualquer app consumidor divergiria.
    """
    client = KonectyClient("http://localhost:3000")

    url = client.google_login_url(
        client_id="my app",
        redirect_uri="https://app.example.invalid/auth/callback?tenant=acme",
        state="a b&c=d/e?f#g+h",
    )

    assert url == (
        "http://localhost:3000/api/auth/google/start"
        "?client_id=my%20app"
        "&redirect_uri=https%3A%2F%2Fapp.example.invalid%2Fauth%2Fcallback%3Ftenant%3Dacme"
        "&state=a%20b%26c%3Dd%2Fe%3Ff%23g%2Bh"
    )


def test_google_login_url_leaves_encodeuricomponent_safe_chars_intact() -> None:
    """`!*'()~` não são escapados por `encodeURIComponent`; aqui também não."""
    client = KonectyClient("http://localhost:3000")

    url = client.google_login_url(client_id="app", state="~!*'()")

    assert url.endswith("&state=~!*'()")


def test_google_login_url_omits_absent_optional_params() -> None:
    client = KonectyClient("https://example.konecty.com")

    url = client.google_login_url(client_id="my-app")

    assert url == "https://example.konecty.com/api/auth/google/start?client_id=my-app"


@pytest.mark.asyncio
async def test_google_login_url_performs_no_request(stub_server) -> None:
    client = KonectyClient(stub_server.base_url)

    client.google_login_url(client_id="my-app", state="opaque-state")

    assert stub_server.requests == []


@pytest.mark.asyncio
async def test_exchange_google_code_returns_session_and_authenticates_client(
    stub_server,
) -> None:
    stub_server.route("POST", "/api/auth/google/session", SESSION_OK)
    stub_server.route("GET", "/api/auth/login-options", LOGIN_OPTIONS)
    client = KonectyClient(stub_server.base_url)
    assert client.auth_id is None

    result = await client.exchange_google_code(
        FAKE_CODE,
        geolocation={"longitude": -43.2, "latitude": -22.9},
        resolution={"width": 1440, "height": 900},
        source="python-sdk-test",
        fingerprint="fake-fingerprint",
    )

    assert result["authId"] == FAKE_AUTH_ID
    assert result["user"]["_id"] == "user-1"
    assert result["user"]["login"] == "someone"
    assert client.auth_id == FAKE_AUTH_ID

    session_request = stub_server.requests[0]
    assert session_request["method"] == "POST"
    assert session_request["json"] == {
        "code": FAKE_CODE,
        "geolocation": {"longitude": -43.2, "latitude": -22.9},
        "resolution": {"width": 1440, "height": 900},
        "source": "python-sdk-test",
        "fingerprint": "fake-fingerprint",
    }

    # The adopted authId is used by the following requests.
    await client.get_login_options()
    assert stub_server.requests[-1]["authorization"] == FAKE_AUTH_ID


@pytest.mark.asyncio
async def test_exchange_google_code_sends_only_code_when_no_telemetry(
    stub_server,
) -> None:
    stub_server.route("POST", "/api/auth/google/session", SESSION_OK)
    client = KonectyClient(stub_server.base_url)

    await client.exchange_google_code(FAKE_CODE)

    assert stub_server.requests[0]["json"] == {"code": FAKE_CODE}


@pytest.mark.asyncio
async def test_exchange_google_code_raises_first_error_and_keeps_client_anonymous(
    stub_server,
) -> None:
    stub_server.route(
        "POST",
        "/api/auth/google/session",
        {
            "success": False,
            "errors": [
                {
                    "message": "Session code is invalid or already used",
                    "code": "invalid_code",
                },
                {"message": "should be ignored", "code": "other"},
            ],
        },
        status=400,
    )
    client = KonectyClient(stub_server.base_url)

    with pytest.raises(KonectyAPIError) as exc_info:
        await client.exchange_google_code(FAKE_CODE)

    assert str(exc_info.value) == "Session code is invalid or already used"
    # Paridade com o SDK TypeScript (KonectyGoogleSessionError.code): o código
    # legível por máquina acompanha o erro, para o caller ramificar/traduzir sem
    # parsear a mensagem — e é o do primeiro erro reconhecido, não o do segundo.
    assert isinstance(exc_info.value, KonectyGoogleSessionError)
    assert exc_info.value.code == "invalid_code"
    assert client.auth_id is None
    assert client.headers["Authorization"] == ""


@pytest.mark.asyncio
async def test_exchange_google_code_falls_back_to_failed_code(stub_server) -> None:
    """Corpo sem código reconhecível vira `failed`, como no SDK TypeScript."""
    stub_server.route(
        "POST",
        "/api/auth/google/session",
        {"success": False, "errors": [{"message": "Boom", "code": "something_else"}]},
        status=500,
    )
    client = KonectyClient(stub_server.base_url)

    with pytest.raises(KonectyGoogleSessionError) as exc_info:
        await client.exchange_google_code(FAKE_CODE)

    assert exc_info.value.code == "failed"
    assert str(exc_info.value) == "Boom"


@pytest.mark.asyncio
async def test_google_session_error_is_catchable_as_api_error(stub_server) -> None:
    """Quem já capturava KonectyAPIError continua capturando: é subclasse."""
    stub_server.route(
        "POST",
        "/api/auth/google/session",
        {"success": False, "errors": [{"message": "Inactive", "code": "user_inactive"}]},
        status=400,
    )
    client = KonectyClient(stub_server.base_url)

    with pytest.raises(KonectyAPIError):
        await client.exchange_google_code(FAKE_CODE)


@pytest.mark.asyncio
async def test_exchange_google_code_error_does_not_drop_existing_session(
    stub_server,
) -> None:
    stub_server.route(
        "POST",
        "/api/auth/google/session",
        {
            "success": False,
            "errors": [{"message": "Session code expired", "code": "expired_code"}],
        },
        status=400,
    )
    client = KonectyClient(stub_server.base_url, "previous-fake-token")

    with pytest.raises(KonectyAPIError, match="Session code expired"):
        await client.exchange_google_code(FAKE_CODE)

    assert client.auth_id == "previous-fake-token"


@pytest.mark.asyncio
async def test_get_login_options_returns_flags(stub_server) -> None:
    stub_server.route("GET", "/api/auth/login-options", LOGIN_OPTIONS)
    client = KonectyClient(stub_server.base_url)

    options = await client.get_login_options()

    assert options["googleEnabled"] is True
    assert options["passwordEnabled"] is True
    assert options["webauthnRequired"] is False
    assert stub_server.requests[0]["method"] == "GET"
