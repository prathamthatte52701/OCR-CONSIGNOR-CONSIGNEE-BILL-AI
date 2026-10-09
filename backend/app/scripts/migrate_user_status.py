"""One-off, idempotent: stamps status="approved" on every pre-approval-era user that has no
status field. Run: python -m app.scripts.migrate_user_status [--dry-run]

Not required for correctness - a missing status already counts as approved everywhere - but
makes the stored data explicit. Users that already have a status are never touched.
"""

import asyncio
import sys

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import close_mongo_connection, connect_to_mongo, get_database


async def migrate(dry_run: bool = False, db: AsyncIOMotorDatabase | None = None) -> int:
    """`db` is for tests (a handle bound to the caller's event loop); the CLI uses the app's."""
    db = db if db is not None else get_database()
    query = {"status": {"$exists": False}}
    if dry_run:
        return await db.users.count_documents(query)
    result = await db.users.update_many(query, {"$set": {"status": "approved"}})
    return result.modified_count


async def _main(dry_run: bool) -> None:
    await connect_to_mongo()
    count = await migrate(dry_run=dry_run)
    print(f"{'Would update' if dry_run else 'Updated'} {count} user(s).")
    await close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(_main("--dry-run" in sys.argv))
