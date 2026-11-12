"""
Daily Activity Report vs DAR Analytics: keys and how-to videos.

- Daily Activity Report opens with ANY of the keys in its workbook cell
  ("DARView,DARCreate"); DAR Analytics needs DarAnalytics. Neither opens the other.
- The Daily Activity Report video follows the same keys.
"""
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.services.how_to_video_service import HowToVideoService
from app.services.walkthrough_access_service import WalkthroughEngine

ENGINE = WalkthroughEngine(directory=Path("app/data/walkthrough"))
DAILY = "Daily Activity Report"
ANALYTICS = "DAR Analytics"

CACHE = {"data": {"howToVideos": [{
    "title": "Daily Activity Report",
    "allowed_roles": ["All"],
    "videos": [{"title": "DAR", "video_url": "https://youtu.be/abcdefghijk", "video_duration": "01:00"}],
}]}}


def service():
    redis = AsyncMock()
    redis.get.return_value = json.dumps(CACHE)
    return HowToVideoService(redis)


@pytest.mark.parametrize("keys", [
    "DARCreate", "darcreate", "DAR_Create", "DARView", "dar view",
    "UDPage,DARCreate,HowToVideos", "DARCreate,DARView", "UDPage,DARView",
])
def test_daily_activity_report_opens_with_either_key(keys):
    assert ENGINE.permission(DAILY, keys) == (True, "feature_key_verified")


@pytest.mark.parametrize("keys", [
    None, "", "DarAnalytics", "DAR", "View", "Create",
    "DAR Dashboard", "DARdashboard", "UDPage,CompareUnit",
])
def test_daily_activity_report_denied_without_its_keys(keys):
    assert ENGINE.permission(DAILY, keys) == (False, "feature_key_not_granted")


def test_dar_analytics_still_needs_its_own_key():
    assert ENGINE.permission(ANALYTICS, "DarAnalytics") == (True, "feature_key_verified")
    assert ENGINE.permission(ANALYTICS, "DARCreate") == (False, "feature_key_not_granted")
    assert ENGINE.permission(ANALYTICS, "DARView") == (False, "feature_key_not_granted")


def test_other_walkthroughs_keep_all_keys_rule():
    # "LeadTab/LeadAdd" still needs both.
    assert ENGINE.permission("Create Lead", "LeadTab") == (False, "feature_key_not_granted")
    assert ENGINE.permission("Create Lead", "LeadTab,LeadAdd") == (True, "feature_key_verified")


def test_required_keys_come_from_the_workbook_cell():
    assert ENGINE.guides[DAILY.casefold()].key == "DARView,DARCreate"
    assert ENGINE.required_keys(DAILY) == ["darview", "darcreate"]


def test_any_of_keys_follow_the_workbook(tmp_path):
    # Editing the workbook cell changes the accepted keys; no code change.
    from openpyxl import Workbook
    from app.services.walkthrough_access_service import WALKTHROUGH_FILE

    book = Workbook()
    sheet = book.active
    sheet.append(["#", "Feature Name", "Steps", "Feature Key"])
    sheet.append([1, "Daily Activity Report", "steps", "DARNew/DARView"])
    book.save(tmp_path / WALKTHROUGH_FILE)

    engine = WalkthroughEngine(directory=tmp_path)
    assert engine.permission(DAILY, "DARNew")[0] is True
    assert engine.permission(DAILY, "DARView")[0] is True
    assert engine.permission(DAILY, "DARCreate")[0] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("keys", ["DARCreate", "DARView", "UDPage,DARCreate"])
async def test_daily_activity_report_video_shows_for_either_key(keys):
    guide = ENGINE.guides[DAILY.casefold()]
    videos = await service().find_videos(
        feature_name=guide.name, excel_feature_key=guide.key, key_features=keys, role="RM")
    assert len(videos) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("keys", ["DarAnalytics", "UDPage", ""])
async def test_daily_activity_report_video_hidden_without_its_keys(keys):
    guide = ENGINE.guides[DAILY.casefold()]
    videos = await service().find_videos(
        feature_name=guide.name, excel_feature_key=guide.key, key_features=keys, role="RM")
    assert videos == []
