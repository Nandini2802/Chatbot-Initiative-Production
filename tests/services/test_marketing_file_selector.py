
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.marketing import (
    MarketingAsset,
    MarketingFile,
)
from app.services.marketing_file_selector import (
    MarketingFileSelection,
    MarketingFileSelector,
)
from app.handlers.marketing_handler import MarketingHandler


FILE_NAMES = [
    "RT Adel S - Shahrukhz 2 Full Project.mp4",
    "SRK-King-Size-Teaser-Sub-Thumb.mp4",
    "The_king_returns_this_time_waterfront.mp4",
    "RT-Adel-S-Shahrukhz-2-Arabic.mp4",
    "Shahrukhz_Show_Appartment.mp4",
    "RT-Adel-S-Shahrukhz-2-Hindi.mp4",
    "S2-Signature-Kings-Ocean-Suite.mp4",
    "SRK-2-Sports-SM-v2.mp4",
    "SRK-2-Cabana-SM.mp4",
]


def get_files():
    return [
        MarketingFile(
            name=name,
            download_url=(
                f"https://example.com/video/{i}"
            ),
            file_size_bytes=1024 * (i + 1),
            updated_at="2026-10-10 06:23:05",
        )
        for i, name in enumerate(FILE_NAMES)
    ]


def mock_foundry(
    request_type="specific",
    selected_ids=None,
    confident=True,
):
    client = MagicMock()

    client.responses.parse = AsyncMock(
        return_value=SimpleNamespace(
            output_parsed=MarketingFileSelection(
                request_type=request_type,
                selected_ids=(
                    selected_ids
                    if selected_ids is not None
                    else []
                ),
                confident=confident,
            )
        )
    )

    return client


@pytest.mark.asyncio
async def test_apartment_video_selected():
    client = mock_foundry(
        selected_ids=[4]
    )

    selector = MarketingFileSelector(
        client=client,
        model="test-model",
    )

    selected = await selector.select_files(
        user_message=(
            "Show apartment video of Shahrukhz"
        ),
        project_name="Shahrukhz",
        asset_type="videos",
        files=get_files(),
    )

    assert len(selected) == 1
    assert selected[0].name == (
        "Shahrukhz_Show_Appartment.mp4"
    )


@pytest.mark.asyncio
async def test_hindi_video_selected():
    client = mock_foundry(
        selected_ids=[5]
    )

    selector = MarketingFileSelector(
        client=client,
        model="test-model",
    )

    selected = await selector.select_files(
        user_message="Give me the Hindi video",
        project_name="Shahrukhz",
        asset_type="videos",
        files=get_files(),
    )

    assert len(selected) == 1
    assert selected[0].name == (
        "RT-Adel-S-Shahrukhz-2-Hindi.mp4"
    )


@pytest.mark.asyncio
async def test_generic_request_returns_all():
    client = mock_foundry(
        request_type="all",
        selected_ids=[],
        confident=False,
    )

    selector = MarketingFileSelector(
        client=client,
        model="test-model",
    )

    selected = await selector.select_files(
        user_message="Show all Shahrukhz videos",
        project_name="Shahrukhz",
        asset_type="videos",
        files=get_files(),
    )

    assert len(selected) == 9


@pytest.mark.asyncio
async def test_no_confident_match_returns_all():
    client = mock_foundry(
        selected_ids=[],
        confident=False,
    )

    selector = MarketingFileSelector(
        client=client,
        model="test-model",
    )

    selected = await selector.select_files(
        user_message="Swimming pool video",
        project_name="Shahrukhz",
        asset_type="videos",
        files=get_files(),
    )

    assert len(selected) == 9


@pytest.mark.asyncio
async def test_invalid_index_returns_all():
    client = mock_foundry(
        selected_ids=[999]
    )

    selector = MarketingFileSelector(
        client=client,
        model="test-model",
    )

    selected = await selector.select_files(
        user_message="Apartment video",
        project_name="Shahrukhz",
        asset_type="videos",
        files=get_files(),
    )

    assert len(selected) == 9


@pytest.mark.asyncio
async def test_multiple_matches():
    client = mock_foundry(
        selected_ids=[3, 5]
    )

    selector = MarketingFileSelector(
        client=client,
        model="test-model",
    )

    selected = await selector.select_files(
        user_message=(
            "Give me Hindi and Arabic videos"
        ),
        project_name="Shahrukhz",
        asset_type="videos",
        files=get_files(),
    )

    assert len(selected) == 2

    assert {
        file.name for file in selected
    } == {
        FILE_NAMES[3],
        FILE_NAMES[5],
    }


@pytest.mark.asyncio
async def test_foundry_failure_returns_all():
    client = MagicMock()
    client.responses.parse = AsyncMock(
        side_effect=RuntimeError(
            "Foundry unavailable"
        )
    )

    selector = MarketingFileSelector(
        client=client,
        model="test-model",
    )

    selected = await selector.select_files(
        user_message="Apartment video",
        project_name="Shahrukhz",
        asset_type="videos",
        files=get_files(),
    )

    assert len(selected) == 9


@pytest.mark.asyncio
async def test_handler_renders_only_selected_video():
    client = mock_foundry(
        selected_ids=[4]
    )

    handler = MarketingHandler(
        redis_client=None,
        client=client,
        model="test-model",
        message=(
            "Show apartment video of Shahrukhz"
        ),
    )

    handler.marketing_service.get_assets = AsyncMock(
        return_value=[
            MarketingAsset(
                project="Shahrukhz",
                asset_type="videos",
                files=get_files(),
                total_files=9,
            )
        ]
    )

    intent = SimpleNamespace(
        intent="marketing",
        project_name="Shahrukhz",
        marketing_assets=["videos"],
        original_query=(
            "Show apartment video of Shahrukhz"
        ),
    )

    result = await handler.handle(intent)

    assert result.has_data is True
    assert len(result.files) == 1

    assert result.files[0]["name"] == (
        "Shahrukhz_Show_Appartment.mp4"
    )

    assert len(result.html_blocks) == 1

    html = result.html_blocks[0]["html"]

    assert "Shahrukhz_Show_Appartment.mp4" in html
    assert "SRK-2-Cabana-SM.mp4" not in html
    assert "RT-Adel-S-Shahrukhz-2-Hindi.mp4" not in html


@pytest.mark.asyncio
async def test_zip_category_unchanged():
    client = mock_foundry(
        selected_ids=[0]
    )

    handler = MarketingHandler(
        redis_client=None,
        client=client,
        model="test-model",
        message="Show Shahrukhz floor plans",
    )

    handler.marketing_service.get_assets = AsyncMock(
        return_value=[
            MarketingAsset(
                project="Shahrukhz",
                asset_type="floor-plans",
                zip_url=(
                    "https://example.com/floor-plans.zip"
                ),
                total_files=2,
                total_size_bytes=19924309,
            )
        ]
    )

    intent = SimpleNamespace(
        intent="marketing",
        project_name="Shahrukhz",
        marketing_assets=["floor-plans"],
        original_query="Show Shahrukhz floor plans",
    )

    result = await handler.handle(intent)

    assert result.has_data is True
    assert len(result.files) == 1
    assert result.files[0]["format"] == "zip"

    # The LLM selector is not used for
    # existing ZIP-only marketing categories.
    client.responses.parse.assert_not_awaited()
