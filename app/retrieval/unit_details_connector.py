
import logging
import math
from urllib.parse import quote

from curl_cffi.requests import AsyncSession

from app.core.config import get_settings
from app.core.middleware_headers import build_middleware_headers


logger = logging.getLogger(__name__)


class UnitDetailsAPIError(Exception):
    pass


class UnitDetailsConnector:

    def __init__(self):
        settings = get_settings()

        self.base_url = settings.unit_details_api_url.rstrip("/")
        self.timeout = settings.unit_details_timeout_seconds

        if not self.base_url.startswith("https://"):
            raise ValueError(
                "UNIT_DETAILS_API_URL must use HTTPS"
            )

    @staticmethod
    def _number(value):
        if value is None or isinstance(value, bool):
            return None

        try:
            number = float(value)
            return number if math.isfinite(number) else None
        except (TypeError, ValueError):
            return None

    async def get_unit_areas(
        self,
        unit_id: str,
    ) -> dict:

        if not unit_id:
            raise UnitDetailsAPIError(
                "Salesforce unit ID is missing"
            )

        # Encode the ID as a single URL path segment.
        encoded_id = quote(str(unit_id), safe="")
        url = f"{self.base_url}/{encoded_id}"

        # Uses the authenticated request context.
        headers = build_middleware_headers({
            "Accept": "application/json",
        })

        try:
            async with AsyncSession(
                impersonate="chrome",
                timeout=self.timeout,
                allow_redirects=False,
            ) as session:

                response = await session.get(
                    url,
                    headers=headers,
                )

            if response.status_code != 200:
                raise UnitDetailsAPIError(
                    f"Unit API returned HTTP {response.status_code}"
                )

            body = response.json()

        except UnitDetailsAPIError:
            raise
        except Exception as exc:
            logger.warning(
                "UNIT_DETAILS_API_REQUEST_FAILED | error_type=%s",
                type(exc).__name__,
            )
            raise UnitDetailsAPIError(
                "Unable to retrieve unit areas"
            ) from exc

        if not isinstance(body, dict):
            raise UnitDetailsAPIError(
                "Invalid unit API response"
            )

        metadata = body.get("metaData")

        if not isinstance(metadata, dict):
            raise UnitDetailsAPIError(
                "Missing unit API metadata"
            )

        if (
            str(metadata.get("status")).upper() != "SUCCESS"
            or str(metadata.get("statusCode")) != "200"
        ):
            raise UnitDetailsAPIError(
                "Unit API returned an unsuccessful response"
            )

        data = body.get("data")

        if not isinstance(data, dict):
            raise UnitDetailsAPIError(
                "Invalid unit API data"
            )

        return {
            "area_sqft": self._number(
                data.get("Total_Saleable_Area_In_Sq_Ft__c")
            ),
            "internal_saleable_area": self._number(
                data.get("Internal_Saleable_Area__c")
            ),
            "balcony_area_sqm": self._number(
                data.get("Balcony_Area_Sq_Mt_New__c")
            ),
        }
