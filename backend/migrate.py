"""Usage: python migrate.py   (applies pending migrations to DATABASE_URL)"""
import asyncio
import sys

from app import config
from app.db import SchemaError, create_pool, migrate


async def main() -> int:
    pool = await create_pool(config.DATABASE_URL)
    try:
        done = await migrate(pool)
    except SchemaError as e:   # a table the platform owns is not what Vista needs: say so plainly, nothing half applied
        print("NOT MIGRATED:", e, file=sys.stderr)
        return 1
    finally:
        await pool.close()
    print("applied:", done or "nothing, already up to date")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
