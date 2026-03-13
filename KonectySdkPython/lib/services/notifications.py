"""Notifications API: list, unread count, mark read, mark all read."""

from typing import Any, Dict, Optional

from .base import BaseService


class NotificationsService(BaseService):
    """Service for user notifications."""

    async def list_notifications(
        self,
        *,
        read: Optional[bool] = None,
        page: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """GET /rest/notifications. Query: read, page, limit."""
        params: Dict[str, str] = {}
        if read is not None:
            params["read"] = "true" if read else "false"
        if page is not None:
            params["page"] = str(page)
        if limit is not None:
            params["limit"] = str(limit)
        return await self._get(
            "/rest/notifications", params=params if params else None
        )

    async def get_unread_count(self) -> Dict[str, Any]:
        """GET /rest/notifications/unread-count."""
        return await self._get("/rest/notifications/unread-count")

    async def mark_notification_read(self, notification_id: str) -> Dict[str, Any]:
        """PUT /rest/notifications/{id}/read."""
        path = f"/rest/notifications/{notification_id}/read"
        return await self._put(path)

    async def mark_all_notifications_read(self) -> Dict[str, Any]:
        """PUT /rest/notifications/read-all."""
        return await self._put("/rest/notifications/read-all")
