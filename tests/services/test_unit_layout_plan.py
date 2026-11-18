
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.handlers.inventory_handler import InventoryHandler
from app.retrieval.unit_layout_connector import UnitLayoutConnector
from app.schemas.retrieval import InventorySnapshot, InventoryUnit


@pytest.mark.asyncio
async def test_unit_layout_plan_success(monkeypatch):

    # Prevent unrelated unit-comparison client configuration
    # from affecting this isolated handler test.
    monkeypatch.setattr(
        "app.handlers.inventory_handler.UnitComparisonClient",
        lambda: object(),
    )

    snapshot = InventorySnapshot(
        units=[
            InventoryUnit(
                unit_id="a1KFV00000082Ea2AI",
                unit_name="GRZ-TH-241",
                unit_code="241",
                project_name="GREENZ BY DANUBE",
            )
        ]
    )

    handler = InventoryHandler(
        snapshot=snapshot,
        payment_token="test-token",
        user_id="test-user",
    )

    handler.unit_layout_connector.get_layout_plans = AsyncMock(
        return_value=[
            {
                "name": "Furniture Plan.jpeg",
                "download_url": (
                    "https://example.file.force.com/"
                    "sfc/dist/version/download/"
                ),
                "file_size_bytes": 1048576,
            }
        ]
    )

    intent = SimpleNamespace(
        inventory_operation="unit_layout_plan",
        unit_number="GRZ-TH-241",
        unit_name=None,
        unit_id=None,
        project_name=None,
    )

    result = await handler.handle(intent)

    assert result.has_data is True
    assert len(result.files) == 1
    assert len(result.html_blocks) == 1
    assert result.files[0]["file_size_display"] == "1.00 MB"
    assert result.html_blocks[0]["card_type"] == "unit_layout_plan"

    handler.unit_layout_connector.get_layout_plans.assert_awaited_once_with(
        unit_id="a1KFV00000082Ea2AI",
        access_token="test-token",
        user_id="test-user",
    )


@pytest.mark.asyncio
async def test_unit_layout_plan_not_found(monkeypatch):

    monkeypatch.setattr(
        "app.handlers.inventory_handler.UnitComparisonClient",
        lambda: object(),
    )

    handler = InventoryHandler(
        snapshot=InventorySnapshot(units=[]),
        payment_token="test-token",
        user_id="test-user",
    )

    handler.unit_layout_connector.get_layout_plans = AsyncMock()

    intent = SimpleNamespace(
        inventory_operation="unit_layout_plan",
        unit_number="GRZ-TH-999",
        unit_name=None,
        unit_id=None,
        project_name=None,
    )

    result = await handler.handle(intent)

    assert result.has_data is False
    assert len(result.files) == 0
    handler.unit_layout_connector.get_layout_plans.assert_not_awaited()


@pytest.mark.asyncio
async def test_unit_layout_plan_empty_files(monkeypatch):

    monkeypatch.setattr(
        "app.handlers.inventory_handler.UnitComparisonClient",
        lambda: object(),
    )

    handler = InventoryHandler(
        snapshot=InventorySnapshot(
            units=[
                InventoryUnit(
                    unit_id="a1KFV00000082Ea2AI",
                    unit_name="GRZ-TH-241",
                )
            ]
        ),
        payment_token="test-token",
        user_id="test-user",
    )

    handler.unit_layout_connector.get_layout_plans = AsyncMock(
        return_value=[]
    )

    intent = SimpleNamespace(
        inventory_operation="unit_layout_plan",
        unit_number="GRZ-TH-241",
        unit_name=None,
        unit_id=None,
        project_name=None,
    )

    result = await handler.handle(intent)

    assert result.has_data is False
    assert len(result.html_blocks) == 0
    assert "No layout plan" in result.messages[0]
