"""Seed canonical data, generate a schedule, and approve it idempotently."""

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.services.operational_seed_service import seed_and_publish_operational_scenarios


async def _main() -> None:
    engine = create_async_engine(str(settings.DATABASE_URL))
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with sessions() as session:
            payload = await seed_and_publish_operational_scenarios(session)
        print(payload["signature"])
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
