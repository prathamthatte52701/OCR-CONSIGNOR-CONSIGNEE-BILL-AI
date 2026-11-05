"""Thin async wrapper around Motor's GridFS bucket - upload/download/delete only."""

import asyncio
import contextlib

from bson import ObjectId
from gridfs.errors import NoFile

from app.core.database import get_gridfs


async def upload_buffer(data: bytes, filename: str, content_type: str) -> ObjectId:
    gridfs = get_gridfs()
    # GridFS does NOT abort a failed upload (it only marks the stream closed), so chunks already
    # written would stay behind with no files row. Pre-generate the id to be able to sweep them.
    file_id = ObjectId()
    try:
        await gridfs.upload_from_stream_with_id(
            file_id, filename, data, metadata={"contentType": content_type}
        )
    except BaseException:
        with contextlib.suppress(Exception):
            await asyncio.shield(delete_file(file_id))  # removes chunks even without a files row
        raise
    return file_id


async def download_buffer(file_id: ObjectId) -> bytes:
    gridfs = get_gridfs()
    stream = await gridfs.open_download_stream(file_id)
    return await stream.read()


async def delete_file(file_id: ObjectId) -> None:
    gridfs = get_gridfs()
    try:
        await gridfs.delete(file_id)
    except NoFile:
        pass


async def get_file_length(file_id: ObjectId) -> int:
    """Stored size in bytes (reads only the files-collection row, not the chunks)."""
    stream = await get_gridfs().open_download_stream(file_id)
    return int(stream.length)
