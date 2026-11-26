import logging

from urllib.parse import quote

from curl_cffi.requests import AsyncSession

from app.core.config import get_settings
from app.core.middleware_headers import build_middleware_headers


logger = logging.getLogger(__name__)


class ProjectCoordinatesConnector:

    def __init__(self):
        self.settings = get_settings()

    async def fetch_project_details(
        self,
        project_id: str,
    ) -> dict:

        base_url = (
            self.settings.project_coordinates_api_url
            .rstrip("/")
        )

        if not base_url.startswith("https://"):
            raise ValueError(
                "PROJECT_COORDINATES_API_URL is invalid"
            )

        if not project_id or not str(project_id).strip():
            raise ValueError("Project ID is required")

        project_id = str(project_id).strip()

        url = (
            f"{base_url}/"
            f"{quote(project_id, safe='')}"
        )

        # Reuse the existing middleware authentication headers.
        headers = build_middleware_headers({
            "Accept": "application/json",
        })

        logger.info(
            "PROJECT_DETAILS_FETCH_STARTED | project_id=%s",
            project_id,
        )

        async with AsyncSession(
            impersonate="chrome"
        ) as session:

            response = await session.get(
                url,
                headers=headers,
                timeout=30,
                allow_redirects=False,
            )

        response.raise_for_status()

        payload = response.json()

        if not isinstance(payload, dict):
            raise ValueError(
                "Invalid Project Details API response"
            )

        metadata = payload.get("metaData") or {}

        if (
            metadata.get("status") != "SUCCESS"
            or str(metadata.get("statusCode")) != "200"
        ):
            raise ValueError(
                "Project Details API returned failure"
            )

        data = payload.get("data")

        if not isinstance(data, dict):
            raise ValueError(
                "Project Details API data is invalid"
            )

        if str(data.get("Id")) != project_id:
            raise ValueError(
                "Project Details API returned a different project"
            )

        logger.info(
            "PROJECT_DETAILS_FETCH_COMPLETED | "
            "project_id=%s | project_name=%s",
            project_id,
            data.get("Name"),
        )

        return data

    async def fetch_coordinates(
        self,
        project_id: str,
        access_token: str,
    ):

        if not project_id or not access_token:
            raise ValueError(
                "Project ID and Salesforce token are required"
            )

        data = await self.fetch_project_details(
            project_id=project_id,
        )

        latitude = data.get(
            "LatitudeLongitude__Latitude__s"
        )

        longitude = data.get(
            "LatitudeLongitude__Longitude__s"
        )

        if latitude is None or longitude is None:
            logger.info(
                "PROJECT_COORDINATES_MISSING | project_id=%s",
                project_id,
            )
            return None

        return {
            "latitude": float(latitude),
            "longitude": float(longitude),
        }