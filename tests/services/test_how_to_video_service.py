
import json

from unittest.mock import AsyncMock

import pytest

from app.services.how_to_video_service import (
    HowToVideoService,
    get_player,
)


SAMPLE_CACHE = {
    "data": {
        "howToVideos": [
            {
                "title": "How to Create EOI",
                "videos": [
                    {
                        "title": "How to Create EOI",
                        "video_url": (
                            "https://youtube.com/shorts/"
                            "-TtcOV3AmnE"
                        ),
                        "video_duration": "01:49",
                    }
                ],
                "allowed_roles": [
                    "Agent",
                    "SALES_MANAGER",
                ],
            }
        ]
    }
}


@pytest.fixture
def service():
    redis = AsyncMock()
    redis.get.return_value = json.dumps(
        SAMPLE_CACHE
    )
    return HowToVideoService(redis)


@pytest.mark.asyncio
async def test_video_allowed(service):

    videos = await service.find_videos(
        feature_name="Create EOI",
        excel_feature_key="EoiView/EoiCreate",
        key_features="EoiView,EoiCreate",
        role="Agent",
    )

    assert len(videos) == 1
    assert videos[0]["kind"] == "youtube"


@pytest.mark.asyncio
async def test_video_denied_for_missing_key(service):

    videos = await service.find_videos(
        feature_name="Create EOI",
        excel_feature_key="EoiView/EoiCreate",
        key_features="EoiView",
        role="Agent",
    )

    assert videos == []


@pytest.mark.asyncio
async def test_video_denied_for_role(service):

    videos = await service.find_videos(
        feature_name="Create EOI",
        excel_feature_key="EoiView/EoiCreate",
        key_features="EoiView,EoiCreate",
        role="UnknownRole",
    )

    assert videos == []


@pytest.mark.asyncio
async def test_video_denied_for_wrong_feature(service):

    videos = await service.find_videos(
        feature_name="Unit Details Page",
        excel_feature_key="UDPage",
        key_features="UDPage",
        role="Agent",
    )

    assert videos == []


def test_youtube_shorts_conversion():

    player = get_player(
        "https://youtube.com/shorts/-TtcOV3AmnE"
    )

    assert player == {
        "kind": "youtube",
        "url": (
            "https://www.youtube-nocookie.com"
            "/embed/-TtcOV3AmnE"
        ),
    }


def test_invalid_video_url():

    assert get_player(
        "javascript:alert(1)"
    ) is None
