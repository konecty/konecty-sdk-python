"""Comments API: list, create, update, delete, search users, search comments."""

from typing import Any, Dict, Optional

from .base import BaseService


class CommentsService(BaseService):
    """Service for record comments."""

    async def get_comments(self, module: str, data_id: str) -> Dict[str, Any]:
        """GET /rest/comment/{module}/{data_id}. Returns API result (success, data)."""
        path = f"/rest/comment/{module}/{data_id}"
        return await self._get(path)

    async def create_comment(
        self,
        module: str,
        data_id: str,
        text: str,
        parent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /rest/comment/{module}/{data_id}. Body: text, parentId optional."""
        path = f"/rest/comment/{module}/{data_id}"
        body: Dict[str, Any] = {"text": text}
        if parent_id is not None:
            body["parentId"] = parent_id
        return await self._post(path, json=body)

    async def update_comment(
        self,
        module: str,
        data_id: str,
        comment_id: str,
        text: str,
    ) -> Dict[str, Any]:
        """PUT /rest/comment/{module}/{data_id}/{comment_id}. Body: text."""
        path = f"/rest/comment/{module}/{data_id}/{comment_id}"
        return await self._put(path, json={"text": text})

    async def delete_comment(
        self,
        module: str,
        data_id: str,
        comment_id: str,
    ) -> Dict[str, Any]:
        """DELETE /rest/comment/{module}/{data_id}/{comment_id}."""
        path = f"/rest/comment/{module}/{data_id}/{comment_id}"
        return await self._delete(path)

    async def search_comment_users(
        self,
        module: str,
        data_id: str,
        query: str = "",
    ) -> Dict[str, Any]:
        """GET /rest/comment/{module}/{data_id}/users/search?q=."""
        path = f"/rest/comment/{module}/{data_id}/users/search"
        params = {"q": query} if query else {}
        return await self._get(path, params=params or None)

    async def search_comments(
        self,
        module: str,
        data_id: str,
        *,
        query: Optional[str] = None,
        author_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        page: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """GET /rest/comment/{module}/{data_id}/search with query params."""
        path = f"/rest/comment/{module}/{data_id}/search"
        params: Dict[str, str] = {}
        if query is not None:
            params["q"] = query
        if author_id is not None:
            params["authorId"] = author_id
        if start_date is not None:
            params["startDate"] = start_date
        if end_date is not None:
            params["endDate"] = end_date
        if page is not None:
            params["page"] = str(page)
        if limit is not None:
            params["limit"] = str(limit)
        return await self._get(path, params=params or None)
