"""Thin async wrapper around Motor's GridFS bucket - upload/download/delete only."""

from bson import ObjectId
from gridfs.errors import NoFile

from app.core.database import get_gridfs


async def upload_buffer(data: bytes, filename: str, content_type: str) -> ObjectId:
    gridfs = get_gridfs()
    file_id = await gridfs.upload_from_stream(
        filename, data, metadata={"contentType": content_type}
    )
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
