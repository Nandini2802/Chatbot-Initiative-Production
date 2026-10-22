
import asyncio
import logging

from app.retrieval.salesforce_client import SalesforceClient
from app.retrieval.inventory_normalizer import (
    normalize_project,
    normalize_unit,
)
from app.schemas.retrieval import InventorySnapshot


logger = logging.getLogger(__name__)


class InventoryConnector:

    def __init__(
        self,
        salesforce_client: SalesforceClient,
    ):
        self.salesforce_client = salesforce_client

    async def fetch_inventory(
        self,
        token: str,
        user_id: str,
    ) -> InventorySnapshot:

        logger.info("INVENTORY_FETCH_STARTED")

        raw_projects, raw_units = await asyncio.gather(
            self.salesforce_client.get_active_projects(token),
            self.salesforce_client.get_visible_units(
                token=token,
                user_id=user_id,
            ),
        )

        projects = [
            normalize_project(item)
            for item in raw_projects
        ]

        units = [
            normalize_unit(item)
            for item in raw_units
        ]

        # Reject incomplete records instead of silently
        # introducing invalid project/unit identifiers.
        projects = [
            item for item in projects
            if item.project_name.strip()
        ]

        units = [
            item for item in units
            if item.unit_name.strip()
            and item.project_name.strip()
        ]

        snapshot = InventorySnapshot(
            projects=projects,
            units=units,
        )

        logger.info(
            "INVENTORY_FETCH_COMPLETED | "
            "projects=%s | units=%s",
            len(projects),
            len(units),
        )

        return snapshot
