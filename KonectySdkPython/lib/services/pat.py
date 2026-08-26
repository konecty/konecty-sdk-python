"""Self-service Personal Access Token (PAT) API: create, list, revoke.

Mirrors the backend's `src/server/routes/rest/auth/patApi.ts` (Konecty core repo). These
routes require a session/OAuth authentication — a PAT itself cannot mint or revoke PATs
(server-side rule D4/PAT-01), the SDK does not enforce that client-side.
"""

from typing import Any, Dict, Optional

from .base import BaseService

PAT_PATH = "/rest/auth/pat"


class PatService(BaseService):
    """Service for the caller's own Personal Access Tokens.

    `pat_id` below is a server-generated identifier (Mongo-style hex id) —
    interpolated raw into the path with an f-string, no percent-encoding, matching
    the TS SDK's equivalent path-templating in pat.ts. It is never free-form user
    input.
    """

    async def create_pat(
        self, name: str, *, expires_at: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        POST /rest/auth/pat. Wire body: {name, expiresAt?}.

        The plaintext token only ever appears in this response's `data.token` — it is
        never recoverable afterwards. `expires_at` is an ISO date string; omit for a
        PAT that never expires.
        """
        payload: Dict[str, Any] = {"name": name}
        if expires_at is not None:
            payload["expiresAt"] = expires_at
        return await self._post(PAT_PATH, json=payload)

    async def list_pats(self) -> Dict[str, Any]:
        """GET /rest/auth/pat. Returns `data`: list of {_id, name, createdAt, expiresAt, lastUsedAt} — never the hashed token."""
        return await self._get(PAT_PATH)

    async def revoke_pat(self, pat_id: str) -> Dict[str, Any]:
        """DELETE /rest/auth/pat/{pat_id}. Self-scoped: another user's PAT id 404s."""
        path = f"{PAT_PATH}/{pat_id}"
        return await self._delete(path)
