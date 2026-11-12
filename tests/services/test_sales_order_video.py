"""Sales Order video shows with the workbook key "SalesOrder" (and "Sales Order")."""
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.services.how_to_video_service import HowToVideoService
from app.services.walkthrough_access_service import WalkthroughEngine

ENGINE = WalkthroughEngine(directory=Path("app/data/walkthrough"))
GUIDE = next(g for g in ENGINE.guides.values() if g.name.startswith("Sales Order"))

CACHE = {"data": {"howToVideos": [{
    "title": "How to view Sales Order",
    "allowed_roles": ["All"],
    "videos": [{"title": "Sales Order", "video_url": "https://youtu.be/abcdefghijk", "video_duration": "01:00"}],
}]}}


async def find(keys):
    redis = AsyncMock()
    redis.get.return_value = json.dumps(CACHE)
    return await HowToVideoService(redis).find_videos(
        feature_name=GUIDE.name, excel_feature_key=GUIDE.key, key_features=keys, role="RM")


def test_workbook_key_is_salesorder():
    assert GUIDE.key == "SalesOrder"


@pytest.mark.asyncio
@pytest.mark.parametrize("keys", ["SalesOrder", "salesorder", "Sales Order", "UDPage,SalesOrder"])
async def test_video_shows_with_sales_order_key(keys):
    assert len(await find(keys)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("keys", ["", None, "UDPage", "Sales", "SalesOfferEnable"])
async def test_video_hidden_without_sales_order_key(keys):
    assert await find(keys) == []
