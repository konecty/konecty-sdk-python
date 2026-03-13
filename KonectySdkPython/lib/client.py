"""Módulo para gerenciar configurações do Konecty."""

import json
import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Literal, Optional, Union, cast

import aiohttp

from .exceptions import (
    KonectyAPIError,
    KonectyError,
    KonectyValidationError,
)
from .file_manager import FileManager
from .filters import KonectyFilter, KonectyFindParams
from .http import request as _http_request
from .http import StreamResponse
from .feature_types.kpi import KpiConfig
from .serialization import json_serial
from .services.aggregation import AggregationService
from .services.change_user import ChangeUserService
from .services.comments import CommentsService
from .services.export import ExportService
from .services.files import FilesService
from .services.notifications import NotificationsService
from .services.query import QueryResult, QueryService
from .services.stream import FindStreamResult, StreamService
from .services.subscriptions import SubscriptionsService
from .types import KonectyDateTime, KonectyDict, KonectyUpdateId

# Configura o logger do urllib3 para mostrar apenas erros
logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)

KONECTY_UPDATE_IGNORE_FIELDS = [
    "_id",
    "code",
    "_updatedAt",
    "_createdAt",
    "_updatedBy",
    "_createdBy",
]
KONECTY_CREATE_IGNORE_FIELDS = ["_updatedAt", "_createdAt", "_updatedBy", "_createdBy"]


def get_first_dict(items: List[Any]) -> Optional[KonectyDict]:
    """Retorna o primeiro item de uma lista como dicionário ou None se estiver vazia."""
    if not items:
        return None
    first = items[0]
    if isinstance(first, dict):
        return cast(KonectyDict, first)
    return None


class KonectyClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url
        self.headers = {"Authorization": f"{token}"}
        self.file_manager = FileManager(base_url=base_url, headers=self.headers)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        stream: bool = False,
        return_bytes: bool = False,
    ) -> Any:
        """Internal HTTP request. Used by client methods and services."""
        return await _http_request(
            self,
            method,
            path,
            params=params,
            json=json,
            stream=stream,
            return_bytes=return_bytes,
        )

    @property
    def _stream(self) -> StreamService:
        if not hasattr(self, "_stream_service"):
            self._stream_service = StreamService(self)
        return self._stream_service

    async def find_stream(
        self,
        module: str,
        options: KonectyFindParams,
        *,
        include_total: bool = False,
    ) -> FindStreamResult:
        """
        Stream records as NDJSON. Returns result with .stream (async generator) and .total (when include_total).

        Example:
            result = await client.find_stream("Contact", options, include_total=True)
            async for record in result.stream:
                ...
            total = result.total
        """
        return await self._stream.find_stream(module, options, include_total=include_total)

    async def count_stream(
        self,
        module: str,
        filter_params: Optional[KonectyFilter] = None,
        **kwargs: Any,
    ) -> int:
        """Return total count for the module (GET /rest/stream/{module}/count)."""
        return await self._stream.count_stream(module, filter_params, **kwargs)

    @property
    def _files(self) -> FilesService:
        if not hasattr(self, "_files_service"):
            self._files_service = FilesService(self)
        return self._files_service

    async def download_file(
        self,
        module: str,
        record_code: str,
        field_name: str,
        file_name: str,
    ) -> bytes:
        """Download a file from a record field. Returns bytes."""
        return await self._files.download_file(
            module, record_code, field_name, file_name
        )

    async def download_image(
        self,
        module: str,
        record_id: str,
        field_name: str,
        file_name: str,
        *,
        style: Optional[Literal["full", "thumb", "wm"]] = None,
    ) -> bytes:
        """Download an image (optional style: full, thumb, wm). Returns bytes."""
        return await self._files.download_image(
            module, record_id, field_name, file_name, style=style
        )

    @property
    def _aggregation(self) -> AggregationService:
        if not hasattr(self, "_aggregation_service"):
            self._aggregation_service = AggregationService(self)
        return self._aggregation_service

    async def get_kpi(
        self,
        module: str,
        kpi_config: KpiConfig,
        *,
        filter_params: Optional[KonectyFilter] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Run KPI aggregation. Returns dict with value and count."""
        return await self._aggregation.get_kpi(
            module, kpi_config, filter_params=filter_params, **kwargs
        )

    async def get_graph(
        self,
        module: str,
        graph_config: Any,
        *,
        filter_params: Optional[KonectyFilter] = None,
        **kwargs: Any,
    ) -> str:
        """Get graph as SVG string. graph_config: type, xAxis, yAxis, series, etc."""
        return await self._aggregation.get_graph(
            module, graph_config, filter_params=filter_params, **kwargs
        )

    async def get_pivot(
        self,
        module: str,
        pivot_config: Any,
        *,
        filter_params: Optional[KonectyFilter] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Get pivot table result. pivot_config: rows, columns, values."""
        return await self._aggregation.get_pivot(
            module, pivot_config, filter_params=filter_params, **kwargs
        )

    @property
    def _export(self) -> ExportService:
        if not hasattr(self, "_export_service"):
            self._export_service = ExportService(self)
        return self._export_service

    async def export_list(
        self,
        module: str,
        list_name: str,
        format: Literal["csv", "xlsx", "json", "xls"],
        *,
        filter_params: Optional[KonectyFilter] = None,
        **kwargs: Any,
    ) -> bytes:
        """Export list as CSV, XLSX, or JSON. Returns file bytes."""
        return await self._export.export_list(
            module, list_name, format, filter_params=filter_params, **kwargs
        )

    @property
    def _comments(self) -> CommentsService:
        if not hasattr(self, "_comments_service"):
            self._comments_service = CommentsService(self)
        return self._comments_service

    async def get_comments(self, module: str, data_id: str) -> Any:
        """Get comments for a record."""
        return await self._comments.get_comments(module, data_id)

    async def create_comment(
        self, module: str, data_id: str, text: str, parent_id: Optional[str] = None
    ) -> Any:
        """Create a comment (optionally reply via parent_id)."""
        return await self._comments.create_comment(
            module, data_id, text, parent_id=parent_id
        )

    async def update_comment(
        self, module: str, data_id: str, comment_id: str, text: str
    ) -> Any:
        """Update a comment."""
        return await self._comments.update_comment(
            module, data_id, comment_id, text
        )

    async def delete_comment(
        self, module: str, data_id: str, comment_id: str
    ) -> Any:
        """Delete (soft) a comment."""
        return await self._comments.delete_comment(module, data_id, comment_id)

    async def search_comment_users(
        self, module: str, data_id: str, query: str = ""
    ) -> Any:
        """Search users for @mention autocomplete."""
        return await self._comments.search_comment_users(
            module, data_id, query
        )

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
    ) -> Any:
        """Search comments with filters."""
        return await self._comments.search_comments(
            module,
            data_id,
            query=query,
            author_id=author_id,
            start_date=start_date,
            end_date=end_date,
            page=page,
            limit=limit,
        )

    @property
    def _subscriptions(self) -> SubscriptionsService:
        if not hasattr(self, "_subscriptions_service"):
            self._subscriptions_service = SubscriptionsService(self)
        return self._subscriptions_service

    async def get_subscription_status(self, module: str, data_id: str) -> Any:
        """Get subscription status for a record."""
        return await self._subscriptions.get_subscription_status(module, data_id)

    async def subscribe(self, module: str, data_id: str) -> Any:
        """Subscribe to record notifications."""
        return await self._subscriptions.subscribe(module, data_id)

    async def unsubscribe(self, module: str, data_id: str) -> Any:
        """Unsubscribe from record."""
        return await self._subscriptions.unsubscribe(module, data_id)

    @property
    def _notifications(self) -> NotificationsService:
        if not hasattr(self, "_notifications_service"):
            self._notifications_service = NotificationsService(self)
        return self._notifications_service

    async def list_notifications(
        self,
        *,
        read: Optional[bool] = None,
        page: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> Any:
        """List user notifications."""
        return await self._notifications.list_notifications(
            read=read, page=page, limit=limit
        )

    async def get_unread_notifications_count(self) -> Any:
        """Get unread notifications count."""
        return await self._notifications.get_unread_count()

    async def mark_notification_read(self, notification_id: str) -> Any:
        """Mark a notification as read."""
        return await self._notifications.mark_notification_read(notification_id)

    async def mark_all_notifications_read(self) -> Any:
        """Mark all notifications as read."""
        return await self._notifications.mark_all_notifications_read()

    @property
    def _change_user(self) -> ChangeUserService:
        if not hasattr(self, "_change_user_service"):
            self._change_user_service = ChangeUserService(self)
        return self._change_user_service

    async def change_user_add(
        self, module: str, ids: List[Any], users: Any
    ) -> Any:
        """Add users to records."""
        return await self._change_user.add_users(module, ids, users)

    async def change_user_remove(
        self, module: str, ids: List[Any], users: Any
    ) -> Any:
        """Remove users from records."""
        return await self._change_user.remove_users(module, ids, users)

    async def change_user_define(
        self, module: str, ids: List[Any], users: Any
    ) -> Any:
        """Define users on records."""
        return await self._change_user.define_users(module, ids, users)

    async def change_user_replace(
        self,
        module: str,
        ids: List[Any],
        *,
        from_user: Any = None,
        to_user: Any = None,
    ) -> Any:
        """Replace user on records."""
        return await self._change_user.replace_users(
            module, ids, from_user=from_user, to_user=to_user
        )

    async def change_user_count_inactive(self, module: str, ids: List[Any]) -> Any:
        """Count inactive users on records."""
        return await self._change_user.count_inactive(module, ids)

    async def change_user_remove_inactive(self, module: str, ids: List[Any]) -> Any:
        """Remove inactive users from records."""
        return await self._change_user.remove_inactive(module, ids)

    async def change_user_set_queue(
        self, module: str, ids: List[Any], queue: Any
    ) -> Any:
        """Set queue on records."""
        return await self._change_user.set_queue(module, ids, queue)

    @property
    def _query(self) -> QueryService:
        if not hasattr(self, "_query_service"):
            self._query_service = QueryService(self)
        return self._query_service

    async def execute_query_json(
        self,
        body: Any,
        *,
        include_total: bool = True,
        include_meta: bool = False,
    ) -> QueryResult:
        """Execute cross-module query (POST /rest/query/json). Returns QueryResult with .stream, .total, .meta."""
        return await self._query.execute_query_json(
            body, include_total=include_total, include_meta=include_meta
        )

    async def execute_query_sql(
        self,
        sql: str,
        *,
        include_total: bool = True,
        include_meta: bool = False,
    ) -> QueryResult:
        """Execute SQL query (POST /rest/query/sql). Returns QueryResult. SQL parse errors return 400."""
        return await self._query.execute_query_sql(
            sql, include_total=include_total, include_meta=include_meta
        )

    async def list_saved_queries(self) -> Any:
        """List saved queries."""
        return await self._query.list_saved_queries()

    async def get_saved_query(self, query_id: str) -> Any:
        """Get a saved query by id."""
        return await self._query.get_saved_query(query_id)

    async def create_saved_query(
        self,
        name: str,
        query: Dict[str, Any],
        description: Optional[str] = None,
    ) -> Any:
        """Create a saved query."""
        return await self._query.create_saved_query(
            name, query, description=description
        )

    async def update_saved_query(
        self,
        query_id: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        query: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Update a saved query."""
        return await self._query.update_saved_query(
            query_id, name=name, description=description, query=query
        )

    async def delete_saved_query(self, query_id: str) -> Any:
        """Delete a saved query."""
        return await self._query.delete_saved_query(query_id)

    async def share_saved_query(
        self,
        query_id: str,
        shared_with: List[Dict[str, Any]],
        is_public: Optional[bool] = None,
    ) -> Any:
        """Share a saved query."""
        return await self._query.share_saved_query(
            query_id, shared_with, is_public=is_public
        )

    async def find(self, module: str, options: KonectyFindParams) -> List[KonectyDict]:
        params: Dict[str, str] = {}
        for key, value in options.model_dump(exclude_none=True).items():
            params[key] = (
                json.dumps(value, default=json_serial)
                if key != "fields"
                else ",".join(value)
            )

        async with (
            aiohttp.ClientSession() as session,
            session.get(
                f"{self.base_url}/rest/data/{module}/find",
                params=params,
                headers={"Authorization": self.headers["Authorization"]},
            ) as response,
        ):
            response.raise_for_status()
            result = await response.json()
            if not result.get("success", False):
                errors = result.get("errors", [])
                logger.error(errors)
                raise KonectyAPIError(errors)
            data = result.get("data", [])
            return cast(List[KonectyDict], data)

    def find_sync(self, module: str, options: KonectyFindParams) -> List[KonectyDict]:
        """Versão síncrona de find."""
        params: Dict[str, str] = {}
        for key, value in options.model_dump(exclude_none=True).items():
            params[key] = (
                json.dumps(value, default=json_serial)
                if key != "fields"
                else ",".join(value)
            )

        import requests

        response = requests.get(
            f"{self.base_url}/rest/data/{module}/find",
            params=params,
            headers={"Authorization": self.headers["Authorization"]},
        )
        response.raise_for_status()
        result = response.json()
        if not result.get("success", False):
            errors = result.get("errors", [])
            logger.error(errors)
            raise KonectyAPIError(errors)
        data = result.get("data", [])
        return cast(List[KonectyDict], data)

    def find_one_sync(
        self, module: str, filter_params: KonectyFilter
    ) -> Optional[KonectyDict]:
        """Versão síncrona de find_one."""
        find_params = KonectyFindParams(filter=filter_params, limit=1)
        result = self.find_sync(module, find_params)
        if not result:
            return None
        return cast(KonectyDict, result[0]) if isinstance(result[0], dict) else None

    async def find_by_id(self, module: str, id: str) -> Optional[KonectyDict]:
        async with (
            aiohttp.ClientSession() as session,
            session.get(
                f"{self.base_url}/rest/data/{module}/{id}",
                headers={"Authorization": self.headers["Authorization"]},
            ) as response,
        ):
            response.raise_for_status()
            result = await response.json()
            if not result.get("success", False):
                errors = result.get("errors", [])
                logger.error(errors)
                raise KonectyAPIError(errors)
            data = result.get("data", [None])
            return get_first_dict(data)

    async def find_one(
        self, module: str, filter_params: KonectyFilter
    ) -> Optional[KonectyDict]:
        find_params = KonectyFindParams(filter=filter_params, limit=1)
        result = await self.find(module, find_params)
        if not result:
            return None
        return cast(KonectyDict, result[0]) if isinstance(result[0], dict) else None

    async def create(self, module: str, data: KonectyDict) -> Optional[KonectyDict]:
        endpoint = f"/rest/data/{module}"
        cleaned_data = {
            k: v for k, v in data.items() if k not in KONECTY_CREATE_IGNORE_FIELDS
        }
        async with (
            aiohttp.ClientSession(base_url=self.base_url) as session,
            session.post(
                endpoint,
                headers=self.headers,
                json=json.loads(json.dumps(cleaned_data, default=json_serial)),
            ) as response,
        ):
            result = await response.json()
            if not result.get("success", False):
                errors = result.get("errors", [])
                raise KonectyAPIError(errors)
            result_data: list[KonectyDict] = result.get("data", [])
            if not result_data:
                return None
            return result_data[0]

    async def update_one(
        self, module: str, id: str, updatedAt: datetime, data: KonectyDict
    ) -> Optional[KonectyDict]:
        endpoint = f"/rest/data/{module}"
        cleaned_data = {
            k: v for k, v in data.items() if k not in KONECTY_UPDATE_IGNORE_FIELDS
        }
        payload = {
            "ids": [
                {
                    "_id": id,
                    "_updatedAt": KonectyDateTime.from_datetime(updatedAt).to_json(),
                }
            ],
            "data": json.loads(json.dumps(cleaned_data, default=json_serial)),
        }
        async with (
            aiohttp.ClientSession(base_url=self.base_url) as session,
            session.put(
                endpoint,
                headers=self.headers,
                json=json.loads(json.dumps(payload, default=json_serial)),
            ) as response,
        ):
            result = await response.json()
            if not result.get("success", False):
                errors = result.get("errors", [])
                raise KonectyAPIError(errors)
            return result.get("data", [None])[0]

    async def update(
        self, module: str, ids: list[KonectyUpdateId], data: KonectyDict
    ) -> list[KonectyDict]:
        endpoint = f"/rest/data/{module}"
        cleaned_data = {
            k: v for k, v in data.items() if k not in KONECTY_UPDATE_IGNORE_FIELDS
        }
        payload = {
            "ids": [id.to_dict() for id in ids],
            "data": json.loads(json.dumps(cleaned_data, default=json_serial)),
        }
        async with (
            aiohttp.ClientSession(base_url=self.base_url) as session,
            session.put(endpoint, headers=self.headers, json=payload) as response,
        ):
            result = await response.json()
            if not result.get("success", False):
                errors = result.get("errors", [])
                raise KonectyAPIError(errors)
            return result.get("data", [])

    async def delete_one(
        self, module: str, id: str, updatedAt: datetime
    ) -> Optional[KonectyDict]:
        endpoint = f"/rest/data/{module}"
        payload = {
            "ids": [
                {
                    "_id": id,
                    "_updatedAt": KonectyDateTime.from_datetime(updatedAt).to_json(),
                }
            ],
        }
        async with (
            aiohttp.ClientSession(base_url=self.base_url) as session,
            session.delete(endpoint, headers=self.headers, json=payload) as response,
        ):
            result = await response.json()
            return result.get("data", [None])[0]

    async def get_document(self, document_id: str) -> Optional[KonectyDict]:
        """Obtém o documento do Konecty."""
        endpoint = f"/rest/menu/documents/{document_id}"
        async with (
            aiohttp.ClientSession(base_url=self.base_url) as session,
            session.get(endpoint, headers=self.headers) as response,
        ):
            result = await response.json()
            if result is None:
                logger.error(f"Documento {document_id} não encontrado")
                return None
            if isinstance(result, dict):
                return cast(KonectyDict, result)
            logger.error(f"Documento {document_id} retornou formato inválido")
            return None

    async def get_schema(self, document_id: str) -> Optional[KonectyDict]:
        """Obtém o schema do documento e gera um modelo Pydantic."""
        try:
            document = await self.get_document(document_id)
            if document is None:
                return None
            return document
        except Exception as e:
            logger.error(f"Erro ao obter schema do documento {document_id}: {e}")
            return None

    async def get_setting(self, key: str) -> Optional[str]:
        """Obtém uma configuração do Konecty."""
        setting = await self.find_one(
            "Setting", KonectyFilter.create().add_condition("key", "equals", key)
        )
        if setting is None:
            return None
        return cast(str, setting.get("value"))

    def get_setting_sync(self, key: str) -> Optional[str]:
        """Versão síncrona de get_setting."""
        setting = self.find_one_sync(
            "Setting", KonectyFilter.create().add_condition("key", "equals", key)
        )
        if setting is None:
            return None
        return cast(str, setting.get("value"))

    async def get_settings(self, keys: List[str]) -> Dict[str, str]:
        """Obtém múltiplas configurações do Konecty.

        Args:
            keys: Lista de chaves das configurações a serem obtidas

        Returns:
            Dicionário com as chaves e seus respectivos valores. Chaves não encontradas terão valor None.
        """
        if not keys:
            return {}

        filter_params = KonectyFilter.create().add_condition("key", "in", keys)
        find_params = KonectyFindParams(filter=filter_params)

        settings = await self.find("Setting", find_params)

        result = {}

        for setting in settings:
            key = setting.get("key")
            value = setting.get("value")
            result[key] = cast(str, value)

        return result

    def get_settings_sync(self, keys: List[str]) -> Dict[str, str]:
        """Versão síncrona de get_settings.

        Args:
            keys: Lista de chaves das configurações a serem obtidas

        Returns:
            Dicionário com as chaves e seus respectivos valores. Chaves não encontradas terão valor None.
        """
        if not keys:
            return {}

        filter_params = KonectyFilter.create().add_condition("key", "in", keys)
        find_params = KonectyFindParams(filter=filter_params)

        settings = self.find_sync("Setting", find_params)

        result = {}

        for setting in settings:
            key = setting.get("key")
            value = setting.get("value")
            result[key] = cast(str, value)

        return result

    async def count_documents(self, module: str, filter_params: KonectyFilter) -> int:
        params: Dict[str, str] = {}
        options = KonectyFindParams(
            filter=filter_params,
            fields=["_id"],
            limit=1,
        )

        for key, value in options.model_dump(exclude_none=True).items():
            params[key] = (
                json.dumps(value, default=json_serial)
                if key != "fields"
                else ",".join(value)
            )

        async with (
            aiohttp.ClientSession() as session,
            session.get(
                f"{self.base_url}/rest/data/{module}/find",
                params=params,
                headers={"Authorization": self.headers["Authorization"]},
            ) as response,
        ):
            response.raise_for_status()
            result = await response.json()
            if not result.get("success", False):
                errors = result.get("errors", [])
                logger.error(errors)
                raise KonectyAPIError(errors)
            count = result.get("total", 0)
            return count

    async def upload_file(
        self,
        module: str,
        record_code: str,
        field_name: str,
        file: Union[bytes, str, AsyncGenerator[bytes, None]],
        file_name: Optional[str] = None,
        file_type: Optional[str] = None,
    ) -> str:
        """
        Upload a file to a specific record field in Konecty.

        Parameters
        ----------
        module : str
            The module name where the record is located (e.g., 'Contact', 'User').
        record_code : str
            The unique identifier code of the record.
        field_name : str
            The name of the field where the file will be uploaded.
        file : Union[bytes, str]
            The file to upload. Can be:
                - bytes: Raw file content (file_name is required)
                - str: URL to the file (file_name is optional; if not provided, will use the last segment of the URL)
        file_name : Optional[str], default=None
            The name to use for the file when uploaded. Required when 'file' is bytes, optional otherwise.

        Returns
        -------
        str
            The file key (ID) assigned by Konecty, which can be used for referencing the file in future operations.

        Raises
        ------
        ValueError
            If file_name is not provided when file is bytes, or if the file is empty or invalid.
        TypeError
            If the file argument is not bytes or a URL string.
        KonectyError
            If the API returns an error response.
        HTTPError
            If there is an HTTP connection error.

        Limitations
        -----------
        - Maximum file size: 20 MB (enforced by server configuration; see nginx.conf).
        - Only one file per call is supported.
        - Progress tracking is not available in this version.

        Examples
        --------
        Upload a file using a file path as string:
            >>> file_id = await client.upload_file(
            ...     module='Contact',
            ...     record_code='ABC123',
            ...     field_name='attachments',
            ...     file='/path/to/document.pdf'
            ... )

        Upload a file using a Path object:
            >>> from pathlib import Path
            >>> file_path = Path('/path/to/image.jpg')
            >>> file_id = await client.upload_file(
            ...     module='Contact',
            ...     record_code='ABC123',
            ...     field_name='photo',
            ...     file=file_path
            ... )

        Upload file content from bytes with a custom filename:
            >>> with open('document.pdf', 'rb') as f:
            ...     file_content = f.read()
            >>> file_id = await client.upload_file(
            ...     module='Document',
            ...     record_code='XYZ789',
            ...     field_name='file',
            ...     file=file_content,
            ...     file_name='important_document.pdf'
            ... )

        Handling errors:
            >>> try:
            ...     file_id = await client.upload_file(
            ...         module='Contact',
            ...         record_code='INVALID',
            ...         field_name='attachments',
            ...         file='/invalid/path/to/file.pdf'
            ...     )
            ... except FileNotFoundError as e:
            ...     print(f"File not found: {e}")
            ... except ValueError as e:
            ...     print(f"Validation error: {e}")
            ... except KonectyError as e:
            ...     print(f"API error: {e}")

        """
        result = await self.file_manager.upload_file(
            module=module,
            record_code=record_code,
            field_name=field_name,
            file=file,
            file_name=file_name,
            file_type=file_type,
        )

        if not result.get("success", False):
            self.file_manager.handle_error_response(result)
        return result.get("key", "")
