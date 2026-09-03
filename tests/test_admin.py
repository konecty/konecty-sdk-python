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

    with pytest.raises(KonectyAPIError, match="Admin access required"):
        await _client(stub_server).list_all_pats()

    request = stub_server.requests[0]
    assert request["method"] == "GET"
    assert request["path"] == "/api/admin/pats"


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

    with pytest.raises(KonectyAPIError, match="PAT not found"):
        await _client(stub_server).revoke_user_pat("user-1", "unknown")

    request = stub_server.requests[0]
    assert request["method"] == "DELETE"
    assert request["path"] == "/api/admin/pats/user-1/unknown"


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
async def test_revoke_legacy_token_interpolates_fingerprint_with_hyphens(
    stub_server,
) -> None:
    """
    Documents (does not newly enforce) that ids/fingerprints are interpolated raw,
    with no percent-encoding — see the note on AdminService. A hyphenated
    fingerprint, a legitimate server-generated shape, must reach the backend
    byte-for-byte in the path.
    """
    stub_server.route(
        "DELETE",
        "/api/admin/legacy-tokens/user-2/ab12-cd34-ef56",
        {"success": True, "data": {"success": True}},
    )

    result = await _client(stub_server).revoke_legacy_token("user-2", "ab12-cd34-ef56")

    assert result["success"] is True
    request = stub_server.requests[0]
    assert request["method"] == "DELETE"
    assert request["path"] == "/api/admin/legacy-tokens/user-2/ab12-cd34-ef56"


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
async def test_create_service_account_omits_access_map_when_none(
    stub_server,
) -> None:
    """
    Equivalent TS test: src/__test__/api/adminServiceAccounts.test.ts —
    describe('createServiceAccount') > it('Should omit accessMap from the body
    when not given').

    Parity with the TS SDK: when `access_map` is omitted, `createServiceAccount`
    passes `accessMap: undefined`, which `JSON.stringify` drops from the wire body
    entirely. The Python SDK mirrors that by leaving the `accessMap` key out of
    the payload rather than sending an explicit `{}` (see
    KonectySdkPython/lib/services/admin.py::create_service_account).
    """
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
    }
    assert "accessMap" not in stub_server.requests[0]["json"]


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

    with pytest.raises(KonectyAPIError, match="Username already in use"):
        await _client(stub_server).create_service_account("Bot", "taken")

    request = stub_server.requests[0]
    assert request["method"] == "POST"
    assert request["path"] == "/api/admin/service-accounts"


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

    with pytest.raises(KonectyAPIError, match="Service account not found"):
        await _client(stub_server).update_service_account_access("unknown", {})

    request = stub_server.requests[0]
    assert request["method"] == "PUT"
    assert request["path"] == "/api/admin/service-accounts/unknown/access"


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

    with pytest.raises(KonectyAPIError, match="target is not a service account"):
        await _client(stub_server).create_service_account_pat("human-1", "nope")

    request = stub_server.requests[0]
    assert request["method"] == "POST"
    assert request["path"] == "/api/admin/service-accounts/human-1/pats"


@pytest.mark.asyncio
async def test_revoke_legacy_token_raises_not_found(stub_server) -> None:
    """
    Equivalent TS test: src/__test__/api/adminCredentials.test.ts —
    describe('revokeLegacyToken') > it('Should return the 404 not-found error
    verbatim when the fingerprint does not belong to the given userId').
    """
    stub_server.route(
        "DELETE",
        "/api/admin/legacy-tokens/user-2/unknown-fingerprint",
        {"success": False, "errors": [{"message": "Legacy token not found"}]},
        status=404,
    )

    with pytest.raises(KonectyAPIError, match="Legacy token not found"):
        await _client(stub_server).revoke_legacy_token("user-2", "unknown-fingerprint")

    request = stub_server.requests[0]
    assert request["method"] == "DELETE"
    assert request["path"] == "/api/admin/legacy-tokens/user-2/unknown-fingerprint"


