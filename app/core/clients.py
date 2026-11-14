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

from redis.asyncio import RedisCluster
from redis_entraid.cred_provider import (
    create_from_default_azure_credential,
)
from pinecone import Pinecone
from openai import AsyncOpenAI
from app.core.foundry_failover import FoundryFailoverClient
from functools import partial

from app.core.config import get_settings
from app.core.keyvault import (
    AppSecrets,
    load_application_secrets,
)


logger = logging.getLogger(__name__)

def remap_redis_node_address(
    address: tuple[str, int],
    redis_hostname: str,
    internal_hosts: frozenset[str] = frozenset({"51.11.255.75"}),
) -> tuple[str, int]:
    host, port = address

    if host in internal_hosts:
        return redis_hostname, port

    return address


@dataclass
class ServiceClients:
    """
    Container holding initialized service clients.
    """

    postgres: AsyncEngine
    redis: RedisCluster
    pinecone: Pinecone
    pinecone_index: Any
    foundry_openai: FoundryFailoverClient


async def create_service_clients(
        secrets: AppSecrets,
) -> ServiceClients:
    """
    Load credentials and initialize service clients.
    """

    settings = get_settings()


    # Step 1: Initialize PostgreSQL
    postgres_engine = create_async_engine(
        secrets.postgres_url.get_secret_value(),
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )

    logger.info("PostgreSQL engine initialized")

    # Step 2: Initialize Redis
    redis_credential_provider = (
        create_from_default_azure_credential(
            ("https://redis.azure.com/.default",)
        )
    )

    redis_client = RedisCluster(
        host=secrets.redis_host,
        port=secrets.redis_port,
        ssl=True,
        ssl_cert_reqs="required",
        ssl_check_hostname=True,
        credential_provider=redis_credential_provider,
        decode_responses=True,
        socket_connect_timeout=10,
        socket_timeout=10,
        address_remap=partial(
            remap_redis_node_address,
            redis_hostname=secrets.redis_host,
        ),
    )

    try:
        await redis_client.initialize()

        logger.info("Redis Cluster client initialized")

        await redis_client.ping()

        logger.info("Redis client initialized")

    except Exception:
        logger.exception(
            "REDIS_CONNECTION_FAILURE | stage=startup | status=unhealthy"
        )
        raise

    # Step 3: Initialize Pinecone
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
    
    # Step 4: Initialize Microsoft Foundry clients

    if not settings.foundry_openai_base_url:
        await redis_client.aclose()
        await postgres_engine.dispose()
        raise ValueError(
            "FOUNDRY_OPENAI_BASE_URL is not configured"
        )

    if not settings.foundry_openai_secondary_base_url:
        await redis_client.aclose()
        await postgres_engine.dispose()
        raise ValueError(
            "FOUNDRY_OPENAI_SECONDARY_BASE_URL is not configured"
        )

    # Primary Microsoft Foundry deployment
    primary_foundry_client = AsyncOpenAI(
        base_url=settings.foundry_openai_base_url,
        api_key=(
            secrets.foundry_openai_api_key.get_secret_value()
        ),
        timeout=settings.foundry_openai_timeout_seconds,
        max_retries=0,
    )

    # Secondary Microsoft Foundry deployment
    secondary_foundry_client = AsyncOpenAI(
        base_url=settings.foundry_openai_secondary_base_url,
        api_key=(
            secrets.foundry_openai_secondary_api_key
            .get_secret_value()
        ),
        timeout=settings.foundry_openai_timeout_seconds,
        max_retries=0,
    )

    # Shared client with automatic HTTP 429 failover
    foundry_client = FoundryFailoverClient(
        primary=primary_foundry_client,
        secondary=secondary_foundry_client,
    )

    logger.info(
        "Microsoft Foundry primary and secondary "
        "clients initialized with HTTP 429 failover"
    )

    return ServiceClients(
        postgres=postgres_engine,
        redis=redis_client,
        pinecone=pinecone_client,
        pinecone_index=pinecone_index,
        foundry_openai=foundry_client,
    )


async def close_service_clients(
    clients: ServiceClients,
) -> None:

    try:
        await clients.foundry_openai.close()
    finally:
        try:
            await clients.redis.aclose()
        finally:
            await clients.postgres.dispose()

    logger.info("External service clients closed")
