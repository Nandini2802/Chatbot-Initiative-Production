import pytest

from app.schemas.retrieval import InventoryUnit
from app.schemas.routing import RoutingIntent
from app.services.inventory_filter_service import (
    matches_unit_series,
    InventoryFilterService,
)


@pytest.mark.parametrize(
    "unit_name,series,expected",
    [
        ("FNZ-1-F40-4009", "09", True),
        ("FNZ-1-F40-4008", "09", False),
        ("FNZ-1-F40-4090", "09", False),
        ("FNZ-1-F40-4001", "01", True),
        ("FNZ-1-F40-4012", "12", True),
        ("FNZ-1-F40-4009", "9", False),
        ("FNZ-1-F40-4009", "90", False),
        ("FNZ-1-F40-4009", "XX", False),
    ],
)
def test_series_matching(unit_name, series, expected):
    unit = InventoryUnit(
        unit_name=unit_name,
    )

    assert matches_unit_series(unit, series) is expected


def test_series_across_projects():
    units = [
        InventoryUnit(
            unit_name="FNZ-1-F40-4009",
            project_name="FASHIONZ 1",
            status="Available",
        ),
        InventoryUnit(
            unit_name="ABC-1-F20-2009",
            project_name="OTHER PROJECT",
            status="Available",
        ),
        InventoryUnit(
            unit_name="FNZ-1-F40-4010",
            project_name="FASHIONZ 1",
            status="Available",
        ),
        InventoryUnit(
            unit_name="FNZ-1-F40-4109",
            project_name="FASHIONZ 1",
            status="Sold",
        ),
    ]

    # Construct only the fields required for this test.
    intent = RoutingIntent.model_construct(
        series="09",
        project_name=None,
        unit_number=None,
        status="Available",
        currency=None,
        project_location=None,
        category=None,
        unit_type=None,
        bedrooms=None,
        typology=None,
        view=None,
        handover_status=None,
        construction_status=None,
        requires_pool=False,
        requires_duplex=False,
        floor_number=None,
        min_floor=None,
        max_floor=None,
        min_price=None,
        max_price=None,
        min_area_sqft=None,
        max_area_sqft=None,
        price_selection=None,
    )

    matches = InventoryFilterService().filter_units(
        units=units,
        intent=intent,
    )

    assert {
        unit.unit_name for unit in matches
    } == {
        "FNZ-1-F40-4009",
        "ABC-1-F20-2009",
    }
