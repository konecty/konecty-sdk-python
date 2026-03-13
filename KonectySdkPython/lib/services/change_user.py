"""Change User API: add, remove, define, replace, countInactive, removeInactive, setQueue."""

from typing import Any, Dict, List

from .base import BaseService


class ChangeUserService(BaseService):
    """Service for changing user/queue on records."""

    async def add_users(
        self, module: str, ids: List[Any], users: Any
    ) -> Dict[str, Any]:
        """POST /rest/changeUser/{module}/add. Body: ids, data (users)."""
        path = f"/rest/changeUser/{module}/add"
        return await self._post(path, json={"ids": ids, "data": users})

    async def remove_users(
        self, module: str, ids: List[Any], users: Any
    ) -> Dict[str, Any]:
        """POST /rest/changeUser/{module}/remove."""
        path = f"/rest/changeUser/{module}/remove"
        return await self._post(path, json={"ids": ids, "data": users})

    async def define_users(
        self, module: str, ids: List[Any], users: Any
    ) -> Dict[str, Any]:
        """POST /rest/changeUser/{module}/define."""
        path = f"/rest/changeUser/{module}/define"
        return await self._post(path, json={"ids": ids, "data": users})

    async def replace_users(
        self,
        module: str,
        ids: List[Any],
        *,
        from_user: Any = None,
        to_user: Any = None,
    ) -> Dict[str, Any]:
        """POST /rest/changeUser/{module}/replace. Body: ids, data: { from?, to? }."""
        path = f"/rest/changeUser/{module}/replace"
        data: Dict[str, Any] = {}
        if from_user is not None:
            data["from"] = from_user
        if to_user is not None:
            data["to"] = to_user
        return await self._post(path, json={"ids": ids, "data": data})

    async def count_inactive(self, module: str, ids: List[Any]) -> Dict[str, Any]:
        """POST /rest/changeUser/{module}/countInactive. Body: ids."""
        path = f"/rest/changeUser/{module}/countInactive"
        return await self._post(path, json={"ids": ids})

    async def remove_inactive(self, module: str, ids: List[Any]) -> Dict[str, Any]:
        """POST /rest/changeUser/{module}/removeInactive. Body: ids."""
        path = f"/rest/changeUser/{module}/removeInactive"
        return await self._post(path, json={"ids": ids})

    async def set_queue(
        self, module: str, ids: List[Any], queue: Any
    ) -> Dict[str, Any]:
        """POST /rest/changeUser/{module}/setQueue. Body: ids, data (queue config)."""
        path = f"/rest/changeUser/{module}/setQueue"
        return await self._post(path, json={"ids": ids, "data": queue})
