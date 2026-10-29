"""Self-service MCP connection status: access level and connected agents, plus disconnect.

Mirrors the backend's `src/server/routes/rest/auth/mcpStatusApi.ts` (Konecty core repo) and
`src/sdk/domains/mcpStatus.ts` in the TypeScript SDK. Both routes require a first-party
session: a PAT or an OAuth access token gets 403 with `MCP_STATUS_REQUIRES_SESSION_CODE`.
"""

from typing import Any, Dict
from urllib.parse import quote

from .base import BaseService

MCP_STATUS_PATH = "/rest/auth/mcp/status"
MCP_CONNECTIONS_PATH = "/rest/auth/mcp/connections"

#: Stable `errors[].code` of the 403 for a non-session caller. Mirrors
#: `MCP_STATUS_REQUIRES_SESSION_CODE` in the TypeScript SDK — keep both in sync.
MCP_STATUS_REQUIRES_SESSION_CODE = "mcp-status-requires-session"

# Characters `encodeURIComponent` leaves alone besides [A-Za-z0-9_.-~], so the path built
# here is byte for byte the TypeScript SDK's.
_ENCODE_URI_COMPONENT_SAFE = "!*'()"


class McpStatusService(BaseService):
    """Service for the caller's own MCP access level and OAuth-connected agents."""

    async def get_mcp_status(self) -> Dict[str, Any]:
        """
        GET /rest/auth/mcp/status. `data` is {access, connections}: `access` is
        "none" | "read" | "write"; each connection carries id, clientName, agent
        ("claude" | "chatgpt" | "other"), scopes, resource, connectedAt, lastActiveAt
        and, while an admin scope is effective, adminExpiresAt. Never token data.
        """
        return await self._get(MCP_STATUS_PATH)

    async def revoke_mcp_connection(self, connection_id: str) -> Dict[str, Any]:
        """
        DELETE /rest/auth/mcp/connections/{id}. Revokes the grant and its tokens.
        Unknown, foreign or already-revoked ids raise the same 404.
        """
        encoded = quote(connection_id, safe=_ENCODE_URI_COMPONENT_SAFE)
        return await self._delete(f"{MCP_CONNECTIONS_PATH}/{encoded}")
