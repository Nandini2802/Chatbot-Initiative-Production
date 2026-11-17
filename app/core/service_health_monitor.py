
import asyncio
import logging
import time

from curl_cffi.requests import AsyncSession

from app.core.startup_checks import (
    check_postgres,
    check_redis,
)
from app.observability.logger import audit_event
from app.core.config import get_settings


logger = logging.getLogger("app.health_monitor")


settings = get_settings()


async def _run_check(service, check):
    """Run one check, log its result, and return its status."""
    start = time.monotonic()
    status = "unhealthy"
    error_type = "none"

    try:
        success = await check()
        status = "healthy" if success else "unhealthy"

    except Exception as exc:
        error_type = type(exc).__name__
        logger.error(
            "SERVICE_HEALTH_CHECK_EXCEPTION | service=%s | type=%s",
            service,
            error_type,
        )

    duration_ms = round(
        (time.monotonic() - start) * 1000, 2
    )

    audit_event(
        "SERVICE_HEALTH_CHECK",
        service=service,
        status=status,
        healthy=(status == "healthy"),
        latency_ms=duration_ms,
        error_type=error_type,
    )

    return status


async def _check_foundry(client):
    """
    Test authentication, connectivity, and access to the
    configured Foundry endpoint without generating tokens.

    A successful models.list() only verifies the listing API.
    It does not guarantee a particular deployment can generate.
    """
    await client.models.list()
    return True



async def _check_middleware(name, url):
    """
    Check middleware health using its dedicated health API.

    Healthy when:
    1. HTTP status is 200
    2. Response JSON contains {"ok": true}
    """

    if not url.startswith("https://"):
        raise ValueError(
            "Middleware health URL must use HTTPS"
        )

    async with AsyncSession(
        impersonate="chrome",
        timeout=10,
    ) as session:

        response = await session.get(
            url,
            headers={
                "Accept": "application/json",
            },
            allow_redirects=False,
        )

        logger.info(
            "MIDDLEWARE_HEALTH_RESPONSE | service=%s | status_code=%s",
            name,
            response.status_code,
        )

        if response.status_code != 200:
            return False

        try:
            data = response.json()
        except ValueError:
            logger.error(
                "MIDDLEWARE_HEALTH_INVALID_JSON | service=%s",
                name,
            )
            return False

        return (
            isinstance(data, dict)
            and data.get("ok") is True
        )



async def check_all_services(clients):
    """
    Execute independent checks concurrently.

    A failed check never interrupts the chatbot.
    """

    async def postgres_check():
        return await check_postgres(clients) == "healthy"

    async def redis_check():
        return await check_redis(clients) == "healthy"

    checks = {
        "postgres": postgres_check,
        "redis": redis_check,
        "azure_openai_primary": lambda: _check_foundry(
            clients.foundry_openai.primary
        ),
        "azure_openai_secondary": lambda: _check_foundry(
            clients.foundry_openai.secondary
        ),
    }

    # Monitor one middleware endpoint
    middleware_url = (
        settings.monitor_middleware_inventory_url.strip()
    )

    print("Monitoring middleware URL:", middleware_url)

    if middleware_url:
        checks["middleware_inventory"] = (
            lambda: _check_middleware(
                "inventory",
                middleware_url,
            )
        )

    # Test override for safe UAT alert verification.
    forced_failures = {
        service.strip()
        for service in (
            settings.monitor_test_failure_service.split(",")
        )
        if service.strip()
    }
    

    async def execute(service, check):
        if service in forced_failures:
            async def simulated_failure():
                return False

            return await _run_check(
                service, simulated_failure
            )

        return await _run_check(service, check)

    services = list(checks.keys())

    results = await asyncio.gather(
        *[
            execute(service, checks[service])
            for service in services
        ]
    )

    statuses = dict(zip(services, results))

    # Report complete Foundry availability separately.
    primary_ok = (
        statuses["azure_openai_primary"] == "healthy"
    )
    secondary_ok = (
        statuses["azure_openai_secondary"] == "healthy"
    )

    await _run_check(
        "azure_openai_all",
        lambda: asyncio.sleep(
            0, result=(primary_ok or secondary_ok)
        ),
    )

    logger.info(
        "SERVICE_HEALTH_CYCLE_COMPLETED | checked=%s | failed=%s",
        len(statuses) + 1,
        sum(s != "healthy" for s in statuses.values())
        + (0 if primary_ok or secondary_ok else 1),
    )

    return statuses
