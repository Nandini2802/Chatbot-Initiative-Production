
import os
import httpx


class ProjectCoordinatesConnector:

    def __init__(self):
        self.api_url = os.getenv(
            "PROJECT_COORDINATES_API_URL"
        )

    async def fetch_coordinates(
        self,
        project_id: str,
        access_token: str,
    ):
        if not self.api_url:
            raise ValueError(
                "PROJECT_COORDINATES_API_URL is missing"
            )

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(
            timeout=20
        ) as client:

            response = await client.get(
                self.api_url,
                params={
                    "project_id": project_id
                },
                headers=headers,
            )

            response.raise_for_status()

            payload = response.json()

        data = payload.get("data")

        # Support a single record or a one-item list.
        if isinstance(data, list):
            data = data[0] if data else None

        if not isinstance(data, dict):
            return None

        latitude = data.get(
            "LatitudeLongitude__Latitude__s"
        )

        longitude = data.get(
            "LatitudeLongitude__Longitude__s"
        )

        if latitude is None or longitude is None:
            return None

        return {
            "latitude": float(latitude),
            "longitude": float(longitude),
        }
