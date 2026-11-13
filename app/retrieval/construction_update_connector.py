
import logging
from urllib.parse import urlparse

from curl_cffi.requests import AsyncSession

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class ConstructionUpdateConnector:

    def __init__(self):
        self.settings = get_settings()

    async def fetch_construction_url(
        self,
        osf_project_id: str,
    ) -> str | None:

        url = self.settings.construction_update_api_url

        if not url.startswith("https://"):
            raise ValueError(
                "Construction Update API URL is invalid"
            )

        if not str(osf_project_id).isdigit():
            raise ValueError("Invalid OSF project ID")

        async with AsyncSession(
            impersonate="chrome"
        ) as session:

            response = await session.post(
                url,
                params={
                    "project_Id": str(osf_project_id)
                },
                headers={
                    "Accept": "application/json"
                },
                data="",
                timeout=(
                    self.settings
                    .construction_update_timeout_seconds
                ),
                allow_redirects=False,
            )

        response.raise_for_status()

        payload = response.json()

        if not isinstance(payload, dict):
            raise ValueError(
                "Invalid construction API response"
            )

        metadata = payload.get("metaData") or {}

        if (
            metadata.get("status") != "SUCCESS"
            or str(metadata.get("statusCode")) != "200"
        ):
            raise ValueError(
                "Construction API unsuccessful"
            )

        data = payload.get("data") or {}

        if not isinstance(data, dict):
            raise ValueError(
                "Invalid construction API data"
            )

        if str(data.get("projectId") or "") != str(osf_project_id):
            raise ValueError(
                "Construction API project ID mismatch"
            )

        construction_url = str(
            data.get("construction_update_url") or ""
        ).strip()

        if not construction_url:
            return None

        parsed = urlparse(construction_url)
        hostname = (parsed.hostname or "").lower()

        allowed_domain = (
            hostname == "danubeproperties.com"
            or hostname.endswith(".danubeproperties.com")
        )

        if (
            parsed.scheme != "https"
            or not allowed_domain
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
        ):
            raise ValueError(
                "Unapproved construction URL"
            )

        logger.info(
            "CONSTRUCTION_URL_FOUND | osf_id=%s",
            osf_project_id,
        )

        return construction_url
