"""Однократная загрузка демо-данных при развёртывании: python -m app.seed.run (выполняется до запуска API)."""
import asyncio

from app.db import SessionLocal, engine
from app.seed.loader import seed_if_empty


async def main():
    async with SessionLocal() as session:
        await seed_if_empty(session)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
