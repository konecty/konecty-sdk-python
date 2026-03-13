"""Subscriptions API: get status, subscribe, unsubscribe."""

from typing import Any, Dict

from .base import BaseService


class SubscriptionsService(BaseService):
    """Service for record subscription (watch) status."""

    async def get_subscription_status(
        self, module: str, data_id: str
    ) -> Dict[str, Any]:
        """GET /rest/subscriptions/{module}/{data_id}. Returns success and subscription data."""
        path = f"/rest/subscriptions/{module}/{data_id}"
        return await self._get(path)

    async def subscribe(self, module: str, data_id: str) -> Dict[str, Any]:
        """POST /rest/subscriptions/{module}/{data_id}. Subscribe to record notifications."""
        path = f"/rest/subscriptions/{module}/{data_id}"
        return await self._post(path)

    async def unsubscribe(self, module: str, data_id: str) -> Dict[str, Any]:
        """DELETE /rest/subscriptions/{module}/{data_id}."""
        path = f"/rest/subscriptions/{module}/{data_id}"
        return await self._delete(path)