@pytest.mark.asyncio
async def test_list_service_accounts_raises_forbidden_for_non_admin(stub_server) -> None:
    """
    Equivalent TS test: src/__test__/api/adminServiceAccounts.test.ts —
    describe('listServiceAccounts') > it('Should return the 403 error verbatim
    when the caller is not an admin').
    """
    stub_server.route(
        "GET",
        "/api/admin/service-accounts",
        {"success": False, "errors": [{"message": "Admin access required"}]},
        status=403,
    )

    with pytest.raises(KonectyAPIError, match="Admin access required"):
        await _client(stub_server).list_service_accounts()

    request = stub_server.requests[0]
    assert request["method"] == "GET"
    assert request["path"] == "/api/admin/service-accounts"


# --- Meta Admin API (fatia mínima) --------------------------------------------------------------
#
# Paridade com `src/__test__/api/adminMeta.test.ts` do `konecty-sdk`: cada teste abaixo cita o
# equivalente de lá e usa **a mesma entrada e a mesma saída esperada**.
#
# Diferença de contrato que é da casa, não desta fatia: aqui um não-2xx levanta `KonectyAPIError`,
# enquanto o TS devolve o envelope `{success: False, errors}`. O código estável continua alcançável
# — `KonectyAPIError` recebe a lista de `errors` inteira, então `exc.value.args[0][0]["code"]` dá o
# mesmo valor que o TS expõe em `result.errors[0].code`.


@pytest.mark.asyncio
async def test_list_meta_documents_gets_the_meta_collection(stub_server) -> None:
    """Equivalent TS test: src/__test__/api/adminMeta.test.ts (describe('listMetaDocuments'))."""
    stub_server.route(
        "GET",
        "/api/admin/meta",
        {"success": True, "data": [{"_id": "Contact", "name": "Contact", "type": "document"}]},
    )

    result = await _client(stub_server).list_meta_documents()

    assert result["data"][0]["_id"] == "Contact"
    request = stub_server.requests[0]
    assert request["method"] == "GET"
    assert request["path"] == "/api/admin/meta"


@pytest.mark.asyncio
async def test_read_meta_encodes_the_document_segment(stub_server) -> None:
    """
    Equivalent TS test: src/__test__/api/adminMeta.test.ts —
    'Should GET /api/admin/meta/:document with the segment percent-encoded'.

    `%20`, nunca `+`: `quote(safe="")` casa com o `encodeURIComponent` do TS. Com `quote_plus` as
    duas URLs deixariam de bater byte a byte — a divergência que já mordeu este time.
    """
    stub_server.route("GET", "/api/admin/meta/My Doc", {"success": True, "data": {"_id": "My Doc", "type": "document"}})

    await _client(stub_server).read_meta("My Doc")

    # `raw_path`, não `path`: o aiohttp decodifica `path`, e o que importa aqui é o que foi para a
    # rede — a mesma URL que o TS produz.
    assert stub_server.requests[0]["raw_path"] == "/api/admin/meta/My%20Doc"


@pytest.mark.asyncio
async def test_read_meta_returns_not_found_envelope(stub_server) -> None:
    """Equivalent TS test: src/__test__/api/adminMeta.test.ts — 'Should surface the 404 envelope'."""
    stub_server.route(
        "GET",
        "/api/admin/meta/Ghost",
        {"success": False, "errors": [{"message": "Meta not found"}]},
        status=404,
    )

    with pytest.raises(KonectyAPIError, match="Meta not found"):
        await _client(stub_server).read_meta("Ghost")


