"""Admin API: cross-user PAT/legacy-token management and Service Accounts.

Mirrors the backend's `src/server/routes/api/admin/credentials.ts` and
`src/server/routes/api/admin/serviceAccounts.ts` (Konecty core repo). Every route here
requires an admin session — a regular user gets 403.
"""

from typing import Any, Dict, Optional
from urllib.parse import quote

from .base import BaseService

ADMIN_PATS_PATH = "/api/admin/pats"
ADMIN_LEGACY_TOKENS_PATH = "/api/admin/legacy-tokens"
ADMIN_SERVICE_ACCOUNTS_PATH = "/api/admin/service-accounts"
ADMIN_META_PATH = "/api/admin/meta"

#: `409` — o deployment carrega metadados de um diretório (`METADATA_DIR`); nada é gravável.
META_ADMIN_CONFIG_READ_ONLY_CODE = "meta-admin-config-read-only"

#: `403` — a rota exige sessão first-party; PAT e token OAuth são recusados.
ADMIN_ROUTES_REQUIRE_SESSION_CODE = "admin-credential-routes-require-session"


def _segment(value: str) -> str:
    """Codifica UM segmento de path.

    `safe=""` de propósito, e **não** `quote_plus`: o TS usa `encodeURIComponent`, que produz `%20`
    para espaço enquanto `quote_plus` produziria `+` — as duas URLs deixariam de bater byte a byte,
    que é exatamente a classe de divergência que já mordeu este time. Codifica por segmento porque
    um `_id` de meta carrega `:` (`Product:list:Default`) e codificar o caminho inteiro escaparia as
    barras que o separam.

    Diferente dos ids de PAT/service account acima, aqui o valor é nome de documento ou `_id` de
    meta — entrada livre, não identificador gerado pelo servidor.
    """
    return quote(value, safe="")


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

    # --- Meta Admin API (fatia mínima) ---------------------------------------------------------
    #
    # Seis métodos, não os 17 que `docs/features.json` declara. As demais rotas existem no core e
    # ficam sem método de SDK até haver consumidor — YAGNI. Cada teste em `tests/test_admin.py`
    # cita o equivalente em `src/__test__/api/adminMeta.test.ts` do `konecty-sdk`.
    #
    # Todas exigem **sessão first-party de admin**: PAT e token OAuth são recusados com `403` e o
    # código `admin-credential-routes-require-session` — metadado decide quem lê e escreve o quê.

    async def list_meta_documents(self) -> Dict[str, Any]:
        """GET /api/admin/meta. Returns `data`: [{_id, name, type, label}] do namespace."""
        return await self._get(ADMIN_META_PATH)

    async def read_meta(self, document: str) -> Dict[str, Any]:
        """GET /api/admin/meta/:document. `404` quando o metadado não existe."""
        return await self._get(f"{ADMIN_META_PATH}/{_segment(document)}")

    async def upsert_meta(self, document: str, type: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """
        PUT /api/admin/meta/:document/:type — grava o metadado singleton de um tipo
        (`document`, `composite`, `namespace`).

        Returns `data`: {matchedCount, modifiedCount, upsertedCount, versioned, version}.
        Escrita idêntica ao estado atual não cria versão (`versioned: False`). Num deployment com
        `METADATA_DIR` responde `409` com `META_ADMIN_CONFIG_READ_ONLY_CODE`.
        """
        return await self._put(f"{ADMIN_META_PATH}/{_segment(document)}/{_segment(type)}", json=body)

    async def delete_meta(self, document: str, type: str) -> Dict[str, Any]:
        """
        DELETE /api/admin/meta/:document/:type — remove e versiona a remoção.

        Returns `data`: {deletedCount, version}. O documento `Namespace` não é deletável.
        """
        return await self._delete(f"{ADMIN_META_PATH}/{_segment(document)}/{_segment(type)}")

    async def list_meta_history(
        self,
        meta_id: str,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        GET /api/admin/meta/:metaId/history — versões, mais recentes primeiro.

        `limit`/`offset` são omitidos da query quando não informados, igual ao TS. Um metadado nunca
        escrito desde o deploy devolve **lista vazia**, não `404`: ausência de histórico não é
        ausência de metadado.
        """
        params: Dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset

        return await self._get(
            f"{ADMIN_META_PATH}/{_segment(meta_id)}/history",
            params=params or None,
        )

    async def rollback_meta(self, meta_id: str, version: int) -> Dict[str, Any]:
        """
        POST /api/admin/meta/:metaId/rollback — restaura o conteúdo de uma versão anterior.

        Returns `data`: {version, restoredFrom}. Forward-only: restaurar a v2 **cria** a v5 e nunca
        reescreve nem apaga versão anterior.
        """
        return await self._post(f"{ADMIN_META_PATH}/{_segment(meta_id)}/rollback", json={"version": version})
