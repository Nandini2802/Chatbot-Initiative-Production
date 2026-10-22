import asyncio
import logging
import os
from typing import Any

from curl_cffi.requests import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException

logger = logging.getLogger(__name__)


class SalesforceClient:
    """Danube Inventory APIs. Use only authorized credentials and WAF access."""

    def __init__(self, http_client: AsyncSession | None = None):
        self.settings = get_settings()
        self.http_client = http_client

    async def _request(
        self,
        url: str,
        token: str,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        if not url or not url.startswith("https://"):
            raise AppException(
                "Inventory API URL is not configured securely",
                status_code=500,
                error_code="INVENTORY_CONFIGURATION_ERROR",
            )
        if not token or not token.strip():
            raise AppException(
                "Authentication token is required",
                status_code=401,
                error_code="AUTHENTICATION_ERROR",
            )

        headers = {
            "Authorization": f"Bearer {token.strip()}",
            "Accept": "*/*",
        }
        if user_id is not None:
            if not user_id.strip():
                raise AppException(
                    "Authenticated user ID is required",
                    status_code=401,
                    error_code="AUTHENTICATION_ERROR",
                )
            headers["user_id"] = user_id.strip()

        # Test-only cookie: never hardcode it or depend on it in production.
        cookie = os.getenv("INVENTORY_TEST_COOKIE", "").strip()
        if cookie:
            headers["Cookie"] = f"sess_map={cookie}"

        max_attempts = max(1, self.settings.inventory_max_retries)

        async def execute(session: AsyncSession) -> dict[str, Any]:
            for attempt in range(max_attempts):
                try:
                    response = await session.get(
                        url,
                        headers=headers,
                        timeout=self.settings.inventory_timeout_seconds,
                    )
                    if response.status_code in (401, 403):
                        raise AppException(
                            "Inventory authorization failed",
                            status_code=response.status_code,
                            error_code="INVENTORY_ACCESS_ERROR",
                        )

                    if response.status_code in (429, 502, 503, 504) and attempt < max_attempts - 1:
                        await asyncio.sleep(min(2 ** attempt, 4))
                        continue

                    if response.status_code >= 400:
                        logger.warning(
                            "INVENTORY_HTTP_FAILED | status=%s | endpoint=%s | content_type=%s",
                            response.status_code,
                            url.split("?")[0],
                            response.headers.get("content-type"),
                        )
                        raise AppException(
                            "Inventory service request failed",
                            status_code=502,
                            error_code="INVENTORY_UPSTREAM_ERROR",
                        )

                    try:
                        payload = response.json()
                    except ValueError as exc:
                        raise AppException(
                            "Inventory API returned invalid JSON",
                            status_code=502,
                            error_code="INVENTORY_RESPONSE_ERROR",
                        ) from exc

                    if not isinstance(payload, dict):
                        raise AppException(
                            "Unexpected inventory response",
                            status_code=502,
                            error_code="INVENTORY_RESPONSE_ERROR",
                        )

                    data = payload.get("data")
                    metadata = payload.get("metaData")
                    if not isinstance(data, dict):
                        raise AppException(
                            "Inventory response is missing data",
                            status_code=502,
                            error_code="INVENTORY_RESPONSE_ERROR",
                        )

                    if (
                        data.get("StatusCode") != 200
                        or data.get("Status") != "Success"
                        or not isinstance(metadata, dict)
                        or metadata.get("status") != "SUCCESS"
                        or metadata.get("statusCode") != 200
                    ):
                        raise AppException(
                            "Inventory API reported a failure",
                            status_code=502,
                            error_code="INVENTORY_UPSTREAM_ERROR",
                        )
                    return payload

                except AppException:
                    raise
                except Exception as exc:
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(min(2 ** attempt, 4))
                        continue
                    logger.warning(
                        "INVENTORY_TRANSPORT_FAILED | error_type=%s",
                        type(exc).__name__,
                    )
                    raise AppException(
                        "Inventory service is temporarily unavailable",
                        status_code=503,
                        error_code="INVENTORY_UPSTREAM_ERROR",
                    ) from exc

            raise AppException(
                "Inventory request failed after retries",
                status_code=503,
                error_code="INVENTORY_UPSTREAM_ERROR",
            )

        if self.http_client is not None:
            return await execute(self.http_client)

        async with AsyncSession(impersonate="chrome") as session:
            return await execute(session)

    async def get_active_projects(self, token: str) -> list[dict]:
        payload = await self._request(
            url=self.settings.inventory_project_api_url,
            token=token,
        )
        projects = payload["data"].get("ActiveProjects")
        if not isinstance(projects, list) or not all(isinstance(p, dict) for p in projects):
            raise AppException(
                "ActiveProjects is missing or invalid",
                status_code=502,
                error_code="INVENTORY_RESPONSE_ERROR",
            )
        logger.info("ACTIVE_PROJECTS_FETCHED | count=%s", len(projects))
        return projects

    async def get_visible_units(self, token: str, user_id: str) -> list[dict]:
        payload = await self._request(
            url=self.settings.inventory_units_api_url,
            token=token,
            user_id=user_id,
        )
        units = payload["data"].get("Units")
        if not isinstance(units, list) or not all(isinstance(u, dict) for u in units):
            raise AppException(
                "Units is missing or invalid",
                status_code=502,
                error_code="INVENTORY_RESPONSE_ERROR",
            )
        logger.info("VISIBLE_UNITS_FETCHED | count=%s", len(units))
        return units
