"""Admin API: cross-user PAT/legacy-token management and Service Accounts.

Mirrors the backend's `src/server/routes/api/admin/credentials.ts` and
`src/server/routes/api/admin/serviceAccounts.ts` (Konecty core repo). Every route here
requires an admin session — a regular user gets 403.
"""

from typing import Any, Dict, Optional

from .base import BaseService

ADMIN_PATS_PATH = "/api/admin/pats"
ADMIN_LEGACY_TOKENS_PATH = "/api/admin/legacy-tokens"
ADMIN_SERVICE_ACCOUNTS_PATH = "/api/admin/service-accounts"


class AdminService(BaseService):
    """Service for namespace-wide credential and Service Account administration."""

    async def list_all_pats(self) -> Dict[str, Any]:
        """GET /api/admin/pats. Returns `data`: {pats: [...], legacyTokens: [...]} for the whole namespace."""
        return await self._get(ADMIN_PATS_PATH)

    async def revoke_pat(self, user_id: str, pat_id: str) -> Dict[str, Any]:
        """DELETE /api/admin/pats/{user_id}/{pat_id}. Revokes a PAT belonging to any user."""
        path = f"{ADMIN_PATS_PATH}/{user_id}/{pat_id}"
        return await self._delete(path)

    async def revoke_legacy_token(self, user_id: str, fingerprint: str) -> Dict[str, Any]:
        """DELETE /api/admin/legacy-tokens/{user_id}/{fingerprint}. `fingerprint` comes from `list_all_pats`'s `legacyTokens` entries."""
        path = f"{ADMIN_LEGACY_TOKENS_PATH}/{user_id}/{fingerprint}"
        return await self._delete(path)

    async def create_service_account(
        self,
        name: str,
        username: str,
        access_map: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        POST /api/admin/service-accounts. Wire body: {name, username, accessMap}.

        `access_map` maps document name -> 'read' | 'readWrite'; an empty/omitted map
        means no access to anything. Returns `data`: {_id, username, role, access,
        mcpRoleHint?} — 201 on success, 409 if the username is already in use.
        """
        payload: Dict[str, Any] = {
            "name": name,
            "username": username,
            "accessMap": access_map or {},
        }
        return await self._post(ADMIN_SERVICE_ACCOUNTS_PATH, json=payload)

    async def list_service_accounts(self) -> Dict[str, Any]:
        """GET /api/admin/service-accounts. Returns `data`: list of {_id, name, username, active, access, pats}."""
        return await self._get(ADMIN_SERVICE_ACCOUNTS_PATH)

    async def update_service_account_access(
        self, service_account_id: str, access_map: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        PUT /api/admin/service-accounts/{id}/access. Wire body: {accessMap}.

        Replaces the whole access map (a document omitted from `access_map` loses
        access). Returns `data`: {_id, access}.
        """
        path = f"{ADMIN_SERVICE_ACCOUNTS_PATH}/{service_account_id}/access"
        return await self._put(path, json={"accessMap": access_map})

    async def create_service_account_pat(
        self,
        service_account_id: str,
        name: str,
        *,
        expires_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        POST /api/admin/service-accounts/{id}/pats. Wire body: {name, expiresAt?}.

        Mints a PAT on behalf of a Service Account (never a human user — the backend
        rejects that with 403, ADM-02). Returns `data`: {_id, token} — 201 on success.
        """
        payload: Dict[str, Any] = {"name": name}
        if expires_at is not None:
            payload["expiresAt"] = expires_at
        path = f"{ADMIN_SERVICE_ACCOUNTS_PATH}/{service_account_id}/pats"
        return await self._post(path, json=payload)
