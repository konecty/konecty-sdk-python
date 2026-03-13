"""File download and image download (binary responses)."""

from typing import Literal, Optional

from .base import BaseService


class FilesService(BaseService):
    """Service for downloading files and images (GET returning bytes)."""

    async def download_file(
        self,
        module: str,
        record_code: str,
        field_name: str,
        file_name: str,
    ) -> bytes:
        """
        Download a file from a record field. GET /rest/file/{module}/{record_code}/{field_name}/{file_name}.

        Args:
            module: Document/module name.
            record_code: Record code (id).
            field_name: Field name holding the file.
            file_name: File name.

        Returns:
            File content as bytes.
        """
        path = f"/rest/file/{module}/{record_code}/{field_name}/{file_name}"
        return await self._get(path, return_bytes=True)

    async def download_image(
        self,
        module: str,
        record_id: str,
        field_name: str,
        file_name: str,
        *,
        style: Optional[Literal["full", "thumb", "wm"]] = None,
    ) -> bytes:
        """
        Download an image from a record field. GET /rest/image/... with optional style (full, thumb, watermark).

        Args:
            module: Document/module name.
            record_id: Record id.
            field_name: Field name holding the image.
            file_name: File name.
            style: None = full file; "thumb" = thumbnail; "wm" = watermark.

        Returns:
            Image content as bytes.
        """
        if style is not None:
            path = f"/rest/image/{style}/{module}/{record_id}/{field_name}/{file_name}"
        else:
            path = f"/rest/image/{module}/{record_id}/{field_name}/{file_name}"
        return await self._get(path, return_bytes=True)
