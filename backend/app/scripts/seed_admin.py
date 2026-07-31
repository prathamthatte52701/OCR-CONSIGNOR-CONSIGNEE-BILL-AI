"""Idempotent admin-account seeder. Run: python -m app.scripts.seed_admin

Credentials come entirely from env vars (ADMIN_1_*/ADMIN_2_*) - never hardcoded here.
"""

import asyncio
from datetime import UTC, datetime

from app.core.config import settings
from app.core.database import close_mongo_connection, connect_to_mongo, get_database
from app.core.security import hash_password

ADMINS = [
    {
        "username": settings.admin_1_username,
        "email": settings.admin_1_email,
        "password": settings.admin_1_password,
    },
    {
        "username": settings.admin_2_username,
        "email": settings.admin_2_email,
        "password": settings.admin_2_password,
    },
]


async def seed() -> None:
    await connect_to_mongo()
    db = get_database()
    now = datetime.now(UTC)

    for admin in ADMINS:
        if not admin["email"] or not admin["password"] or not admin["username"]:
            print(f"Skipping incomplete admin entry (email={admin['email'] or '<unset>'})")
            continue

        email = admin["email"].strip().lower()
        existing = await db.users.find_one({"email": email})
        if existing is not None:
            print(f"Admin {email} already exists, skipping.")
            continue

        await db.users.insert_one(
            {
                "username": admin["username"],
                "email": email,
                "passwordHash": hash_password(admin["password"]),
                "role": "admin",
                "tokenVersion": 0,
                "createdAt": now,
                "updatedAt": now,
            }
        )
        print(f"Created admin: {email}")

    await close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(seed())
