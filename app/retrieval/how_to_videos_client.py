
"""Fetch Danube How-To Videos through curl_cffi."""

import logging

from curl_cffi.requests import AsyncSession

from app.core.config import get_settings


logger = logging.getLogger(__name__)


class HowToVideosAPIClient:

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.settings = get_settings()

    async def fetch_videos(self) -> dict:

        if not self.api_key:
            raise ValueError(
                "HOW_TO_VIDEOS_API_KEY is missing"
            )

        url = self.settings.how_to_videos_api_url

        if not url.startswith("https://"):
            raise ValueError(
                "How-To Videos API must use HTTPS"
            )

        async with AsyncSession(
            timeout=self.settings.how_to_videos_timeout_seconds,
        ) as session:

            response = await session.post(
                url,
                headers={
                    "x_api_key": self.api_key,
                    "Accept": "application/json",
                },
                data="",
                allow_redirects=False,
            )

            response.raise_for_status()
            payload = response.json()

        if not isinstance(payload, dict):
            raise ValueError("Invalid API response")

        metadata = payload.get("metaData") or {}

        if metadata.get("status") != "SUCCESS":
            raise ValueError(
                "How-To Videos API did not return SUCCESS"
            )

        data = payload.get("data")

        if not isinstance(data, dict):
            raise ValueError("Missing data object")

        videos = data.get("howToVideos")

        if not isinstance(videos, list):
            raise ValueError(
                "howToVideos must be a list"
            )

        logger.info(
            "HOW_TO_VIDEOS_FETCH_SUCCESS | count=%s",
            len(videos),
        )

        return payload
