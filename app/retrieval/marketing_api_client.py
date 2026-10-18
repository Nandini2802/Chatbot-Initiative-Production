
import logging
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class MarketingAPIClient:

    def __init__(
        self,
        api_key: str,
        http_client: httpx.AsyncClient | None = None,
    ):
        self.settings = get_settings()
        self.api_key = api_key
        self.http_client = http_client

    async def fetch_catalog(self) -> Any:
        """
        Fetch the complete Marketing API response.
        """

        if not self.settings.marketing_api_url:
            raise ValueError(
                "Marketing API URL is not configured"
            )

        headers = {
            "x_api_key": self.api_key,
            "product_name": (
                self.settings.marketing_product_name
            ),
            "product_feature_name": (
                self.settings.marketing_product_feature_name
            ),
        }

        logger.info(
            "MARKETING_API_REQUEST_STARTED"
        )

        async def make_request(
            client: httpx.AsyncClient,
        ) -> Any:

            response = await client.post(
                self.settings.marketing_api_url,
                headers=headers,
                timeout=60.0,
            )

            response.raise_for_status()

            data = response.json()

            if data is None or data == {} or data == []:
                raise ValueError(
                    "Marketing API returned empty data"
                )

            logger.info(
                "MARKETING_API_REQUEST_SUCCESS | status=%s",
                response.status_code,
            )

            return data

        try:
            if self.http_client is not None:
                return await make_request(
                    self.http_client
                )

            async with httpx.AsyncClient() as client:
                return await make_request(client)

        except Exception:
            logger.exception(
                "MARKETING_API_REQUEST_FAILED"
            )
            raise