@pytest.mark.asyncio
async def test_upsert_meta_puts_the_body_and_reports_the_version(stub_server) -> None:
    """Equivalent TS test: src/__test__/api/adminMeta.test.ts — 'Should PUT ... and report the version'."""
    stub_server.route(
        "PUT",
        "/api/admin/meta/Contact/document",
        {"success": True, "data": {"matchedCount": 1, "modifiedCount": 1, "upsertedCount": 0, "versioned": True, "version": 3}},
    )

    result = await _client(stub_server).upsert_meta("Contact", "document", {"icon": "random", "menuSorter": 1})

    assert result["data"]["version"] == 3
    assert result["data"]["versioned"] is True
    request = stub_server.requests[0]
    assert request["method"] == "PUT"
    assert request["path"] == "/api/admin/meta/Contact/document"
    # Corpo byte a byte igual ao do TS.
    assert request["json"] == {"icon": "random", "menuSorter": 1}


@pytest.mark.asyncio
async def test_upsert_meta_reports_no_version_when_content_is_identical(stub_server) -> None:
    """Equivalent TS test: src/__test__/api/adminMeta.test.ts — 'Should report versioned=false ...'."""
    stub_server.route(
        "PUT",
        "/api/admin/meta/Contact/document",
        {"success": True, "data": {"matchedCount": 1, "modifiedCount": 0, "upsertedCount": 0, "versioned": False, "version": 3}},
    )

    result = await _client(stub_server).upsert_meta("Contact", "document", {"icon": "random"})

    assert result["data"]["versioned"] is False


@pytest.mark.asyncio
async def test_upsert_meta_surfaces_the_read_only_config_code(stub_server) -> None:
    """Equivalent TS test: src/__test__/api/adminMeta.test.ts — 'Should surface the 409 read-only-config code'."""
    stub_server.route(
        "PUT",
        "/api/admin/meta/Contact/document",
        {"success": False, "errors": [{"message": "Metadata is owned by the metadata directory", "code": "meta-admin-config-read-only"}]},
        status=409,
    )

    with pytest.raises(KonectyAPIError) as exc:
        await _client(stub_server).upsert_meta("Contact", "document", {})

    # Mesmo valor que o TS expõe em `result.errors[0].code`.
    assert exc.value.args[0][0]["code"] == "meta-admin-config-read-only"


@pytest.mark.asyncio
async def test_upsert_meta_surfaces_the_requires_session_code(stub_server) -> None:
    """Equivalent TS test: src/__test__/api/adminMeta.test.ts — 'Should surface the 403 requires-session code'."""
    stub_server.route(
        "PUT",
        "/api/admin/meta/Contact/document",
        {"success": False, "errors": [{"message": "requires a first-party session", "code": "admin-credential-routes-require-session"}]},
        status=403,
    )

    with pytest.raises(KonectyAPIError) as exc:
        await _client(stub_server).upsert_meta("Contact", "document", {})

    assert exc.value.args[0][0]["code"] == "admin-credential-routes-require-session"


@pytest.mark.asyncio
async def test_delete_meta_deletes_and_reports_the_version(stub_server) -> None:
    """Equivalent TS test: src/__test__/api/adminMeta.test.ts (describe('deleteMeta'))."""
    stub_server.route("DELETE", "/api/admin/meta/Contact/document", {"success": True, "data": {"deletedCount": 1, "version": 4}})

    result = await _client(stub_server).delete_meta("Contact", "document")

    assert result["data"]["deletedCount"] == 1
    assert result["data"]["version"] == 4
    assert stub_server.requests[0]["method"] == "DELETE"


@pytest.mark.asyncio
async def test_list_meta_history_sends_limit_and_offset(stub_server) -> None:
    """
    Equivalent TS test: src/__test__/api/adminMeta.test.ts —
    'Should GET /api/admin/meta/:metaId/history with limit and offset in the query string'.
    """
    stub_server.route("GET", "/api/admin/meta/Contact:list:Default/history", {"success": True, "data": []})

    await _client(stub_server).list_meta_history("Contact:list:Default", limit=10, offset=20)

    request = stub_server.requests[0]
    # `_id` de meta carrega `:`, codificado no segmento; a query fica fora dele.
    # `:` fica cru: o `yarl` do aiohttp normaliza `%3A` de volta para `:` ao montar a requisição,
    # porque `:` é `pchar` legal (RFC 3986). O TS foi alinhado a isto — ver o `segment()` de
    # src/sdk/domains/adminMeta.ts — para que os dois SDKs coloquem os MESMOS bytes na rede.
    assert request["raw_path"] == "/api/admin/meta/Contact:list:Default/history?limit=10&offset=20"
    assert request["query"] == {"limit": "10", "offset": "20"}


