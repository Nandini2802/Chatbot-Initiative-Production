
import logging

from app.services.api_cache_service import APICacheService
from app.persistence.redis_store import RedisCacheKeys

logger = logging.getLogger(__name__)


class ProjectCatalogService:

    def __init__(self, redis_client):
        self.cache = APICacheService(redis_client)

    async def get_project_names(self) -> list[str]:

        cached = await self.cache.get(
            RedisCacheKeys.MARKETING_CATALOG
        )

        print("\n========== CATALOG CACHE DEBUG ==========", flush=True)

        print(
            f"[CACHE DEBUG] Cached value type: {type(cached).__name__}",
            flush=True,
        )

        if cached is None:
            print("[CACHE DEBUG] Cached value is None", flush=True)

        elif isinstance(cached, dict):
            print(
                f"[CACHE DEBUG] Top-level keys: {list(cached.keys())}",
                flush=True,
            )

            data = cached.get("data")

            print(
                f"[CACHE DEBUG] data type: {type(data).__name__}",
                flush=True,
            )

            if isinstance(data, dict):
                print(
                    f"[CACHE DEBUG] data keys: {list(data.keys())}",
                    flush=True,
                )

                nested_data = data.get("data")

                if isinstance(nested_data, dict):
                    print(
                        f"[CACHE DEBUG] nested data keys: {list(nested_data.keys())}",
                        flush=True,
                    )

        else:
            print(
                "[CACHE DEBUG] Unexpected cached value type",
                flush=True,
            )

        print("=========================================\n", flush=True)

        if not isinstance(cached, dict):
            logger.warning("MARKETING_CATALOG_NOT_FOUND")
            return []

        # Handle the cached response structure.
        data = cached.get("data", {})

        if not isinstance(data, dict):
            return []

        # Some cache wrappers store the original
        # API response inside another data object.
        if (
            "marketingCollateral" not in data
            and isinstance(data.get("data"), dict)
        ):
            data = data["data"]

        projects = data.get(
            "marketingCollateral", []
        )

        print(
            f"[CATALOG DEBUG] marketingCollateral type: {type(projects).__name__}",
            flush=True,
        )

        if isinstance(projects, list):
            print(
                f"[CATALOG DEBUG] Number of collateral records: {len(projects)}",
                flush=True,
            )

            if projects and isinstance(projects[0], dict):
                print(
                    f"[CATALOG DEBUG] First record keys: {list(projects[0].keys())}",
                    flush=True,
                )

        names = {
            item["project_title"].strip()
            for item in projects
            if isinstance(item, dict)
            and isinstance(item.get("project_title"), str)
            and item["project_title"].strip()
        }

        result = sorted(names)

        logger.info(
            "PROJECT_CATALOG_LOADED | count=%s",
            len(result),
        )

        return result
