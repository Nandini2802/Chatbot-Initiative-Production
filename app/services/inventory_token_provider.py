from functools import lru_cache

from app.core.config import get_settings
from app.services.inventory_token_service import (
    InventoryTokenService,
)


@lru_cache(maxsize=1)
def get_inventory_token_service() -> InventoryTokenService:

    settings = get_settings()

    if settings.environment != "local":
        raise RuntimeError(
            "Test Inventory credentials are restricted "
            "to the local environment"
        )

    return InventoryTokenService(
        token_url=settings.inventory_auth_url,
        client_id=settings.inventory_client_id,
        client_secret=settings.inventory_client_secret,
        cookie=settings.inventory_test_cookie or None,
    )