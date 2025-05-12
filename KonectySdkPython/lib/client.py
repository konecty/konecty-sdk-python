"""Módulo para gerenciar configurações do Konecty."""

import json
import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional, Union, cast

import aiohttp

from .file_manager import FileManager
from .filters import KonectyFilter, KonectyFindParams
from .types import KonectyDateTime

# Configura o logger do urllib3 para mostrar apenas erros
logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)

KonectyDict = Dict[str, Any]

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


class KonectyError(Exception):
    """Exceção base para erros do Konecty."""

    pass


class KonectyAPIError(KonectyError):
    """Exceção para erros da API."""

    pass


class KonectyValidationError(KonectyError):
    """Exceção para erros de validação."""

    pass


class KonectySerializationError(KonectyError):
    """Exceção para erros de serialização."""

    def __init__(self) -> None:
        super().__init__("Tipo não serializável")


def json_serial(obj: Any) -> str:
    """Serializa objetos para JSON."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise KonectySerializationError()


class KonectyClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url
        self.headers = {"Authorization": f"{token}"}
        self.file_manager = FileManager(base_url=base_url, headers=self.headers)

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
