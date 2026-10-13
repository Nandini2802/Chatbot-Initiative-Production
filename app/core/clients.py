"""
Centralized client management for external services.

Responsibilities:
    - Create PostgreSQL engine
    - Create Redis client
    - Create Pinecone client
    - Reuse clients throughout the application
    - Close resources during application shutdown
"""

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    create_async_engine,
)

from redis.asyncio import Redis
from redis_entraid.cred_provider import (
    create_from_default_azure_credential,
)
from pinecone import Pinecone

from app.core.config import get_settings
from app.core.keyvault import (
    AppSecrets,
    load_application_secrets,
)


logger = logging.getLogger(__name__)


@dataclass
class ServiceClients:
    """
    Container holding initialized service clients.
    """

    postgres: AsyncEngine
    redis: Redis
    pinecone: Pinecone
    pinecone_index: Any


async def create_service_clients() -> ServiceClients:
    """
    Load credentials and initialize service clients.
    """

    settings = get_settings()

    # Step 1: Load secrets
    secrets: AppSecrets = await load_application_secrets()

    # Step 2: Initialize PostgreSQL
    postgres_engine = create_async_engine(
        secrets.postgres_url.get_secret_value(),
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )

    logger.info("PostgreSQL engine initialized")

    # Step 3: Initialize Redis
    redis_credential_provider = (
        create_from_default_azure_credential(
            ("https://redis.azure.com/.default",)
        )
    )

    # Initialize Azure Managed Redis
    redis_client = Redis(
        host=secrets.redis_host,
        port=secrets.redis_port,
        ssl=True,
        ssl_cert_reqs="required",
        credential_provider=redis_credential_provider,
        decode_responses=True,
        socket_connect_timeout=10,
        socket_timeout=10,
    )

    logger.info("Redis client initialized")

    # Step 4: Initialize Pinecone
    pinecone_client = Pinecone(
        api_key=secrets.pinecone_api_key.get_secret_value()
    )

    if not settings.pinecone_index_name:
        await redis_client.aclose()
        await postgres_engine.dispose()
        raise ValueError(
            "PINECONE_INDEX_NAME is not configured"
        )

    try:
        pinecone_index = pinecone_client.Index(
            settings.pinecone_index_name
        )
    except Exception:
        await redis_client.aclose()
        await postgres_engine.dispose()
        raise

    logger.info("Pinecone client initialized")

    return ServiceClients(
        postgres=postgres_engine,
        redis=redis_client,
        pinecone=pinecone_client,
        pinecone_index=pinecone_index,
    )


async def close_service_clients(
    clients: ServiceClients,
) -> None:
    """
    Close resources during application shutdown.
    """

    await clients.redis.aclose()
    await clients.postgres.dispose()

    logger.info("Redis and PostgreSQL resources closed")
