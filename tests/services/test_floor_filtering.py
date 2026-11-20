
import pytest

from app.schemas.retrieval import InventoryUnit
from app.schemas.routing import RoutingIntent
from app.services.inventory_filter_service import (
    InventoryFilterService,
)
from app.utils.floor_utils import (
    extract_floor_from_name,
    get_unit_floor,
)


@pytest.mark.parametrize(
    "unit_name, expected",
    [
        ("SRNZ-A-F01-101", 1),
        ("SRNZ-B-F01-101", 1),
        ("B101Z-F100-10007", 100),
        ("B101Z-F20-2027", 20),
        ("DMZ-F16-1624", 16),
        ("ETZ-3-A-F37-3705", 37),
        ("ETZ-A-F02-203", 2),
        ("ETZ-B-F29-2905", 29),
        ("FNZ-1-F26-2601", 26),
        ("SPZ-B-F29-2917", 29),
        ("VWZ-V1-F36-3602", 36),
        ("VWZ-V2-F04-408", 4),
        ("B102Z-F20-2005", 20),
        ("TMZ-F33-3318", 33),
        ("SPLZ-A-F08-803", 8),
        ("SPLZ-B-F08-810", 8),
        ("ASPZ-F02-201", 2),
        ("SRKZ-F18-1801", 18),
        ("OAZ-1-GF-RETAIL 02", 0),
        ("UNKNOWN-UNIT", None),
    ],
)
def test_floor_extraction(unit_name, expected):
    assert extract_floor_from_name(unit_name) == expected


def make_intent(**filters):
    data = {
        "intent": "inventory",
        "original_query": "Find units",
        "expanded_query": "Find units",
        "action": "search",
        "project_name": None,
        "unit_number": None,
        "bedrooms": None,
        "currency": None,
        "file_format": None,
        "bank_account_types": [],
        "marketing_assets": [],
        "missing_fields": [],
        "requires_clarification": False,
        "inventory_scope": "units",
        "inventory_operation": "unit_search",
    }
    data.update(filters)
    return RoutingIntent(**data)


def sample_units():
    names = [
        "SRNZ-A-F01-101",
        "B101Z-F20-2027",
        "ETZ-3-A-F37-3705",
        "B101Z-F100-10007",
        "OAZ-1-GF-RETAIL 02",
    ]
    return [
        InventoryUnit(unit_name=name)
        for name in names
    ]


def filter_names(**filters):
    result = InventoryFilterService().filter_units(
        sample_units(),
        make_intent(**filters),
    )
    return [unit.unit_name for unit in result]


def test_above_30():
    assert filter_names(
        min_floor=30,
        min_floor_inclusive=False,
    ) == [
        "ETZ-3-A-F37-3705",
        "B101Z-F100-10007",
    ]


def test_floor_30_and_above():
    assert filter_names(
        min_floor=20,
        min_floor_inclusive=True,
    ) == [
        "B101Z-F20-2027",
        "ETZ-3-A-F37-3705",
        "B101Z-F100-10007",
    ]


def test_below_20():
    assert filter_names(
        max_floor=20,
        max_floor_inclusive=False,
    ) == [
        "SRNZ-A-F01-101",
        "OAZ-1-GF-RETAIL 02",
    ]


def test_between_10_and_40():
    assert filter_names(
        min_floor=10,
        max_floor=40,
    ) == [
        "B101Z-F20-2027",
        "ETZ-3-A-F37-3705",
    ]


def test_ground_floor():
    assert filter_names(
        floor_number="GF",
    ) == [
        "OAZ-1-GF-RETAIL 02",
    ]


def test_exact_floor():
    assert filter_names(
        floor_number="37",
    ) == [
        "ETZ-3-A-F37-3705",
    ]


def test_name_takes_priority_over_salesforce():
    unit = InventoryUnit(
        unit_name="SRNZ-A-F37-3705",
        floor_number="20",
    )
    assert get_unit_floor(unit) == 37


def test_salesforce_fallback():
    unit = InventoryUnit(
        unit_name="UNKNOWN-UNIT",
        floor_number="29",
    )
    assert get_unit_floor(unit) == 29


def test_unknown_floor_excluded():
    unit = InventoryUnit(
        unit_name="UNKNOWN-UNIT",
    )
    result = InventoryFilterService().filter_units(
        [unit],
        make_intent(min_floor=10),
    )
    assert result == []
