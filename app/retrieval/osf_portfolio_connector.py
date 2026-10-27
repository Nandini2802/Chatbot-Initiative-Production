
import logging
import json

from curl_cffi.requests import AsyncSession
from pathlib import Path

from app.core.config import get_settings
from app.core.keyvault import load_application_secrets

logger = logging.getLogger(__name__)


class OSFPortfolioConnector:

    def __init__(self):
        self.settings = get_settings()

    async def fetch_portfolio(self) -> list[dict]:
        url = self.settings.osf_portfolio_api_url

        if not url.startswith("https://"):
            raise ValueError("OSF Portfolio URL is invalid")

        secrets = await load_application_secrets()
        api_key = (
            secrets.osf_portfolio_api_key.get_secret_value()
        )

        if not api_key:
            raise ValueError("OSF Portfolio API key missing")

        headers = {
            "x_api_key": api_key,
            "Accept": "application/json",
        }

        async with AsyncSession(
            impersonate="chrome"
        ) as session:

            response = await session.get(
                url,
                headers=headers,
                timeout=self.settings.osf_portfolio_timeout_seconds,
                allow_redirects=False,
            )

            print("response", response, "status_code", response.status_code, "text", response.text)

        response.raise_for_status()

        try:
            payload = json.loads(response.text)

            debug_file = (
                Path(__file__).resolve().parents[2]
                / "logs"
                / "project_maps.txt"
            )

            debug_file.parent.mkdir(parents=True, exist_ok=True)

            with debug_file.open("a", encoding="utf-8") as file:

                file.write("\n========== OSF API RESPONSE ==========\n")

                file.write(
                    f"RESPONSE TYPE: {type(payload).__name__}\n"
                )

                if isinstance(payload, dict):

                    file.write(
                        f"TOP LEVEL KEYS: {list(payload.keys())}\n"
                    )

                    file.write(
                        f"API STATUS: {payload.get('metaData', {}).get('status')}\n"
                    )

                    projects = payload.get("data", [])

                    file.write(
                        f"TOTAL PROJECTS: {len(projects) if isinstance(projects, list) else 'INVALID DATA TYPE'}\n"
                    )

                    if isinstance(projects, list):

                        for project in projects:

                            if not isinstance(project, dict):
                                continue

                            title = str(project.get("title") or "")
                            name = str(project.get("name") or "")

                            if not any(
                                keyword in f"{title} {name}".casefold()
                                for keyword in ("greenz", "shahrukhz")
                            ):
                                continue

                            meta = project.get("meta") or {}

                            file.write(
                                "\n---------------------------------\n"
                            )

                            file.write(
                                f"PROJECT TITLE: {title}\n"
                                f"PROJECT NAME: {name}\n"
                            )

                            if isinstance(meta, dict):

                                file.write(
                                    f"META KEYS: {list(meta.keys())}\n"
                                )

                                file.write(
                                    f"GOOGLE MAP DATA: {meta.get('danube_google_map_address')}\n"
                                )

                            else:
                                file.write(
                                    f"META TYPE: {type(meta).__name__}\n"
                                )

                file.write("\n========== END OSF DEBUG ==========\n")

        except json.JSONDecodeError:
            raise ValueError(
                "OSF API did not return valid JSON. "
                f"Status: {response.status_code}, "
                f"Content-Type: {response.headers.get('Content-Type')}"
            )

        if not isinstance(payload, dict):
            raise ValueError("Invalid OSF response")

        metadata = payload.get("metaData") or {}

        if (
            metadata.get("status") != "SUCCESS"
            or str(metadata.get("statusCode")) != "200"
        ):
            raise ValueError("OSF API unsuccessful")

        projects = payload.get("data")

        if not isinstance(projects, list):
            raise ValueError("OSF data is not a list")

        logger.info(
            "OSF_PORTFOLIO_FETCHED | count=%s",
            len(projects),
        )

        return [
            item for item in projects
            if isinstance(item, dict)
        ]
