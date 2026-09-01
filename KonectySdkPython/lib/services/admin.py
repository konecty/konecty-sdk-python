"""Admin API: cross-user PAT/legacy-token management and Service Accounts.

Mirrors the backend's `src/server/routes/api/admin/credentials.ts` and
`src/server/routes/api/admin/serviceAccounts.ts` (Konecty core repo). Every route here
requires an admin session — a regular user gets 403.
"""

from typing import Any, Dict, List, Optional

from .base import BaseService

ADMIN_PATS_PATH = "/api/admin/pats"
ADMIN_LEGACY_TOKENS_PATH = "/api/admin/legacy-tokens"
ADMIN_SERVICE_ACCOUNTS_PATH = "/api/admin/service-accounts"
ADMIN_MCP_ACCESS_PATH = "/api/admin/mcp-access"


class AdminService(BaseService):
    """Service for namespace-wide credential and Service Account administration.

    `user_id`/`pat_id`/`fingerprint`/`service_account_id` below are server-generated
    identifiers (Mongo-style hex ids or slug-like alphanumeric/hyphen strings) —
    interpolated raw into the path with an f-string, no percent-encoding, matching
    the TS SDK's equivalent path-templating in adminCredentials.ts/
    adminServiceAccounts.ts. They are never free-form user input.
    """

    async def list_all_pats(self) -> Dict[str, Any]:
        """GET /api/admin/pats. Returns `data`: {pats: [...], legacyTokens: [...]} for the whole namespace."""
        return await self._get(ADMIN_PATS_PATH)

    async def revoke_user_pat(self, user_id: str, pat_id: str) -> Dict[str, Any]:
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
        POST /api/admin/service-accounts. Wire body: {name, username, accessMap?}.

        `access_map` maps document name -> 'read' | 'readWrite'; when omitted the
        `accessMap` key itself is left out of the request body (matching the TS SDK,
        which passes `accessMap: undefined` and drops it on `JSON.stringify`) — the
        backend treats a missing map the same as an empty one: no access to anything.
        Returns `data`: {_id, username, role, access, mcpRoleHint?} — 201 on success,
        409 if the username is already in use.
        """
        payload: Dict[str, Any] = {"name": name, "username": username}
        if access_map is not None:
            payload["accessMap"] = access_map
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

    async def get_mcp_access(self) -> Dict[str, Any]:
        """
        GET /api/admin/mcp-access. Returns `data`: {roles, readRoleIds, writeRoleIds, readOnlyConfig}.

        `readRoleIds` are the roles allowed to reach the MCP; `writeRoleIds` the subset
        also allowed to use write/destructive tools (a role listed there reads too, whether
        or not it also appears in `readRoleIds`). `readOnlyConfig` is true when the
        deployment loads its namespace config from a metadata directory — `update_mcp_access`
        then refuses with 409.
        """
        return await self._get(ADMIN_MCP_ACCESS_PATH)

    async def update_mcp_access(
        self, read_role_ids: List[str], write_role_ids: List[str]
    ) -> Dict[str, Any]:
        """
        PUT /api/admin/mcp-access. Wire body: {readRoleIds, writeRoleIds}.

        Replaces both lists wholesale (a role omitted loses access). An unknown role id
        is rejected with 400 and nothing is written; a deployment configured by a metadata
        directory answers 409 with code `mcp-access-config-read-only`.
        """
        return await self._put(
            ADMIN_MCP_ACCESS_PATH,
            json={"readRoleIds": read_role_ids, "writeRoleIds": write_role_ids},
        )
