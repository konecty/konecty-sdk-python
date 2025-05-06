import logging
from os import path, unlink
from typing import AsyncGenerator, Optional, Union
from urllib.parse import quote, urlparse

import aiohttp


class FileManager:
    """
    Handles file operations such as reading files as bytes and validating file existence.
    Designed for use with KonectyClient and other components needing file manipulation.
    """

    DEFAULT_TIMEOUT = 60

    def __init__(self, base_url: str, headers: dict) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = headers
        self.logger = logging.getLogger("konecty.file_manager")

    async def upload_file(
        self,
        module: str,
        record_code: str,
        field_name: str,
        file: Union[bytes, str, AsyncGenerator[bytes, None]],
        file_name: Optional[str],
        file_type: Optional[str],
    ) -> dict:
        """
        Upload a file to Konecty. Only bytes or a URL (str) are accepted or a Stream (AsyncGenerator[bytes, None]).
        If a URL is provided, the file will be streamed and uploaded.
        Args:
            module (str): Nome do módulo.
            record_code (str): Código do registro.
            field_name (str): Nome do campo.
            file (bytes | str | AsyncGenerator[bytes, None]): Arquivo a ser enviado (bytes) ou URL (str) ou Stream (AsyncGenerator[bytes, None]).
            file_name (Optional[str]): Nome do arquivo (obrigatório se file for bytes, opcional se for URL).
        Returns:
            dict: Resposta JSON da API.
        Raises:
            aiohttp.ClientError, ValueError, TypeError
        """
        import aiohttp
        url = self._build_upload_url(module, record_code, field_name)
        form = await self.build_multipart_form(file, file_name, file_type)

        async with aiohttp.ClientSession() as session:
            client_timeout = aiohttp.ClientTimeout(total=self.DEFAULT_TIMEOUT)
            try:
                async with session.post(url, data=form, headers=self.headers, timeout=client_timeout) as response:
                    response.raise_for_status()
                    return await response.json()
            except aiohttp.ClientError as e:
                raise

    def _build_upload_url(
        self,
        module: str,
        record_code: str,
        field_name: str,
    ) -> str:
        if not all([module, record_code, field_name]):
            raise ValueError("All parameters (module, record_code, field_name) must be provided.")
        # URL encode each path segment
        module_enc = quote(str(module), safe="")
        record_code_enc = quote(str(record_code), safe="")
        field_name_enc = quote(str(field_name), safe="")

        return f"{self.base_url}/rest/file/upload/ns/access/{module_enc}/{record_code_enc}/{field_name_enc}"

    async def build_multipart_form(
        self,
        file: Union[bytes, str, AsyncGenerator[bytes, None]],
        file_name: Optional[str] = None,
        file_type: Optional[str] = None,
    ) -> "aiohttp.FormData":
        file_bytes, name = await self.prepare_file_data(file, file_name)
        import aiohttp
        form = aiohttp.FormData()
        form.add_field(
            "file",
            file_bytes,
            filename=name,
            content_type=file_type,
        )
        return form

    async def prepare_file_data(
        self,
        file: Union[bytes, str, AsyncGenerator[bytes, None]],
        file_name: Optional[str] = None,
    ) -> tuple[bytes, str]:
        """
        Prepara os dados do arquivo para inclusão em um request multipart.
        Args:
            file (bytes | str): Conteúdo em bytes ou URL.
            file_name (Optional[str]): Nome do arquivo (obrigatório se file for bytes, opcional se for URL).
        Returns:
            tuple[bytes, str, str]: (conteúdo em bytes, nome do arquivo, content-type)
        Raises:
            ValueError: Se file_name não for fornecido quando file for bytes.
            TypeError: Se file não for bytes ou str.
        """

        if isinstance(file, bytes):
            if not file_name:
                raise ValueError("file_name must be provided when uploading bytes")
            file_bytes = file
            name = file_name
        elif isinstance(file, AsyncGenerator):
            # Save the file stream to a temporary file and read it
            temp_file_name = f"/app/logs/{file_name}"
            with open(temp_file_name, "wb") as temp_file:
                async for chunk in file:
                    self.logger.info(f"Chunk: {len(chunk)}")
                    temp_file.write(chunk)

            with open(temp_file_name, "rb") as temp_file:
                file_bytes = temp_file.read()

            unlink(temp_file_name)
            name = file_name or temp_file.name
        elif isinstance(file, str):
            # Treat as URL
            async with aiohttp.ClientSession() as session:
                async with session.get(file) as resp:
                    resp.raise_for_status()
                    file_bytes = await resp.read()
                    # Use file_name if provided, else extract from URL
                    if file_name:
                        name = file_name
                    else:
                        parsed = urlparse(file)
                        name = path.basename(parsed.path) or "downloaded_file"
        else:
            raise TypeError("file must be bytes or a URL string")
        # content_type, _ = mimetypes.guess_type(name)
        # if not content_type:
        #     content_type = "application/octet-stream"
        return file_bytes, name

    def get_auth_headers(self, headers: dict) -> dict:
        if not headers or "Authorization" not in headers:
            raise ValueError("Authorization header is required for file upload.")
        return dict(headers)

    async def upload_file_post(
        self,
        module: str,
        record_code: str,
        field_name: str,
        file: Union[bytes, str],
        file_name: Optional[str],
        timeout: int = 60,
    ) -> "aiohttp.ClientResponse":
        import aiohttp
        url = self._build_upload_url(module, record_code, field_name)
        form = await self.build_multipart_form(file, file_name)
        async with aiohttp.ClientSession() as session:
            try:
                client_timeout = aiohttp.ClientTimeout(total=timeout)
                async with session.post(url, data=form, headers=self.headers, timeout=client_timeout) as response:
                    response.raise_for_status()
                    return response
            except aiohttp.ClientError as e:
                raise

    async def parse_json_response(self, response: aiohttp.ClientResponse) -> dict:
        try:
            return await response.json()
        except Exception as exc:
            try:
                text = await response.text()
            except Exception:
                text = "<erro ao obter texto da resposta>"
            raise ValueError(f"Falha ao decodificar JSON da resposta: {exc}. Resposta original: {text}") from exc 

    def handle_error_response(self, response_json: dict) -> None:
        errors = response_json.get("errors", [])
        if not errors:
            raise FileManagerUnknownError("Erro desconhecido: resposta sem array 'errors'", details=response_json)
        
        error_message = ",\n ".join(error.get("message", "Erro desconhecido") for error in errors)
        raise FileManagerUnknownError(error_message, details=errors[0])

    async def process_api_response(self, response: aiohttp.ClientResponse) -> str:
        """
        Wrapper de alto nível para processar resposta de API, tratando todos os cenários de erro e sucesso.

        Args:
            response (aiohttp.ClientResponse): Resposta HTTP da API.

        Returns:
            str: Valor do campo 'key' em caso de sucesso.

        Raises:
            FileManagerAPIError: Para erros conhecidos de API.
            ValueError: Para erros de parsing ou formato inesperado.
        """
        import logging
        logger = logging.getLogger("konecty.file_manager")
        try:
            response_json = await self.parse_json_response(response)
        except Exception as exc:
            logger.error(f"Erro ao parsear resposta JSON: {exc}")
            raise
        try:
            if response_json.get("success", False):
                key = response_json.get("key")
                if not key:
                    raise FileManagerUnknownError("Campo 'key' ausente ou vazio na resposta de sucesso.", details=response_json)
                return key
            else:
                self.handle_error_response(response_json)
                # Se não lançar, garantir raise
                raise FileManagerUnknownError(
                    "Resposta de erro não mapeada corretamente.", details=response_json
                )
        except FileManagerAPIError as api_exc:
            logger.error(f"Erro de API: {api_exc}")
            raise
        except Exception as exc:
            logger.error(f"Erro inesperado ao processar resposta: {exc}")
            raise FileManagerUnknownError(f"Erro inesperado ao processar resposta: {exc}", details=getattr(exc, 'details', None)) from exc

class FileManagerAPIError(Exception):
    """Exceção base para erros de API do FileManager."""
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.details = details or {}

class FileManagerValidationError(FileManagerAPIError):
    """Exceção para erros de validação de entrada."""
    pass

class FileManagerAuthError(FileManagerAPIError):
    """Exceção para erros de autenticação."""
    pass

class FileManagerServerError(FileManagerAPIError):
    """Exceção para erros de servidor/backend."""
    pass

class FileManagerUnknownError(FileManagerAPIError):
    """Exceção para erros inesperados/desconhecidos."""
    pass 