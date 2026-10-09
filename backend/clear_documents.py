"""One-off script to wipe the documents collection. Run manually, not part of the app.

Usage: ../venv/Scripts/python.exe clear_documents.py
"""

import asyncio

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings


async def main() -> None:
    client: AsyncIOMotorClient = AsyncIOMotorClient(settings.mongo_uri)
    db = client.get_default_database()
    result = await db.documents.delete_many({})
    print(f"Deleted {result.deleted_count} documents.")


if __name__ == "__main__":
    asyncio.run(main())