@pytest.mark.asyncio
async def test_list_meta_history_omits_the_query_when_no_options(stub_server) -> None:
    """Equivalent TS test: src/__test__/api/adminMeta.test.ts — 'Should omit the query string entirely'."""
    stub_server.route("GET", "/api/admin/meta/Contact/history", {"success": True, "data": []})

    await _client(stub_server).list_meta_history("Contact")

    assert stub_server.requests[0]["query"] == {}


@pytest.mark.asyncio
async def test_list_meta_history_returns_empty_for_a_meta_never_written(stub_server) -> None:
    """Equivalent TS test: src/__test__/api/adminMeta.test.ts — 'Should return an empty list ... not an error'."""
    stub_server.route("GET", "/api/admin/meta/Contact/history", {"success": True, "data": []})

    result = await _client(stub_server).list_meta_history("Contact")

    # Ausência de histórico não é ausência de metadado — o consumidor precisa distinguir.
    assert result["data"] == []


@pytest.mark.asyncio
async def test_rollback_meta_posts_the_version_and_reports_the_new_one(stub_server) -> None:
    """Equivalent TS test: src/__test__/api/adminMeta.test.ts (describe('rollbackMeta'))."""
    stub_server.route("POST", "/api/admin/meta/Contact/rollback", {"success": True, "data": {"version": 5, "restoredFrom": 2}})

    result = await _client(stub_server).rollback_meta("Contact", 2)

    request = stub_server.requests[0]
    assert request["method"] == "POST"
    assert request["path"] == "/api/admin/meta/Contact/rollback"
    assert request["json"] == {"version": 2}
    # Forward-only: restaurar a v2 cria a v5 — não apaga a v3 nem a v4.
    assert result["data"]["version"] == 5
    assert result["data"]["restoredFrom"] == 2


#: Vetor de codificação compartilhado com o SDK TypeScript. As mesmas 8 entradas estão em
#: `src/__test__/api/adminMeta.test.ts` (`SEGMENT_ENCODING_CASES`), com as mesmas saídas — é o que
#: trava a paridade byte a byte da URL, onde a divergência entre os dois SDKs já aconteceu.
SEGMENT_ENCODING_CASES = [
    ("Contact:list:Default", "Contact:list:Default"),
    ("My Doc", "My%20Doc"),
    # `/` SEMPRE codificado: cru, quebraria o path em dois segmentos.
    ("a/b", "a%2Fb"),
    # `+` SEMPRE codificado: cru num path, servidor leniente pode lê-lo como espaço.
    ("a+b", "a%2Bb"),
    ('{"$ne":null}', "%7B%22$ne%22:null%7D"),
    ("a&b", "a&b"),
    ("a@b", "a@b"),
    ("ç", "%C3%A7"),
]


@pytest.mark.asyncio
async def test_path_segment_encoding_matches_the_typescript_sdk(stub_server) -> None:
    """
    Equivalent TS test: src/__test__/api/adminMeta.test.ts —
    describe('path segment encoding') > 'Should produce the same bytes the Python SDK puts on the wire'.

    Assevera o `raw_path`, não o `path`: o aiohttp decodifica `path`, e o que precisa bater entre os
    dois SDKs é o que vai para a rede.
    """
    client = _client(stub_server)

    for raw, _encoded in SEGMENT_ENCODING_CASES:
        stub_server.route("GET", f"/api/admin/meta/{raw}", {"success": True, "data": {}})
        await client.read_meta(raw)

    seen = [req["raw_path"].replace("/api/admin/meta/", "") for req in stub_server.requests]

    assert seen == [encoded for _raw, encoded in SEGMENT_ENCODING_CASES]
