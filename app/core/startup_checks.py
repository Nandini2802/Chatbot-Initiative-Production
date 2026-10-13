
"""
Connectivity checks for external services.

Responsibilities:
    - Verify PostgreSQL connectivity
    - Verify Redis connectivity
    - Verify Pinecone index accessibility
    - Return dependency health status
"""

import asyncio
import logging

from sqlalchemy import text

from app.core.clients import ServiceClients
from app.core.config import get_settings

logger = logging.getLogger(__name__)


async def check_postgres(clients: ServiceClients) -> str:
    try:
        async with clients.postgres.connect() as connection:
            await connection.execute(text("SELECT 1"))

        return "healthy"

    except Exception:
        logger.exception("PostgreSQL connectivity check failed")
        return "unhealthy"


async def check_redis(clients: ServiceClients) -> str:
    try:
        await clients.redis.ping()
        return "healthy"

    except Exception:
        logger.exception("Redis connectivity check failed")
        return "unhealthy"


async def check_pinecone(clients: ServiceClients) -> str:
    try:
        settings = get_settings()

        await asyncio.to_thread(
            clients.pinecone.describe_index,
            settings.pinecone_index_name,
        )

        return "healthy"

    except Exception:
        logger.exception("Pinecone connectivity check failed")
        return "unhealthy"


async def run_startup_checks(
    clients: ServiceClients,
) -> dict[str, str]:

    results = await asyncio.gather(
        check_postgres(clients),
        check_redis(clients),
        check_pinecone(clients),
    )

    return dict(
        zip(
            ("postgres", "redis", "pinecone"),
            results,
        )
    )
