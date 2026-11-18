
import asyncio
import logging
from urllib.parse import urlparse

from curl_cffi.requests import AsyncSession

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class UnitLayoutAPIError(Exception):
    pass


class UnitLayoutConnector:

    def __init__(self):
        self.settings = get_settings()

    async def get_layout_plans(
        self,
        unit_id: str,
        access_token: str,
        user_id: str,
    ) -> list[dict]:

        if not unit_id or not access_token or not user_id:
            raise UnitLayoutAPIError(
                "Missing unit or authentication details."
            )

        base_url = self.settings.unit_layout_api_url.rstrip("/")

        if not base_url.startswith("https://"):
            raise UnitLayoutAPIError(
                "Unit layout API URL is not configured securely."
            )

        url = f"{base_url}/{unit_id}"

        headers = {
            "salesforce_access_token": access_token,
            "user_id": user_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            async with AsyncSession(
                impersonate="chrome",
                timeout=self.settings.unit_layout_timeout_seconds,
                allow_redirects=False,
            ) as session:
                response = await session.get(
                    url,
                    headers=headers,
                )

            if response.status_code != 200:
                raise UnitLayoutAPIError(
                    f"Layout API returned HTTP {response.status_code}"
                )

            body = response.json()

        except UnitLayoutAPIError:
            raise
        except Exception as exc:
            logger.exception("UNIT_LAYOUT_API_REQUEST_FAILED")
            raise UnitLayoutAPIError(
                "Unable to retrieve unit layout plans."
            ) from exc

        if not isinstance(body, dict):
            raise UnitLayoutAPIError("Invalid API response.")

        metadata = body.get("metaData") or {}

        if (
            str(metadata.get("status")).upper() != "SUCCESS"
            or str(metadata.get("statusCode")) != "200"
        ):
            raise UnitLayoutAPIError(
                "Unit layout API returned an unsuccessful response."
            )

        data = body.get("data")

        if not isinstance(data, dict) or data.get("success") is not True:
            raise UnitLayoutAPIError(
                "Invalid unit layout data."
            )

        raw_files = data.get("floorPlanFiles")

        if not isinstance(raw_files, list):
            raise UnitLayoutAPIError(
                "Invalid floorPlanFiles response."
            )

        files = []

        for item in raw_files:
            if not isinstance(item, dict):
                continue

            file_url = item.get("url")
            file_name = item.get("name")

            if not isinstance(file_url, str):
                continue

            parsed = urlparse(file_url)

            # Only return trusted Salesforce file URLs.
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or not (
                    parsed.hostname == "file.force.com"
                    or parsed.hostname.endswith(".file.force.com")
                )
                or parsed.username is not None
                or parsed.password is not None
            ):
                logger.warning("UNIT_LAYOUT_UNTRUSTED_FILE_URL")
                continue

            if not isinstance(file_name, str) or not file_name.strip():
                file_name = "Unit Layout Plan"

            files.append({
                "name": file_name.strip(),
                "download_url": file_url,
                "file_size_bytes": None,
            })

        # Size requests run concurrently, with a short timeout.
        if files:
            sizes = await asyncio.gather(
                *[
                    self._get_file_size(
                        file["download_url"]
                    )
                    for file in files
                ],
                return_exceptions=True,
            )

            for file, size in zip(files, sizes):
                if isinstance(size, int) and not isinstance(size, bool):
                    file["file_size_bytes"] = size

        return files

    async def _get_file_size(self, file_url: str) -> int | None:
        """
        Read Content-Length when available.

        Do not download the file merely to determine its size.
        Salesforce may reject HEAD requests.
        """

        try:
            async with AsyncSession(
                impersonate="chrome",
                timeout=self.settings.unit_layout_size_timeout_seconds,
                allow_redirects=False,
            ) as session:

                response = await session.head(
                    file_url,
                    headers={"Accept-Encoding": "identity"},
                )

            if response.status_code != 200:
                return None

            length = response.headers.get("Content-Length")

            if length is None:
                return None

            size = int(length)

            return size if size >= 0 else None

        except Exception:
            logger.debug("UNIT_LAYOUT_SIZE_UNAVAILABLE")
            return None
