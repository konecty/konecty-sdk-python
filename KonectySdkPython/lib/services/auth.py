"""Auth API: Google hosted authorization code flow and login options."""

from typing import Any, Dict, Optional, Union
from urllib.parse import quote, urlencode

from ..exceptions import KonectyAPIError, KonectyGoogleSessionError
from .base import BaseService

GOOGLE_START_PATH = "/api/auth/google/start"
# Conjunto que `encodeURIComponent` deixa passar além de [A-Za-z0-9_.-~], que o
# `quote` já preserva por padrão. Usado para que a URL montada aqui seja
# byte a byte igual à do SDK TypeScript — ver `_encode_query` abaixo.
_ENCODE_URI_COMPONENT_SAFE = "!*'()"
GOOGLE_SESSION_PATH = "/api/auth/google/session"
LOGIN_OPTIONS_PATH = "/api/auth/login-options"


_GOOGLE_SESSION_ERROR_CODES = (
    "invalid_code",
    "expired_code",
    "user_not_found",
    "user_inactive",
)


def _first_error_code(error: KonectyAPIError) -> str:
    """
    Extract the first recognised ``errors[].code``; ``failed`` when there is none.

    Same set and same fallback as the TypeScript SDK, so both raise the same code
    for the same response.
    """
    errors = error.args[0] if error.args else None
    if isinstance(errors, list):
        for item in errors:
            if isinstance(item, dict) and item.get("code") in _GOOGLE_SESSION_ERROR_CODES:
                return str(item["code"])
    return "failed"


def _first_error_message(error: KonectyAPIError) -> str:
    """Extract errors[0].message from a KonectyAPIError raised by the HTTP layer."""
    errors = error.args[0] if error.args else None
    if isinstance(errors, list) and errors:
        first = errors[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, str) and message:
                return message
    return str(error)


def _encode_query(params: list) -> str:
    """
    Codifica o query string como `encodeURIComponent` do SDK TypeScript.

    O default do `urlencode` é `quote_plus`, que transforma espaço em `+`;
    `encodeURIComponent` produz `%20`. Os dois decodificam para o mesmo valor no
    servidor, mas a spec pede URLs idênticas entre os SDKs.
    """
    return urlencode(params, quote_via=quote, safe=_ENCODE_URI_COMPONENT_SAFE)


class AuthService(BaseService):
    """Service for the Google login flow (authorization code hosted by Konecty)."""

    def google_login_url(
        self,
        client_id: str,
        redirect_uri: Optional[str] = None,
        state: Optional[str] = None,
    ) -> str:
        """
        Build the absolute URL of GET /api/auth/google/start. Does not perform any request.

        The browser follows this URL; Konecty redirects to accounts.google.com and,
        after consent, back to redirect_uri with a single-use code (and the original state).
        """
        params = [("client_id", client_id)]
        if redirect_uri is not None:
            params.append(("redirect_uri", redirect_uri))
        if state is not None:
            params.append(("state", state))
        base_url = self._client.base_url.rstrip("/")
        return f"{base_url}{GOOGLE_START_PATH}?{_encode_query(params)}"

    async def exchange_google_code(
        self,
        code: str,
        *,
        geolocation: Optional[Union[Dict[str, Any], str]] = None,
        resolution: Optional[Union[Dict[str, Any], str]] = None,
        source: Optional[str] = None,
        fingerprint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        POST /api/auth/google/session. Exchanges the single-use code (TTL 60s) for a session.

        On success the returned authId is adopted by the client, so following requests
        are authenticated. On error raises KonectyGoogleSessionError — errors[0].message
        as the message plus the machine-readable ``code`` — and leaves the client
        authentication state untouched. The error subclasses KonectyAPIError, so callers
        catching that keep working.
        """
        payload: Dict[str, Any] = {"code": code}
        if geolocation is not None:
            payload["geolocation"] = geolocation
        if resolution is not None:
            payload["resolution"] = resolution
        if source is not None:
            payload["source"] = source
        if fingerprint is not None:
            payload["fingerprint"] = fingerprint

        try:
            response = await self._post(GOOGLE_SESSION_PATH, json=payload)
        except KonectyAPIError as error:
            raise KonectyGoogleSessionError(
                _first_error_code(error), _first_error_message(error)
            ) from error

        auth_id = response.get("authId") if isinstance(response, dict) else None
        if not isinstance(auth_id, str) or not auth_id:
            raise KonectyGoogleSessionError(
                "failed", "Google session response has no authId"
            )

        self._client.set_auth_id(auth_id)
        return response

    async def get_login_options(self) -> Dict[str, Any]:
        """GET /api/auth/login-options. Flags: passwordEnabled, emailOtpEnabled,
        whatsAppOtpEnabled, webauthnEnabled, webauthnRequired, googleEnabled."""
        return await self._get(LOGIN_OPTIONS_PATH)
